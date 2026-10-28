from uuid import uuid4

import pytest

from app.domain.people.entities import Person


def test_person_name_is_stripped_and_required() -> None:
    assert Person(organization_id=uuid4(), name="  Ada ").name == "Ada"
    with pytest.raises(ValueError, match="name"):
        Person(organization_id=uuid4(), name="  ")


def test_blank_display_name_is_none() -> None:
    assert Person(organization_id=uuid4(), name="Ada", display_name="  ").display_name is None
    assert Person(organization_id=uuid4(), name="Ada", display_name=" João ").display_name == "João"


def test_shown_name_prefers_display_name() -> None:
    org = uuid4()
    assert (
        Person(organization_id=org, name="Joao Barbosa", display_name="João Barbosa").shown_name
        == "João Barbosa"
    )
    assert Person(organization_id=org, name="Joao Barbosa").shown_name == "Joao Barbosa"
