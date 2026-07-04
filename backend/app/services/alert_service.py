import json

from sqlalchemy.orm import Session

from app.database.models import Alert, AlertRule, AlertStatus, Device, Room
from app.services.gemini_service import get_gemini_service
from app.utils.timeutils import to_iso


class AlertService:
    """CRUD and query operations for alerts."""

    def __init__(self, db: Session):
        self.db = db

    def get_active_alerts(self, limit: int = 100):
        """Get all active alerts, most recent first."""
        return (
            self.db.query(Alert)
            .filter(Alert.status == AlertStatus.ACTIVE)
            .order_by(Alert.triggered_at.desc())
            .limit(limit)
            .all()
        )

    def get_all_alerts(self, limit: int = 100):
        """Get all alerts (active and resolved), most recent first."""
        return (
            self.db.query(Alert)
            .order_by(Alert.triggered_at.desc())
            .limit(limit)
            .all()
        )

    def get_alert(self, alert_id: int):
        """Get a single alert by ID."""
        return self.db.query(Alert).filter(Alert.id == alert_id).first()

    def serialize_alert(self, alert: Alert) -> dict:
        """Convert an Alert ORM object to a dict."""
        return {
            "id": alert.id,
            "rule": str(alert.rule.value) if hasattr(alert.rule, "value") else str(alert.rule),
            "status": str(alert.status.value) if hasattr(alert.status, "value") else str(alert.status),
            "message": alert.message,
            "triggered_at": to_iso(alert.triggered_at),
            "resolved_at": to_iso(alert.resolved_at),
            "context": alert.context,
        }

    def build_alert_data(self, alert: Alert) -> dict:
        """Assemble the structured dict GeminiService.generate_alert_message expects.

        This only *reads back* facts that AlertEngine already decided and
        recorded (the rule, its context, which room/devices are involved) --
        it never re-evaluates whether the alert condition holds. That
        decision was made once, upstream, when the alert was triggered.
        """
        context = {}
        if alert.context:
            try:
                context = json.loads(alert.context)
            except (TypeError, ValueError):
                context = {}

        room_name = None
        active_devices: list[str] = []

        room_id = context.get("room_id")
        if room_id is not None:
            room = self.db.query(Room).filter(Room.id == room_id).first()
            if room is not None:
                room_name = room.name
                active_devices = [d.name for d in room.devices if d.is_active]
        elif alert.rule == AlertRule.DEVICES_AFTER_HOURS:
            # Global rule, not tied to one room. For a still-ACTIVE alert this
            # reflects the current situation accurately (the alert only stays
            # active while at least one device remains on after hours). For an
            # already-resolved alert, this is a best-effort reconstruction --
            # nothing snapshotted the after-hours device list at trigger time.
            active_devices = [
                d.name
                for d in self.db.query(Device).filter(Device.is_active.is_(True)).all()
            ]

        alert_type = alert.rule.value if hasattr(alert.rule, "value") else str(alert.rule)

        data = {
            "alert_type": alert_type,
            "room": room_name,
            "active_devices": active_devices,
            "time": to_iso(alert.triggered_at),
            "message": alert.message,
        }
        # Merge in any other structured fields AlertEngine stored (e.g.
        # total_power for POWER_EXCEEDED), without letting them clobber the
        # keys above.
        for key, value in context.items():
            if key != "room_id":
                data.setdefault(key, value)
        return data

    def generate_ai_message(self, alert: Alert) -> str:
        """Alert Engine -> Alert Service -> Gemini Service -> NL message.

        Gemini only phrases the already-triggered alert; it plays no part in
        deciding that the alert exists.
        """
        return get_gemini_service().generate_alert_message(self.build_alert_data(alert))
