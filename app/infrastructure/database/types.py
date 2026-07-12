"""Cross-dialect column types shared by the ORM models."""

from datetime import UTC, datetime

from sqlalchemy.engine import Dialect
from sqlalchemy.types import DateTime, TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """DateTime(timezone=True) that survives SQLite's naive round-trip.

    SQLite stores DATETIME as a naive ISO string, dropping tzinfo on read
    (Postgres's timestamptz doesn't have this problem). Domain invariants
    and API serialization need tz-aware datetimes, so reattach UTC here.
    Renders identical DDL to DateTime(timezone=True) — swapping a column
    to this type needs no migration.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
