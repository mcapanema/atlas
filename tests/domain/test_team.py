from datetime import UTC
from uuid import UUID, uuid4

import pytest

from app.domain.teams.entities import Team


def test_team_has_id_and_created_at() -> None:
    team = Team(organization_id=uuid4(), name="Platform")

    assert isinstance(team.id, UUID)
    assert team.created_at.tzinfo == UTC


def test_team_strips_name() -> None:
    team = Team(organization_id=uuid4(), name="  Platform  ")

    assert team.name == "Platform"


def test_team_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Team name must not be empty"):
        Team(organization_id=uuid4(), name="   ")


def test_team_keeps_optional_external_id() -> None:
    team = Team(organization_id=uuid4(), name="Platform", external_id="lin_team_1")

    assert team.external_id == "lin_team_1"
