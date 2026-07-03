from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import PowerLog
from app.services.device_service import DeviceService

router = APIRouter()


@router.get("/power")
def get_power(db: Session = Depends(get_db)):
	svc = DeviceService(db)
	total = svc.get_total_power()
	# return last N power logs (most recent first)
	logs = (
		db.query(PowerLog)
		.order_by(PowerLog.id.desc())
		.limit(10)
		.all()
	)
	return {
		"total_power": float(total),
		"recent_logs": [
			{"id": l.id, "total_power": l.total_power, "timestamp": l.timestamp.isoformat()} for l in logs
		],
	}

