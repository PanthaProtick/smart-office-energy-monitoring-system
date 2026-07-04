import asyncio
from datetime import UTC, datetime

from app.database.database import SessionLocal
from app.services.alert_engine import AlertEngine
from app.database.models import AlertRule, Room


class AlertScheduler:
    """Background task scheduler for time-based alert rules (runs every 5 minutes)."""

    def __init__(self):
        self.running = False
        self.task = None

    async def start(self):
        """Start the alert scheduler background loop."""
        if self.running:
            return
        self.running = True
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        """Stop the alert scheduler background loop."""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def _loop(self):
        """Main loop: every 5 minutes, check time-based alert rules."""
        while self.running:
            try:
                await asyncio.sleep(300)  # 5 minutes

                db = SessionLocal()
                try:
                    engine = AlertEngine(db)

                    # Rule 2: room fully active for 2+ hours. Room.all_active_since
                    # is kept up to date by DeviceService on every device toggle;
                    # here we just check whether the threshold has been crossed.
                    rooms = (
                        db.query(Room)
                        .filter(Room.all_active_since.isnot(None))
                        .all()
                    )
                    for room in rooms:
                        if engine.check_room_active_duration(room):
                            hours = engine.ROOM_ACTIVE_DURATION_THRESHOLD.total_seconds() / 3600
                            engine.trigger_alert(
                                AlertRule.ROOM_COMPLETELY_ACTIVE,
                                f"All devices in room '{room.name}' have been active "
                                f"for over {hours:g} hours",
                                metadata={"room_id": room.id},
                                room_id=room.id,
                            )
                        else:
                            engine.resolve_alert(AlertRule.ROOM_COMPLETELY_ACTIVE, room_id=room.id)

                    # Check high power sustained
                    # Get total power from most recent PowerLog
                    from app.database.models import PowerLog
                    recent_log = (
                        db.query(PowerLog)
                        .order_by(PowerLog.id.desc())
                        .first()
                    )
                    if recent_log:
                        if engine.check_high_power_sustained(recent_log.total_power):
                            engine.trigger_alert(
                                AlertRule.HIGH_POWER_SUSTAINED,
                                f"High power sustained (>{engine.SUSTAINED_POWER_THRESHOLD}W for 5+ min): {recent_log.total_power:.1f}W",
                            )
                        else:
                            engine.resolve_alert(AlertRule.HIGH_POWER_SUSTAINED)

                finally:
                    db.close()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Alert scheduler error: {e}")
                await asyncio.sleep(10)


# Global scheduler instance
scheduler = AlertScheduler()
