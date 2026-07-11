from datetime import UTC

from app.domain._time import utcnow


def test_utcnow_is_timezone_aware_utc() -> None:
    assert utcnow().tzinfo is UTC
