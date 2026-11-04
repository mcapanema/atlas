from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.domain.incidents.entities import ServiceIncident

T = datetime(2026, 10, 1, 12, tzinfo=UTC)
NAIVE = datetime(2026, 10, 1)  # noqa: DTZ001 — naive on purpose


def test_restored_before_opened_is_rejected() -> None:
    with pytest.raises(ValueError, match="restored_at must not be before opened_at"):
        ServiceIncident(
            organization_id=uuid4(),
            external_id="i1",
            title="Down",
            opened_at=T,
            restored_at=datetime(2026, 10, 1, 11, tzinfo=UTC),
        )


def test_naive_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="opened_at must be timezone-aware"):
        ServiceIncident(organization_id=uuid4(), external_id="i1", title="Down", opened_at=NAIVE)


def test_an_open_incident_is_valid() -> None:
    incident = ServiceIncident(organization_id=uuid4(), external_id="i1", title="Down", opened_at=T)
    assert incident.restored_at is None
    assert incident.services == ()
