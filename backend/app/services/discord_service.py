"""DiscordService: delivers AI-enhanced alert notifications to Discord.

Architecture (per Milestone 11):

    Alert Engine -> Alert Service -> Gemini Service -> Discord Service -> Discord Channel

DiscordService sits at the very end of that pipeline. It never decides
*whether* something is alert-worthy -- AlertEngine already made that call
upstream when it created the Alert row, and GeminiService already turned
the resulting structured data into a human-readable message. This
service's only job is to render that message as a Discord embed and
deliver it.

Design choices, and why:

- Reads DISCORD_WEBHOOK_URL from the environment (via python-dotenv, so a
  local .env file works too) -- never hardcoded.
- Delivery uses a Discord webhook (a single POST with an embed payload)
  rather than a full bot client. The backend only ever *sends*
  notifications; it never needs to receive Discord events, so a webhook is
  the simplest correct tool and keeps the backend free of any long-lived
  bot connection or token.
- If the webhook URL is missing, httpx isn't installed, the request fails,
  times out, or Discord returns an error response, this NEVER raises out
  of `notify_alert`. It logs the problem and returns False instead, so a
  Discord outage can't take the backend down with it -- satisfying the
  milestone's "Continues functioning if Discord ... becomes unavailable"
  requirement.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

# Loads a local .env file if present (no-op if it doesn't exist or the
# variable is already set in the real environment -- e.g. in production).
load_dotenv()

logger = logging.getLogger(__name__)

try:
    import httpx

    _HTTPX_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - exercised only if the package is missing
    httpx = None
    _HTTPX_IMPORT_ERROR = exc

DEFAULT_TIMEOUT_S = 10.0  # bounded so a slow/hanging webhook can't stall a caller

# (icon, color) per alert rule, purely cosmetic. Falls back to a generic
# bell/blue for any rule not listed here (e.g. future AlertRule values).
RULE_STYLE = {
    "power_exceeded": ("⚡", 0xE74C3C),
    "room_completely_active": ("🏠", 0xF1C40F),
    "devices_after_hours": ("🌙", 0x9B59B6),
    "high_power_sustained": ("🔥", 0xE67E22),
}
DEFAULT_STYLE = ("🔔", 0x3498DB)


class DiscordService:
    """Delivers alert notifications to a Discord channel via a webhook.

    Safe to instantiate even with no webhook configured, and safe to call
    even if every delivery attempt fails -- `notify_alert` falls back to
    doing nothing (and logging why) rather than raising.
    """

    def __init__(self, webhook_url: str | None = None, timeout_s: float = DEFAULT_TIMEOUT_S):
        self._webhook_url = webhook_url or os.environ.get("DISCORD_WEBHOOK_URL") or None
        self._timeout_s = timeout_s

        if _HTTPX_IMPORT_ERROR is not None:
            logger.warning(
                "httpx is not installed (%s); DiscordService will not deliver "
                "notifications.",
                _HTTPX_IMPORT_ERROR,
            )
        elif not self._webhook_url:
            logger.info(
                "DISCORD_WEBHOOK_URL is not set; automatic Discord alert "
                "notifications are disabled."
            )

    @property
    def is_configured(self) -> bool:
        """True if a webhook URL is set and httpx is available."""
        return bool(self._webhook_url) and httpx is not None

    # -- public API ----------------------------------------------------------

    async def notify_alert(self, alert_data: dict, message: str) -> bool:
        """Deliver one already-phrased alert message to Discord.

        `alert_data` is the same structured dict AlertService builds for
        GeminiService (alert_type/room/active_devices/etc); `message` is
        the text GeminiService already generated for it. This method only
        renders and delivers -- it never talks to Gemini itself, so a
        caller that wants to skip AI phrasing can pass any plain string.

        Returns True if the notification was handed off successfully,
        False otherwise (including "not configured", which is not an
        error -- it's the expected state when no webhook is set up).
        """
        if not self.is_configured:
            return False

        payload = {"embeds": [self._build_embed(alert_data, message)]}

        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await client.post(self._webhook_url, json=payload)
                response.raise_for_status()
            return True
        except Exception:
            # Covers timeouts, network errors, invalid webhook URLs, rate
            # limits, and anything else httpx might raise -- the backend
            # must keep working regardless of what Discord does.
            logger.exception("Failed to deliver Discord alert notification; continuing without it")
            return False

    # -- embed rendering -------------------------------------------------------
    # Kept as a pure function of (alert_data, message) so it's trivially
    # testable without a network call.

    @staticmethod
    def _build_embed(alert_data: dict, message: str) -> dict:
        rule = str(alert_data.get("alert_type") or "alert")
        icon, color = RULE_STYLE.get(rule, DEFAULT_STYLE)
        title = f"{icon} {rule.replace('_', ' ').title()}"

        room = alert_data.get("room")
        if room:
            title += f" — {room}"

        fields = []

        devices = alert_data.get("active_devices") or []
        if devices:
            fields.append(
                {
                    "name": "Active Devices",
                    "value": ", ".join(str(d) for d in devices),
                    "inline": False,
                }
            )

        total_power = alert_data.get("total_power")
        if total_power is not None:
            fields.append({"name": "Total Power", "value": f"{total_power:.1f}W", "inline": True})

        time = alert_data.get("time")
        if time:
            fields.append({"name": "Time", "value": str(time), "inline": True})

        return {
            "title": title,
            "description": message,
            "color": color,
            "fields": fields,
        }


# Module-level singleton, mirroring GeminiService's pattern -- constructing
# one is cheap (no network call happens in __init__), but reusing an
# instance avoids re-reading the environment on every alert. Callers that
# want an isolated instance (e.g. tests, or a specific webhook URL) should
# construct DiscordService(...) directly instead of using this.
_default_instance: "DiscordService | None" = None


def get_discord_service() -> "DiscordService":
    global _default_instance
    if _default_instance is None:
        _default_instance = DiscordService()
    return _default_instance
