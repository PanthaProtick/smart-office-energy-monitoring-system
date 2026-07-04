from datetime import UTC

from sqlalchemy.types import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator):
    """A DateTime column that is always UTC, in and out.

    SQLite has no native timezone-aware datetime type, so SQLAlchemy's
    `DateTime(timezone=True)` is a no-op there: a tz-aware value goes in,
    and a naive value comes back out on the next query, silently stripped
    of its offset. Every downstream `.isoformat()` call then produces an
    ambiguous string with no 'Z'/offset, which browsers parse as *local*
    time instead of UTC -- causing displayed times to be off by whatever
    the viewer's UTC offset is.

    This type closes that gap in one place instead of relying on every
    call site remembering to re-attach tzinfo:
      - on write: if given a tz-aware datetime, convert to UTC and store
        naive (the DB has nowhere to put an offset anyway).
      - on read: re-attach tzinfo=UTC to whatever naive value comes back.

    Every datetime that passes through a UTCDateTime column is therefore
    guaranteed to be timezone-aware UTC on the Python side, and
    `.isoformat()` on it will always include the offset.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value
