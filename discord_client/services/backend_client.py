"""BackendClient: the Discord client's only way of talking to the backend.

Per Milestone 11's design constraints, this client must never touch
SQLite and must never contain business logic -- this module is a thin
REST wrapper and nothing else. All business logic (alert rules, device
toggling, AI-generated summaries) lives in the FastAPI backend; slash
commands just call these methods and hand the result to an embed builder.
"""

from __future__ import annotations

import httpx

from config import BACKEND_URL, REQUEST_TIMEOUT_S


class BackendError(RuntimeError):
    """Raised when the backend can't be reached or returns an error response."""


class BackendClient:
    """Thin async HTTP wrapper around the FastAPI REST API.

    One instance is shared across the whole bot process (see bot.py) so
    every slash command reuses the same connection pool instead of opening
    a new client per interaction.
    """

    def __init__(self, base_url: str = BACKEND_URL, timeout_s: float = REQUEST_TIMEOUT_S):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout_s)

    async def close(self):
        await self._client.aclose()

    async def _get(self, path: str):
        try:
            response = await self._client.get(path)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            raise BackendError(
                f"Backend returned {exc.response.status_code} for {path}: {detail}"
            ) from exc
        except httpx.HTTPError as exc:
            raise BackendError(f"Could not reach backend at {path}: {exc}") from exc

    # -- reusable methods (per Milestone 11) --------------------------------

    async def get_devices(self) -> list[dict]:
        """GET /devices -- every device across every room."""
        return await self._get("/devices")

    async def get_power(self, include_summary: bool = True) -> dict:
        """GET /power, optionally enriched with the AI summary from
        GET /power/summary. The AI summary is best-effort: if it can't be
        fetched, `ai_summary` is simply None rather than failing the whole
        command.
        """
        data = await self._get("/power")
        if include_summary:
            try:
                summary = await self._get("/power/summary")
                data["ai_summary"] = summary.get("ai_summary")
            except BackendError:
                data["ai_summary"] = None
        return data

    async def get_alerts(self) -> list[dict]:
        """GET /alerts -- all currently active alerts."""
        return await self._get("/alerts")

    async def get_room(self, room_id: int) -> dict:
        """GET /rooms/{room_id} -- a room's details plus the devices inside it."""
        return await self._get(f"/rooms/{room_id}")

    async def get_analysis(self) -> dict:
        """GET /office/summary -- device status + current power + active
        alerts, plus a Gemini-generated office-wide analysis. This is the
        backend's combined analysis endpoint that Milestone 11's `/analyze`
        command displays as-is.
        """
        return await self._get("/office/summary")
