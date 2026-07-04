"""Unit tests for DiscordService.

These never make a real network call: with no DISCORD_WEBHOOK_URL set, the
service is inert by design; where we test the "delivered" and "delivery
failed" paths, we monkeypatch httpx.AsyncClient rather than talking to a
real Discord webhook.
"""

import asyncio

import pytest

from app.services import discord_service as discord_service_module
from app.services.discord_service import DiscordService


@pytest.fixture
def no_webhook_service(monkeypatch):
    """A DiscordService guaranteed to have no webhook -- exercises the no-op path."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    return DiscordService(webhook_url=None)


# ---------------------------------------------------------------------------
# Unconfigured behavior (no webhook set at all)
# ---------------------------------------------------------------------------


def test_no_webhook_means_not_configured(no_webhook_service):
    assert no_webhook_service.is_configured is False


def test_notify_alert_is_a_noop_without_a_webhook(no_webhook_service):
    alert_data = {"alert_type": "power_exceeded", "room": None, "active_devices": [], "time": "12:00"}
    result = asyncio.run(no_webhook_service.notify_alert(alert_data, "Some message"))
    assert result is False


# ---------------------------------------------------------------------------
# Delivery (httpx.AsyncClient is faked so no real network call happens)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=204):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    def __init__(self, calls, response=None, exc=None, **kwargs):
        self._calls = calls
        self._response = response or _FakeResponse()
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        self._calls.append({"url": url, "json": json})
        if self._exc is not None:
            raise self._exc
        return self._response


def test_notify_alert_delivers_embed_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        discord_service_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(calls),
    )

    service = DiscordService(webhook_url="https://discord.example/webhook")
    alert_data = {
        "alert_type": "devices_after_hours",
        "room": "Drawing Room",
        "active_devices": ["Fan 1", "Light 1"],
        "time": "21:30",
    }

    result = asyncio.run(service.notify_alert(alert_data, "Devices left on after hours."))

    assert result is True
    assert len(calls) == 1
    assert calls[0]["url"] == "https://discord.example/webhook"
    embed = calls[0]["json"]["embeds"][0]
    assert "Drawing Room" in embed["title"]
    assert embed["description"] == "Devices left on after hours."
    assert any(f["name"] == "Active Devices" for f in embed["fields"])


def test_notify_alert_returns_false_and_never_raises_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        discord_service_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient(calls, exc=RuntimeError("network down")),
    )

    service = DiscordService(webhook_url="https://discord.example/webhook")
    result = asyncio.run(service.notify_alert({"alert_type": "power_exceeded"}, "message"))

    assert result is False


def test_notify_alert_returns_false_on_error_status(monkeypatch):
    monkeypatch.setattr(
        discord_service_module.httpx,
        "AsyncClient",
        lambda **kwargs: _FakeAsyncClient([], response=_FakeResponse(status_code=404)),
    )

    service = DiscordService(webhook_url="https://discord.example/webhook")
    result = asyncio.run(service.notify_alert({"alert_type": "power_exceeded"}, "message"))

    assert result is False


def test_embed_falls_back_to_generic_style_for_unknown_rule():
    embed = DiscordService._build_embed({"alert_type": "some_future_rule"}, "message")
    assert embed["description"] == "message"
    assert embed["color"] == discord_service_module.DEFAULT_STYLE[1]
