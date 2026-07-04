import asyncio
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.database.models import Alert, AlertRule, AlertStatus, Device, Room


class AlertEngine:
    """Executes alert rules against current system state."""

    POWER_THRESHOLD = 500.0  # watts
    AFTER_HOURS_START = 18  # 6 PM
    AFTER_HOURS_END = 8  # 8 AM
    SUSTAINED_POWER_THRESHOLD = 150.0  # watts for 5+ minutes
    ROOM_ACTIVE_DURATION_THRESHOLD = timedelta(hours=2)

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

    def check_room_active_duration(self, room: Room) -> bool:
        """True if `room` has had every device active continuously for
        at least ROOM_ACTIVE_DURATION_THRESHOLD. Relies on
        Room.all_active_since, which DeviceService keeps up to date on
        every device toggle."""
        if room.all_active_since is None:
            return False

        since = room.all_active_since
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        return datetime.now(UTC) - since >= self.ROOM_ACTIVE_DURATION_THRESHOLD

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

    def _find_active_alert(self, rule: AlertRule, room_id: int | None = None) -> Alert | None:
        query = self.db.query(Alert).filter(Alert.rule == rule, Alert.status == AlertStatus.ACTIVE)

        if room_id is None:
            return query.first()

        # Rules like ROOM_COMPLETELY_ACTIVE can be active for several rooms
        # at once, so we disambiguate using the room_id stashed in context.
        for alert in query.all():
            if not alert.context:
                continue
            try:
                ctx = json.loads(alert.context)
            except (TypeError, ValueError):
                continue
            if ctx.get("room_id") == room_id:
                return alert
        return None

    def trigger_alert(
        self, rule: AlertRule, message: str, metadata=None, room_id: int | None = None
    ) -> Alert:
        existing = self._find_active_alert(rule, room_id)

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

    def resolve_alert(self, rule: AlertRule, room_id: int | None = None) -> Alert:
        alert = self._find_active_alert(rule, room_id)

        if alert:
            alert.status = AlertStatus.RESOLVED
            alert.resolved_at = datetime.now(UTC)
            self.db.commit()
            self.db.refresh(alert)
            self._schedule_broadcast(self._serialize_alert(alert))

        return alert
