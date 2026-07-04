from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Alert, AlertStatus, Device, Room
from app.services import energy_service
from app.services.device_service import DeviceService
from app.services.gemini_service import get_gemini_service

router = APIRouter()


def _get_status_data(db: Session) -> dict:
    rooms = db.query(Room).order_by(Room.id).all()
    devices = db.query(Device).order_by(Device.id).all()

    total_devices = len(devices)
    active_devices = sum(1 for d in devices if d.is_active)
    total_rooms = len(rooms)
    active_rooms = sum(
        1 for r in rooms if r.devices and all(d.is_active for d in r.devices)
    )

    return {
        "total_devices": total_devices,
        "active_devices": active_devices,
        "total_rooms": total_rooms,
        "active_rooms": active_rooms,
        "rooms": [
            {
                "name": r.name,
                "active_devices": sum(1 for d in r.devices if d.is_active),
                "total_devices": len(r.devices),
            }
            for r in rooms
        ],
    }


def _get_office_data(db: Session) -> dict:
    status = _get_status_data(db)
    svc = DeviceService(db)
    snapshot = energy_service.get_energy_snapshot(db)
    active_alerts = (
        db.query(Alert).filter(Alert.status == AlertStatus.ACTIVE).count()
    )
    return {
        **status,
        "total_power": svc.get_total_power(),
        "total_power_usage_wh": snapshot["total_power_usage_wh"],
        "predicted_power_usage_wh": snapshot["predicted_power_usage_wh"],
        "active_alerts": active_alerts,
    }


@router.get("/status/summary")
def get_status_summary(db: Session = Depends(get_db)):
    """Current device/room status plus a Gemini-generated natural-language summary.

    Falls back to a deterministic template if Gemini is unavailable,
    misconfigured, or errors -- this endpoint never 500s because of that.
    """
    data = _get_status_data(db)
    return {
        **data,
        "ai_summary": get_gemini_service().generate_status_summary(data),
    }


@router.get("/office/summary")
def get_office_summary(db: Session = Depends(get_db)):
    """Combined office-wide snapshot (rooms, power, alerts) plus a
    Gemini-generated natural-language analysis.

    Falls back to a deterministic template if Gemini is unavailable,
    misconfigured, or errors -- this endpoint never 500s because of that.
    """
    data = _get_office_data(db)
    return {
        **data,
        "ai_summary": get_gemini_service().generate_office_analysis(data),
    }
