"""Shared time helpers for domain entities (stdlib only)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def require_aware(owner: str, **values: datetime | None) -> None:
    """Raise ValueError naming `owner.field` for any datetime that is naive."""
    for name, value in values.items():
        if value is not None and value.tzinfo is None:
            raise ValueError(f"{owner}.{name} must be timezone-aware")
