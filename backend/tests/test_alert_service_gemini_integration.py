"""Integration test for the Alert Engine -> Alert Service -> Gemini Service pipeline.

Uses an isolated in-memory SQLite DB (no shared state with a real office.db)
and monkeypatches the Gemini call so this never hits the network, regardless
of whether GEMINI_API_KEY happens to be set in the environment running the
tests.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.database import Base
from app.database.models import AlertRule, Device, DeviceType, Room
from app.services.alert_engine import AlertEngine
from app.services.alert_service import AlertService
from app.services.device_service import DeviceService


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # device_service.toggle_device() reports through energy_service, which
    # requires this baseline to have been recorded once -- normally done by
    # main.py's startup event. Mirror that here so tests don't depend on
    # import order across the test session.
    from app.services import energy_service
    energy_service.initialize_baseline(session)

    yield session
    session.close()


@pytest.fixture
def seeded_room(db_session):
    room = Room(name="Drawing Room", device_count=2)
    db_session.add(room)
    db_session.commit()
    db_session.refresh(room)

    d1 = Device(
        room_id=room.id, name="Fan 1", type=DeviceType.FAN, power_rating=75,
        is_active=False, last_updated=datetime.now(UTC),
    )
    d2 = Device(
        room_id=room.id, name="Light 1", type=DeviceType.LIGHT, power_rating=20,
        is_active=False, last_updated=datetime.now(UTC),
    )
    db_session.add_all([d1, d2])
    db_session.commit()
    return room


def test_room_completely_active_alert_data_includes_room_and_devices(db_session, seeded_room):
    device_svc = DeviceService(db_session)
    for device in seeded_room.devices:
        device_svc.toggle_device(device.id)

    engine = AlertEngine(db_session)
    # Simulate the scheduler deciding the 2-hour threshold has been crossed --
    # AlertService.build_alert_data must never re-derive this itself.
    alert = engine.trigger_alert(
        AlertRule.ROOM_COMPLETELY_ACTIVE,
        "All devices in room 'Drawing Room' have been active for over 2 hours",
        metadata={"room_id": seeded_room.id},
        room_id=seeded_room.id,
    )

    alert_svc = AlertService(db_session)
    data = alert_svc.build_alert_data(alert)

    assert data["alert_type"] == "room_completely_active"
    assert data["room"] == "Drawing Room"
    assert set(data["active_devices"]) == {"Fan 1", "Light 1"}


def test_power_exceeded_alert_data_includes_total_power(db_session):
    engine = AlertEngine(db_session)
    alert = engine.trigger_alert(
        AlertRule.POWER_EXCEEDED,
        "Total power exceeded 500.0W: 620.5W",
        metadata={"total_power": 620.5},
    )

    alert_svc = AlertService(db_session)
    data = alert_svc.build_alert_data(alert)

    assert data["alert_type"] == "power_exceeded"
    assert data["total_power"] == 620.5
    assert data["room"] is None  # not a room-scoped rule


def test_generate_ai_message_uses_gemini_service_and_never_raises(db_session, monkeypatch):
    import app.services.alert_service as alert_service_module

    calls = []

    class FakeGeminiService:
        def generate_alert_message(self, alert_data):
            calls.append(alert_data)
            return "fake summary"

    monkeypatch.setattr(alert_service_module, "get_gemini_service", lambda: FakeGeminiService())

    engine = AlertEngine(db_session)
    alert = engine.trigger_alert(AlertRule.DEVICES_AFTER_HOURS, "Devices active after hours")

    alert_svc = AlertService(db_session)
    result = alert_svc.generate_ai_message(alert)

    assert result == "fake summary"
    assert calls[0]["alert_type"] == "devices_after_hours"
