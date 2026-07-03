from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Device, DeviceLog, PowerLog, AlertRule


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

            # Trigger event-based alert rules
            from app.services.alert_engine import AlertEngine
            engine = AlertEngine(self.db)

            # Check power exceeded
            if engine.check_power_exceeded(total_power):
                engine.trigger_alert(
                    AlertRule.POWER_EXCEEDED,
                    f"Total power exceeded {engine.POWER_THRESHOLD}W: {total_power:.1f}W",
                )
            else:
                engine.check_and_resolve_power_exceeded(total_power)

            # Check room completely active
            if engine.check_room_completely_active(device.room_id):
                engine.trigger_alert(
                    AlertRule.ROOM_COMPLETELY_ACTIVE,
                    f"All devices in room {device.room_id} are active",
                )
            else:
                engine.check_and_resolve_room_active(device.room_id)

            return device
        except Exception:
            self.db.rollback()
            raise
