import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.database.models import Alert, AlertRule, AlertStatus, Device, Room


class AlertEngine:
    """Executes alert rules against current system state."""

    POWER_THRESHOLD = 200.0  # watts
    AFTER_HOURS_START = 18  # 6 PM
    AFTER_HOURS_END = 8  # 8 AM
    SUSTAINED_POWER_THRESHOLD = 150.0  # watts for 5+ minutes

    def __init__(self, db: Session):
        self.db = db

    def _schedule_broadcast(self, payload: dict):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        from app.services.websocket_manager import manager

        loop.create_task(manager.broadcast("alert_created", payload))

    def check_power_exceeded(self, current_total_power: float) -> bool:
        return current_total_power > self.POWER_THRESHOLD

    def check_room_completely_active(self, room_id: int) -> bool:
        room = self.db.query(Room).filter(Room.id == room_id).first()
        if not room:
            return False
        devices = self.db.query(Device).filter(Device.room_id == room_id).all()
        if not devices:
            return False
        return all(d.is_active for d in devices)

    def check_devices_after_hours(self) -> bool:
        now = datetime.now(UTC)
        hour = now.hour

        if hour < self.AFTER_HOURS_END or hour >= self.AFTER_HOURS_START:
            active_devices = self.db.query(Device).filter(Device.is_active.is_(True)).count()
            return active_devices > 0
        return False

    def check_high_power_sustained(self, current_total_power: float) -> bool:
        if current_total_power < self.SUSTAINED_POWER_THRESHOLD:
            return False

        from app.database.models import PowerLog

        five_min_ago = datetime.now(UTC) - timedelta(minutes=5)
        recent_logs = (
            self.db.query(PowerLog)
            .filter(PowerLog.timestamp >= five_min_ago)
            .order_by(PowerLog.timestamp.asc())
            .all()
        )

        if len(recent_logs) < 3:
            return False

        return all(log.total_power >= self.SUSTAINED_POWER_THRESHOLD for log in recent_logs)

    def _serialize_alert(self, alert: Alert) -> dict:
        return {
            "id": alert.id,
            "rule": alert.rule.value if hasattr(alert.rule, "value") else str(alert.rule),
            "status": alert.status.value if hasattr(alert.status, "value") else str(alert.status),
            "message": alert.message,
            "triggered_at": alert.triggered_at.isoformat(),
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "context": alert.context,
        }

    def trigger_alert(self, rule: AlertRule, message: str, metadata=None) -> Alert:
        existing = (
            self.db.query(Alert)
            .filter(Alert.rule == rule, Alert.status == AlertStatus.ACTIVE)
            .first()
        )

        if existing:
            return existing

        alert = Alert(
            rule=rule,
            status=AlertStatus.ACTIVE,
            message=message,
            triggered_at=datetime.now(UTC),
            context=json.dumps(metadata) if metadata is not None else None,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        self._schedule_broadcast(self._serialize_alert(alert))
        return alert

    def resolve_alert(self, rule: AlertRule) -> Alert:
        alert = (
            self.db.query(Alert)
            .filter(Alert.rule == rule, Alert.status == AlertStatus.ACTIVE)
            .first()
        )

        if alert:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(alert)
            self._schedule_broadcast(self._serialize_alert(alert))

        return alert
