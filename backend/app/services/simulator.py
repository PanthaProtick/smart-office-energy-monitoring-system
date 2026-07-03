import asyncio
import random
from typing import Optional

from app.database.database import SessionLocal
from app.services.device_service import DeviceService


class DeviceSimulator:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        while self.running:
            try:
                await asyncio.sleep(10)

                db = SessionLocal()
                try:
                    svc = DeviceService(db)
                    devices = svc.get_all_devices()
                    if not devices:
                        continue

                    device = random.choice(devices)
                    svc.toggle_device(device.id)
                finally:
                    db.close()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Simulator error: {e}")
                await asyncio.sleep(1)


simulator = DeviceSimulator()
