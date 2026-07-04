from sqlalchemy.orm import Session

from app.database.models import Alert, AlertStatus
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
