"""GeminiService: turns structured backend data into short, readable text.

Architecture (per Milestone 10):

    Alert Engine -> Alert Service -> Gemini Service -> Natural Language Message

GeminiService sits at the bottom of that pipeline. It never decides *whether*
something is an alert, a threshold breach, or worth mentioning -- all of that
business logic already happened upstream in AlertEngine/AlertService (or in
whatever assembled the status/power/office snapshot). This service's only job
is to phrase already-decided structured data into professional, human-
readable text.

Design choices, and why:

- Reads GEMINI_API_KEY from the environment (via python-dotenv, so a local
  .env file works too) -- never hardcoded, never passed around as a literal.
- If the key is missing, the SDK import fails, the API call errors, or the
  call times out, this NEVER raises out of these four public methods. It
  logs the problem and returns a deterministic template string instead, so
  a Gemini outage can't take the backend down with it.
- Every prompt embeds the same hard constraints (professional tone, <=120
  words, don't invent facts, only reference supplied data, at most one
  recommendation) so behavior is consistent across all four message types.
"""

from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv

# Loads a local .env file if present (no-op if it doesn't exist or the
# variable is already set in the real environment -- e.g. in production).
load_dotenv()

logger = logging.getLogger(__name__)

try:
    from google import genai
    from google.genai import types as genai_types

    _GENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only if the package is missing
    genai = None
    genai_types = None
    _GENAI_IMPORT_ERROR = exc

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TIMEOUT_MS = 10_000  # 10s -- bounded so a slow/hanging call can't stall a request
MAX_WORDS = 120

SYSTEM_INSTRUCTION = f"""You are a smart-office energy monitoring assistant. You convert \
structured backend data into a short, professional notification for facility staff.

Rules you must always follow:
- Do not invent, assume, or infer any fact that is not present in the data you are given.
- Reference only the values, device names, rooms, numbers, and times supplied in the data.
- Keep the tone professional and concise.
- Keep the message under {MAX_WORDS} words.
- The decision that this is worth reporting has already been made upstream -- your only \
job is to phrase the given facts clearly. Do not add caveats about whether it's really a \
problem, and do not question or second-guess the data.
- If, and only if, a practical recommendation is clearly supported by the data, include \
exactly one brief, actionable suggestion. Otherwise omit it -- do not force one in.
- Output plain text only: no markdown, no headings, no bullet points."""


