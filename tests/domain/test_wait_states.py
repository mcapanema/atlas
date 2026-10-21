import pytest

from app.domain.metric_rules.entities import DEFAULT_RULES, resolve_rules


def test_no_wait_states_by_default() -> None:
    assert DEFAULT_RULES.wait_state_names == ()
    assert not DEFAULT_RULES.is_wait_state("In Review")


def test_listed_wait_states_match_by_whole_name_in_any_case() -> None:
    rules = resolve_rules({"wait_state_names": [" in review ", "Waiting for Deploy"]})

    assert rules.wait_state_names == ("in review", "Waiting for Deploy")
    assert rules.is_wait_state("In Review")
    assert rules.is_wait_state("waiting for deploy")
    assert not rules.is_wait_state("In Progress")
    assert not rules.is_wait_state("In Review 2")


@pytest.mark.parametrize("value", ["In Review", [""]])
def test_invalid_wait_state_names_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="wait_state_names"):
        resolve_rules({"wait_state_names": value})
