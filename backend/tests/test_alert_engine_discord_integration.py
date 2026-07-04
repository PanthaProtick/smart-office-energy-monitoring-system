"""Integration test for the automatic-notification pipeline added in
Milestone 11:

    Alert Engine -> Alert Service -> Gemini Service -> Discord Service -> Discord Channel

Uses an isolated in-memory SQLite DB and fakes both GeminiService and
DiscordService so this never hits the network.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import AlertRule
from app.services.alert_engine import AlertEngine


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class _FakeDiscordService:
    is_configured = True

    def __init__(self):
        self.notifications = []

    async def notify_alert(self, alert_data, message):
        self.notifications.append((alert_data, message))
        return True


class _UnconfiguredFakeDiscordService:
    is_configured = False

    async def notify_alert(self, alert_data, message):  # pragma: no cover - must never be called
        raise AssertionError("notify_alert should not be called when not configured")


class _FakeGeminiService:
    def generate_alert_message(self, alert_data):
        return "fake discord message"


def test_new_alert_triggers_discord_notification(db_session, monkeypatch):
    fake_discord = _FakeDiscordService()
    monkeypatch.setattr(
        "app.services.discord_service.get_discord_service", lambda: fake_discord
    )
    monkeypatch.setattr(
        "app.services.gemini_service.get_gemini_service", lambda: _FakeGeminiService()
    )

    engine = AlertEngine(db_session)

    async def run():
        engine.trigger_alert(AlertRule.DEVICES_AFTER_HOURS, "Devices active after hours")
        # Give the background task (and the thread it dispatches Gemini to)
        # a chance to actually run before the event loop is torn down.
        await asyncio.sleep(0.2)

    asyncio.run(run())

    assert len(fake_discord.notifications) == 1
    alert_data, message = fake_discord.notifications[0]
    assert alert_data["alert_type"] == "devices_after_hours"
    assert message == "fake discord message"


def test_resolving_an_alert_does_not_notify_discord(db_session, monkeypatch):
    fake_discord = _FakeDiscordService()
    monkeypatch.setattr(
        "app.services.discord_service.get_discord_service", lambda: fake_discord
    )
    monkeypatch.setattr(
        "app.services.gemini_service.get_gemini_service", lambda: _FakeGeminiService()
    )

    engine = AlertEngine(db_session)

    async def run():
        engine.trigger_alert(AlertRule.DEVICES_AFTER_HOURS, "Devices active after hours")
        await asyncio.sleep(0.2)
        engine.resolve_alert(AlertRule.DEVICES_AFTER_HOURS)
        await asyncio.sleep(0.2)

    asyncio.run(run())

    # Exactly one notification -- for the trigger, not the resolve.
    assert len(fake_discord.notifications) == 1


def test_no_notification_attempted_when_discord_not_configured(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.discord_service.get_discord_service",
        lambda: _UnconfiguredFakeDiscordService(),
    )

    engine = AlertEngine(db_session)

    async def run():
        engine.trigger_alert(AlertRule.DEVICES_AFTER_HOURS, "Devices active after hours")
        await asyncio.sleep(0.2)

    # Should not raise (the assertion inside notify_alert would surface as a
    # failure if it were ever called).
    asyncio.run(run())


def test_trigger_alert_outside_event_loop_does_not_raise(db_session, monkeypatch):
    """Mirrors the existing scheduler/service call sites, which call
    trigger_alert() from plain sync code with no running event loop."""
    monkeypatch.setattr(
        "app.services.discord_service.get_discord_service", lambda: _FakeDiscordService()
    )

    engine = AlertEngine(db_session)
    alert = engine.trigger_alert(AlertRule.DEVICES_AFTER_HOURS, "Devices active after hours")

    assert alert is not None
