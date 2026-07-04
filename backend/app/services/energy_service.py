"""
Cumulative energy consumption (Wh) since the backend process started, plus
a simple projected estimate for the full day.

Read this before changing the math:

- PowerLog rows are written by DeviceService.toggle_device() only when a
  device changes state, so `total_power` is a piecewise-constant STEP
  function of time, not a regularly-sampled series. Energy is the area
  under that step function: sum(power_level * duration_at_that_level).
  See get_total_energy_wh().

- The simulator (services/simulator.py) toggles a uniformly random device
  every 10s, independent of time-of-day. There is no diurnal/occupancy
  signal in this data for a regression model to learn. The theoretically
  correct long-run expectation for total power is
  (installed_capacity_w / 2): each device is a symmetric two-state Markov
  chain (its flip rate doesn't depend on its current state), which gives a
  50% stationary probability of being ON. predict_daily_wh() uses that
  fact as a stabilizing prior while the empirical sample is small (e.g.
  right after startup, when every device starts OFF and a naive average
  would be biased toward zero) instead of reaching for ML on data that
  structurally has no time-based pattern to fit.
"""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.models import Device, PowerLog

# Set once by initialize_baseline() during FastAPI's startup event.
# NOTE: process-local globals -- fine for a single-worker dev server, but
# won't be shared across multiple uvicorn workers/processes. If this ever
# runs with >1 worker, move this baseline into a table instead.
_backend_start_time: Optional[datetime] = None
_backend_start_power: Optional[float] = None


def _get_current_total_power_w(db: Session) -> float:
    """Sum of power_rating for currently-active devices.

    Deliberately duplicated from DeviceService.get_total_power() rather than
    imported, to avoid a circular import (device_service will import this
    module to broadcast energy updates on toggle). Worth collapsing into one
    shared helper later.
    """
    total = (
        db.query(func.coalesce(func.sum(Device.power_rating), 0.0))
        .filter(Device.is_active.is_(True))
        .scalar()
    )
    return float(total or 0.0)


def initialize_baseline(db: Session) -> None:
    """Record the t0 boundary (time + power) for energy integration.

    Must be called once during app startup, before any request or the
    simulator can toggle a device -- otherwise get_total_energy_wh() has no
    starting point to integrate from.
    """
    global _backend_start_time, _backend_start_power
    _backend_start_time = datetime.now(UTC)
    _backend_start_power = _get_current_total_power_w(db)


def get_installed_capacity_w(db: Session) -> float:
    """Sum of power_rating across ALL devices, active or not."""
    total = db.query(func.coalesce(func.sum(Device.power_rating), 0.0)).scalar()
    return float(total or 0.0)


def get_total_energy_wh(db: Session) -> float:
    """Integrate the total_power step function from backend start to now (Wh)."""
    if _backend_start_time is None or _backend_start_power is None:
        # Fail loudly rather than silently returning 0 -- a silent 0 would
        # look like a real (very low) reading instead of a wiring bug.
        raise RuntimeError(
            "energy_service.initialize_baseline() was never called at startup"
        )

    logs = (
        db.query(PowerLog)
        .filter(PowerLog.timestamp >= _backend_start_time)
        .order_by(PowerLog.timestamp.asc())
        .all()
    )

    points = [(_backend_start_time, _backend_start_power)]
    points += [(log.timestamp, log.total_power) for log in logs]
    points.append((datetime.now(UTC), points[-1][1]))  # close out final interval

    energy_wh = 0.0
    for (t0, p0), (t1, _p1) in zip(points, points[1:]):
        hours = (t1 - t0).total_seconds() / 3600
        energy_wh += p0 * hours
    return energy_wh


def predict_daily_wh(db: Session, total_energy_wh: float) -> float:
    """
    Project the full day's total (Wh) with plain math, not ML -- see module
    docstring for why a regression model has nothing real to fit here.

    Blends two estimators:
      - empirical_rate: total_energy_wh so far / hours elapsed. This is the
        statistically correct estimator IF the remaining hours behave like
        the elapsed ones -- true here, since toggles don't depend on time.
      - analytical_rate: installed_capacity_w / 2, the closed-form
        steady-state expectation, used to stabilize the estimate early on
        (empirical_rate is biased toward 0 right after startup, when every
        device begins OFF).

    Blend weight ramps linearly from analytical -> empirical over 4 hours.
    This 4-hour constant is a judgment call, not derived -- tune it if your
    toggle rate or device count changes a lot.
    """
    if _backend_start_time is None:
        raise RuntimeError(
            "energy_service.initialize_baseline() was never called at startup"
        )

    elapsed_hours = (datetime.now(UTC) - _backend_start_time).total_seconds() / 3600
    installed_capacity_w = get_installed_capacity_w(db)
    analytical_rate_w = installed_capacity_w / 2

    if elapsed_hours <= 0:
        return analytical_rate_w * 24

    empirical_rate_w = total_energy_wh / elapsed_hours
    weight = min(elapsed_hours / 4, 1.0)
    blended_rate_w = weight * empirical_rate_w + (1 - weight) * analytical_rate_w
    return blended_rate_w * 24


def get_energy_snapshot(db: Session) -> dict:
    """Convenience bundle used by both the broadcast hook and the REST endpoint."""
    total_energy_wh = get_total_energy_wh(db)
    predicted_daily_wh = predict_daily_wh(db, total_energy_wh)
    elapsed_hours = (datetime.now(UTC) - _backend_start_time).total_seconds() / 3600
    return {
        "total_power_usage_wh": round(total_energy_wh, 2),
        "predicted_power_usage_wh": round(predicted_daily_wh, 2),
        "elapsed_hours": round(elapsed_hours, 3),
        "timestamp": datetime.now(UTC),
    }
