from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import PowerLog
from app.services import energy_service
from app.services.device_service import DeviceService
from app.utils.timeutils import to_iso

router = APIRouter()


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

