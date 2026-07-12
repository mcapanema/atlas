"""Shared time helper for domain entities (stdlib only)."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
