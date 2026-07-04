from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.services.alert_service import AlertService

router = APIRouter()


@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db)):
    svc = AlertService(db)
    alerts = svc.get_active_alerts(limit=100)
    return [svc.serialize_alert(a) for a in alerts]


@router.get("/alerts/history")
def get_alerts_history(db: Session = Depends(get_db)):
    svc = AlertService(db)
    alerts = svc.get_all_alerts(limit=100)
    return [svc.serialize_alert(a) for a in alerts]


@router.get("/alerts/{alert_id}/summary")
def get_alert_summary(alert_id: int, db: Session = Depends(get_db)):
    """Alert data plus a Gemini-generated natural-language summary.

    Falls back to a deterministic template (see GeminiService) if Gemini is
    unavailable, misconfigured, or errors -- this endpoint never 500s because
    of that.
    """
    svc = AlertService(db)
    alert = svc.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {
        **svc.serialize_alert(alert),
        "ai_summary": svc.generate_ai_message(alert),
    }
