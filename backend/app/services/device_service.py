import asyncio
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import AlertRule, Device, DeviceLog, PowerLog, Room


class DeviceService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_devices(self):
        return self.db.query(Device).order_by(Device.id).all()

    def get_device(self, device_id: int):
        return self.db.query(Device).filter(Device.id == device_id).first()

    def get_room_devices(self, room_id: int):
        return (
            self.db.query(Device)
            .filter(Device.room_id == room_id)
            .order_by(Device.id)
            .all()
        )

    def get_total_power(self):
        total_power = (
            self.db.query(func.coalesce(func.sum(Device.power_rating), 0.0))
            .filter(Device.is_active.is_(True))
            .scalar()
        )
        return float(total_power or 0.0)

    def _schedule_broadcast(self, event_type: str, payload: dict):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        from app.services.websocket_manager import manager

        loop.create_task(manager.broadcast(event_type, payload))

    def toggle_device(self, device_id: int):
        device = self.get_device(device_id)
        if device is None:
            raise ValueError(f"Device with id {device_id} not found")

        try:
            device.is_active = not device.is_active
            device.last_updated = datetime.now(UTC)

            self.db.add(
                DeviceLog(
                    device_id=device.id,
                    is_active=device.is_active,
                    timestamp=device.last_updated,
                )
            )

            self.db.flush()

            total_power = self.get_total_power()
            self.db.add(
                PowerLog(
                    total_power=total_power,
                    timestamp=device.last_updated,
                )
            )

            self.db.commit()
            self.db.refresh(device)

            self._schedule_broadcast(
                "device_updated",
                {
                    "id": device.id,
                    "room_id": device.room_id,
                    "name": device.name,
                    "type": device.type.value,
                    "power_rating": device.power_rating,
                    "is_active": device.is_active,
                    "last_updated": device.last_updated.isoformat(),
                },
            )
            self._schedule_broadcast(
                "power_updated",
                {
                    "total_power": total_power,
                    "timestamp": device.last_updated.isoformat(),
                },
            )

            from app.services.alert_engine import AlertEngine

            engine = AlertEngine(self.db)

            # Rule 3: high total power draw — event-driven, checked on every toggle.
            if engine.check_power_exceeded(total_power):
                engine.trigger_alert(
                    AlertRule.POWER_EXCEEDED,
                    f"Total power exceeded {engine.POWER_THRESHOLD}W: {total_power:.1f}W",
                    metadata={"total_power": total_power},
                )
            else:
                engine.resolve_alert(AlertRule.POWER_EXCEEDED)

            # Rule 2: a fully-active room no longer alerts instantly. Instead we
            # just record/clear the timestamp the room became fully active;
            # AlertScheduler periodically checks that timestamp and raises the
            # alert once a room has stayed fully active for 2+ hours.
            room = self.db.query(Room).filter(Room.id == device.room_id).first()
            if room is not None:
                if engine.check_room_completely_active(device.room_id):
                    if room.all_active_since is None:
                        room.all_active_since = device.last_updated
                        self.db.commit()
                else:
                    if room.all_active_since is not None:
                        room.all_active_since = None
                        self.db.commit()
                    # The room condition no longer holds, so resolve immediately
                    # rather than waiting for the next scheduler tick.
                    engine.resolve_alert(AlertRule.ROOM_COMPLETELY_ACTIVE, room_id=device.room_id)

            # Rule 1: devices left on after office hours — event-driven, checked
            # on every toggle instead of waiting for the periodic scheduler.
            if engine.check_devices_after_hours():
                engine.trigger_alert(
                    AlertRule.DEVICES_AFTER_HOURS,
                    "Devices are active outside office hours (8 AM - 6 PM)",
                )
            else:
                engine.resolve_alert(AlertRule.DEVICES_AFTER_HOURS)

            return device
        except Exception:
            self.db.rollback()
            raise