class GeminiService:
    """Reusable wrapper around the Gemini API for natural-language summaries.

    Safe to instantiate even with no API key configured, and safe to call
    even if every call fails -- every public method falls back to a
    deterministic template rather than raising.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ):
        self.model = model
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._client = None

        if _GENAI_IMPORT_ERROR is not None:
            logger.warning(
                "google-genai is not installed (%s); GeminiService will use "
                "fallback template messages only.",
                _GENAI_IMPORT_ERROR,
            )
            return

        if not self._api_key:
            logger.warning(
                "GEMINI_API_KEY is not set; GeminiService will use fallback "
                "template messages only."
            )
            return

        try:
            self._client = genai.Client(
                api_key=self._api_key,
                http_options=genai_types.HttpOptions(timeout=timeout_ms),
            )
        except Exception:
            logger.exception("Failed to initialize the Gemini client")
            self._client = None

    @property
    def is_available(self) -> bool:
        """True if a real Gemini client was constructed and calls will be attempted."""
        return self._client is not None

    # -- public API --------------------------------------------------------

    def generate_alert_message(self, alert_data: dict) -> str:
        """Turn an already-triggered alert's structured data into readable text.

        Example input:
            {
                "alert_type": "AFTER_HOURS",
                "room": "Drawing Room",
                "active_devices": ["Fan 1", "Fan 2", "Light 1"],
                "time": "21:30",
            }
        """
        prompt = (
            "Write a short after-the-fact alert notification for facility staff "
            "based on this alert data (JSON):\n"
            f"{json.dumps(alert_data, indent=2, default=str)}"
        )
        return self._generate(prompt, fallback=self._fallback_alert_message(alert_data))

    def generate_status_summary(self, status_data: dict) -> str:
        """Turn a current device/room status snapshot into readable text."""
        prompt = (
            "Write a brief current-status summary for facility staff based on "
            f"this data (JSON):\n{json.dumps(status_data, indent=2, default=str)}"
        )
        return self._generate(prompt, fallback=self._fallback_status_summary(status_data))

    def generate_power_summary(self, power_data: dict) -> str:
        """Turn a power/energy-usage snapshot into readable text."""
        prompt = (
            "Write a brief power-consumption summary for facility staff based on "
            f"this data (JSON):\n{json.dumps(power_data, indent=2, default=str)}"
        )
        return self._generate(prompt, fallback=self._fallback_power_summary(power_data))

    def generate_office_analysis(self, office_data: dict) -> str:
        """Turn a combined office-wide snapshot (rooms, power, alerts) into readable text."""
        prompt = (
            "Write a brief overall analysis of current office conditions for "
            f"facility staff based on this data (JSON):\n"
            f"{json.dumps(office_data, indent=2, default=str)}"
        )
        return self._generate(prompt, fallback=self._fallback_office_analysis(office_data))

    # -- Gemini call + fallback dispatch ------------------------------------

    def _generate(self, prompt: str, fallback: str) -> str:
        if self._client is None:
            return fallback

        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.3,
                    max_output_tokens=300,
                ),
            )
            text = (getattr(response, "text", None) or "").strip()
            if not text:
                logger.warning("Gemini returned an empty response; using fallback message")
                return fallback
            return text
        except Exception:
            # Covers timeouts, network errors, auth failures, rate limits, and
            # anything else the SDK might raise -- the backend must keep working
            # regardless of what Gemini does.
            logger.exception("Gemini API call failed; using fallback message")
            return fallback

    # -- deterministic fallback templates -----------------------------------
    # These intentionally use only .get()/defaults so a caller can never crash
    # this service by passing a dict with missing or unexpected keys.

    @staticmethod
    def _fallback_alert_message(alert_data: dict) -> str:
        alert_type = alert_data.get("alert_type") or "Alert"
        room = alert_data.get("room")
        devices = alert_data.get("active_devices") or []
        time = alert_data.get("time")

        label = str(alert_type).replace("_", " ").strip().title()
        parts = [f"{label} detected"]
        if room:
            parts.append(f"in {room}")
        if time:
            parts.append(f"at {time}")
        message = " ".join(parts) + "."

        if devices:
            message += f" Active device(s): {', '.join(str(d) for d in devices)}."

        return message

    @staticmethod
    def _fallback_status_summary(status_data: dict) -> str:
        total_devices = status_data.get("total_devices")
        active_devices = status_data.get("active_devices")
        total_rooms = status_data.get("total_rooms")
        active_rooms = status_data.get("active_rooms")

        bits = []
        if active_devices is not None and total_devices is not None:
            bits.append(f"{active_devices} of {total_devices} device(s) currently active")
        if active_rooms is not None and total_rooms is not None:
            bits.append(f"{active_rooms} of {total_rooms} room(s) fully active")

        if not bits:
            return "Status summary is currently unavailable."
        return "Status summary: " + "; ".join(bits) + "."

    @staticmethod
    def _fallback_power_summary(power_data: dict) -> str:
        total_power = power_data.get("total_power")
        usage_wh = power_data.get("total_power_usage_wh")
        predicted_wh = power_data.get("predicted_power_usage_wh")

        bits = []
        if total_power is not None:
            bits.append(f"current total draw is {total_power:.1f}W")
        if usage_wh is not None:
            bits.append(f"{usage_wh:.1f}Wh consumed so far today")
        if predicted_wh is not None:
            bits.append(f"a projected {predicted_wh:.1f}Wh for the full day")

        if not bits:
            return "Power summary is currently unavailable."
        return "Power summary: " + ", ".join(bits) + "."

    @staticmethod
    def _fallback_office_analysis(office_data: dict) -> str:
        active_alerts = office_data.get("active_alerts")
        total_power = office_data.get("total_power")
        active_rooms = office_data.get("active_rooms")
        total_rooms = office_data.get("total_rooms")

        bits = []
        if total_power is not None:
            bits.append(f"total power draw is {total_power:.1f}W")
        if active_rooms is not None and total_rooms is not None:
            bits.append(f"{active_rooms} of {total_rooms} room(s) fully active")
        if active_alerts is not None:
            bits.append(f"{active_alerts} active alert(s)")

        if not bits:
            return "Office analysis is currently unavailable."
        return "Office analysis: " + ", ".join(bits) + "."


# Module-level singleton. Building a GeminiService is cheap (it never makes a
# network call in __init__), but reusing one instance avoids re-reading the
# environment and re-constructing the SDK client on every request. Callers
# that want an isolated instance (e.g. tests, or a specific api key/model)
# should construct GeminiService(...) directly instead of using this.
_default_instance: "GeminiService | None" = None


def get_gemini_service() -> "GeminiService":
    global _default_instance
    if _default_instance is None:
        _default_instance = GeminiService()
    return _default_instance
