import pytest

from app.domain.metric_rules.entities import DEFAULT_RULES, apply_overrides


def test_sprint_length_defaults_to_two_weeks() -> None:
    assert DEFAULT_RULES.sprint_length_days == 14


def test_a_team_can_run_one_week_sprints() -> None:
    assert apply_overrides(DEFAULT_RULES, {"sprint_length_days": 7}).sprint_length_days == 7


@pytest.mark.parametrize("value", [6, 366, 10.5, True])
def test_sprint_length_is_a_whole_number_from_7_to_365(value: object) -> None:
    with pytest.raises(ValueError, match="sprint_length_days"):
        apply_overrides(DEFAULT_RULES, {"sprint_length_days": value})
