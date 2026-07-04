from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import PowerLog
from app.services import energy_service
from app.services.device_service import DeviceService
from app.services.gemini_service import get_gemini_service
from app.utils.timeutils import to_iso

router = APIRouter()


def _get_power_data(db: Session) -> dict:
	svc = DeviceService(db)
	snapshot = energy_service.get_energy_snapshot(db)
	return {
		"total_power": svc.get_total_power(),
		"total_power_usage_wh": snapshot["total_power_usage_wh"],
		"predicted_power_usage_wh": snapshot["predicted_power_usage_wh"],
	}


@router.get("/power")
def get_power(db: Session = Depends(get_db)):
	svc = DeviceService(db)
	total = svc.get_total_power()
	snapshot = energy_service.get_energy_snapshot(db)
	# return last N power logs (most recent first)
	logs = (
		db.query(PowerLog)
		.order_by(PowerLog.id.desc())
		.limit(10)
		.all()
	)
	return {
		"total_power": float(total),
		"total_power_usage_wh": snapshot["total_power_usage_wh"],
		"predicted_power_usage_wh": snapshot["predicted_power_usage_wh"],
		"recent_logs": [
			{"id": l.id, "total_power": l.total_power, "timestamp": to_iso(l.timestamp)} for l in logs
		],
	}


@router.get("/power/summary")
def get_power_summary(db: Session = Depends(get_db)):
	"""Power/energy snapshot plus a Gemini-generated natural-language summary.

	Falls back to a deterministic template if Gemini is unavailable,
	misconfigured, or errors -- this endpoint never 500s because of that.
	"""
	data = _get_power_data(db)
	return {
		**data,
		"ai_summary": get_gemini_service().generate_power_summary(data),
	}

