from datetime import UTC, datetime

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

    def check_power_exceeded(self, current_total_power: float) -> bool:
        """Event rule: Total power exceeded threshold."""
        return current_total_power > self.POWER_THRESHOLD

    def check_room_completely_active(self, room_id: int) -> bool:
        """Event rule: All devices in a room are active."""
        room = self.db.query(Room).filter(Room.id == room_id).first()
        if not room:
            return False
        devices = self.db.query(Device).filter(Device.room_id == room_id).all()
        if not devices:
            return False
        return all(d.is_active for d in devices)

    def check_devices_after_hours(self) -> bool:
        """Time rule: Any devices are active outside office hours (8 AM - 6 PM)."""
        now = datetime.now(UTC)
        hour = now.hour

        # If outside office hours and any device is active, trigger alert
        if hour < self.AFTER_HOURS_END or hour >= self.AFTER_HOURS_START:
            active_devices = self.db.query(Device).filter(Device.is_active.is_(True)).count()
            return active_devices > 0
        return False

    def check_high_power_sustained(self, current_total_power: float) -> bool:
        """Time rule: High power (>150W) has been sustained for 5+ minutes."""
        # This would require querying PowerLog history
        # For simplicity, we'll check if current power is high and there are recent sustained readings
        if current_total_power < self.SUSTAINED_POWER_THRESHOLD:
            return False

        # Check if power has been sustained for at least 5 minutes
        from app.database.models import PowerLog

        five_min_ago = datetime.now(UTC)
        # For MVP, we'll just check if there are multiple high power readings in last 5 min
        recent_logs = (
            self.db.query(PowerLog)
            .filter(PowerLog.timestamp >= five_min_ago)
            .all()
        )

        if len(recent_logs) < 3:  # rough heuristic: at least 3 readings in 5 min
            return False

        return all(log.total_power >= self.SUSTAINED_POWER_THRESHOLD for log in recent_logs)

    def trigger_alert(self, rule: AlertRule, message: str, metadata: str = None) -> Alert:
        """Create a new active alert if no duplicate exists."""
        # Check if there's already an active alert for this rule
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
            context=metadata,
        )
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert

    def resolve_alert(self, rule: AlertRule) -> Alert:
        """Mark all active alerts of a rule as resolved."""
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

        return alert

    def check_and_resolve_power_exceeded(self, current_total_power: float):
        """Resolve power_exceeded if power drops below threshold."""
        if not self.check_power_exceeded(current_total_power):
            self.resolve_alert(AlertRule.POWER_EXCEEDED)

    def check_and_resolve_room_active(self, room_id: int):
        """Resolve room_completely_active if not all devices are active."""
        if not self.check_room_completely_active(room_id):
            alert = (
                self.db.query(Alert)
                .filter(
                    Alert.rule == AlertRule.ROOM_COMPLETELY_ACTIVE,
                    Alert.status == AlertStatus.ACTIVE,
                )
                .first()
            )
            if alert:
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = datetime.now(UTC)
                self.db.commit()
