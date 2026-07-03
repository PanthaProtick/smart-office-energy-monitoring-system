from fastapi import APIRouter, Depends
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
