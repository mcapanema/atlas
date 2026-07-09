from datetime import UTC
from uuid import UUID, uuid4

import pytest

from app.domain.projects.entities import Project


def test_project_has_id_and_created_at() -> None:
    project = Project(team_id=uuid4(), name="Checkout")

    assert isinstance(project.id, UUID)
    assert project.created_at.tzinfo == UTC


def test_project_strips_name() -> None:
    project = Project(team_id=uuid4(), name="  Checkout  ")

    assert project.name == "Checkout"


def test_project_rejects_empty_name() -> None:
    with pytest.raises(ValueError, match="Project name must not be empty"):
        Project(team_id=uuid4(), name="   ")
