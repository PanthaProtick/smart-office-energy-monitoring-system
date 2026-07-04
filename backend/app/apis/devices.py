from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.database.models import Room, Device
from app.services.device_service import DeviceService
from app.utils.timeutils import to_iso

router = APIRouter()


def _serialize_device(device: Device) -> dict:
	return {
		"id": device.id,
		"room_id": device.room_id,
		"name": device.name,
		"type": str(device.type.value) if hasattr(device.type, 'value') else str(device.type),
		"power_rating": device.power_rating,
		"is_active": bool(device.is_active),
		"last_updated": to_iso(device.last_updated),
	}


@router.get("/devices")
def get_devices(db: Session = Depends(get_db)):
	svc = DeviceService(db)
	devices = svc.get_all_devices()
	return [_serialize_device(d) for d in devices]


@router.get("/devices/{device_id}")
def get_device(device_id: int, db: Session = Depends(get_db)):
	svc = DeviceService(db)
	device = svc.get_device(device_id)
	if not device:
		raise HTTPException(status_code=404, detail="Device not found")
	return _serialize_device(device)


@router.post("/devices/{device_id}/toggle")
def post_toggle_device(device_id: int, db: Session = Depends(get_db)):
	svc = DeviceService(db)
	try:
		device = svc.toggle_device(device_id)
	except ValueError:
		raise HTTPException(status_code=404, detail="Device not found")
	return _serialize_device(device)


@router.get("/rooms")
def get_rooms(db: Session = Depends(get_db)):
	rooms = db.query(Room).order_by(Room.id).all()
	return [{"id": r.id, "name": r.name, "device_count": r.device_count} for r in rooms]

