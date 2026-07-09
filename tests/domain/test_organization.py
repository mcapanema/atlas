from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.organizations.entities import Organization


def test_organization_has_generated_id_and_timestamp() -> None:
    org = Organization(name="Acme")

    assert isinstance(org.id, UUID)
    assert org.created_at.tzinfo is UTC
    assert org.created_at <= datetime.now(UTC)


def test_organization_strips_name() -> None:
    org = Organization(name="  Acme  ")

    assert org.name == "Acme"


@pytest.mark.parametrize("bad_name", ["", "   "])
def test_organization_rejects_empty_name(bad_name: str) -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        Organization(name=bad_name)
