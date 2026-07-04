from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# The office's real-world timezone, independent of whatever timezone the
# machine running this backend happens to be set to. All "office hours"
# business logic (e.g. AlertEngine.check_devices_after_hours) should be
# evaluated against this, not against the server's local clock or a bare
# UTC hour comparison -- otherwise "8 AM - 6 PM" silently means something
# different depending on where the process happens to be deployed.
#
# Change this single constant if the office moves timezones.
OFFICE_TIMEZONE = ZoneInfo("Asia/Dhaka")  # UTC+6


def office_now() -> datetime:
    """Current time in the office's local timezone (tz-aware)."""
    return datetime.now(UTC).astimezone(OFFICE_TIMEZONE)


def to_iso(dt: datetime | None) -> str | None:
    """Serialize a datetime to an unambiguous UTC ISO 8601 string.

    Every datetime in this app is stored/produced as UTC (see
    app.database.types.UTCDateTime), so this always emits a trailing
    'Z' rather than a bare offset-less string. Browsers parse a
    'Z'-suffixed string as UTC and localize it correctly to the
    viewer's machine; an offset-less string gets silently misread as
    already being in the viewer's local timezone.

    Use this everywhere a timestamp is serialized for an API response
    or websocket broadcast, instead of calling `.isoformat()` directly.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Defensive: every column uses UTCDateTime so this shouldn't
        # happen, but if it ever does, treat naive values as UTC rather
        # than silently emitting an ambiguous string.
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
