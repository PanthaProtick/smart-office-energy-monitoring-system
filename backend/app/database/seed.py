from datetime import UTC, datetime
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from app.database.database import SessionLocal
from app.database.models import Device, DeviceType, Room


def create_device(room, name, device_type, power):
    return Device(
        room_id=room.id,
        name=name,
        type=device_type,
        power_rating=power,
        is_active=False,
        last_updated=datetime.now(UTC),
    )


def seed_db():
    db = SessionLocal()
    try:
        existing_room = db.query(Room).first()
        if existing_room:
            print("Database already seeded.")
            return

        drawing_room = Room(name="Drawing Room", device_count=5)
        work_room_1 = Room(name="Work Room 1", device_count=5)
        work_room_2 = Room(name="Work Room 2", device_count=5)

        db.add_all([drawing_room, work_room_1, work_room_2])
        db.commit()

        db.refresh(drawing_room)
        db.refresh(work_room_1)
        db.refresh(work_room_2)

        devices = [
            create_device(drawing_room, "Light 1", DeviceType.LIGHT, 20),
            create_device(drawing_room, "Light 2", DeviceType.LIGHT, 20),
            create_device(drawing_room, "Light 3", DeviceType.LIGHT, 20),
            create_device(drawing_room, "Fan 1", DeviceType.FAN, 75),
            create_device(drawing_room, "Fan 2", DeviceType.FAN, 75),
            create_device(work_room_1, "Light 1", DeviceType.LIGHT, 20),
            create_device(work_room_1, "Light 2", DeviceType.LIGHT, 20),
            create_device(work_room_1, "Light 3", DeviceType.LIGHT, 20),
            create_device(work_room_1, "Fan 1", DeviceType.FAN, 75),
            create_device(work_room_1, "Fan 2", DeviceType.FAN, 75),
            create_device(work_room_2, "Light 1", DeviceType.LIGHT, 20),
            create_device(work_room_2, "Light 2", DeviceType.LIGHT, 20),
            create_device(work_room_2, "Light 3", DeviceType.LIGHT, 20),
            create_device(work_room_2, "Fan 1", DeviceType.FAN, 75),
            create_device(work_room_2, "Fan 2", DeviceType.FAN, 75),
        ]

        db.add_all(devices)
        db.commit()
        print("Database seeded successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_db()