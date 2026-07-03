import asyncio
import random
from typing import Optional

from app.database.database import SessionLocal
from app.services.device_service import DeviceService
from app.services.websocket_manager import manager


class DeviceSimulator:
    def __init__(self):
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the simulator background loop."""
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the simulator background loop."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        """Main simulator loop: every 2 seconds, toggle a random device."""
        while self.running:
            try:
                await asyncio.sleep(10)  # Wait for 10 seconds before toggling a device

                # Get a session and pick a random device
                db = SessionLocal()
                try:
                    svc = DeviceService(db)
                    devices = svc.get_all_devices()
                    if not devices:
                        continue

                    # Pick a random device and toggle it
                    device = random.choice(devices)
                    toggled_device = svc.toggle_device(device.id)

                    # Broadcast the device update
                    await manager.broadcast(
                        "device_updated",
                        {
                            "id": toggled_device.id,
                            "name": toggled_device.name,
                            "is_active": toggled_device.is_active,
                            "power_rating": toggled_device.power_rating,
                            "last_updated": toggled_device.last_updated.isoformat(),
                        },
                    )

                    # Broadcast the power update
                    total_power = svc.get_total_power()
                    await manager.broadcast(
                        "power_updated",
                        {"total_power": total_power},
                    )
                finally:
                    db.close()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Simulator error: {e}")
                await asyncio.sleep(1)


# Global simulator instance
simulator = DeviceSimulator()
