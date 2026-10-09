from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.domain.metric_rules.entities import (
    DEFAULT_RULES,
    MetricRules,
    RecomputeStatus,
    RuleOverrides,
    apply_overrides,
    resolve_rules,
    unknown_rule_names,
)


def test_defaults_reproduce_the_built_in_behavior() -> None:
    rules = DEFAULT_RULES

    assert rules == MetricRules()
    assert (rules.exclude_born_done, rules.move_back_ends_wip) == (True, True)
    assert rules.restart_clock_after_move_back is False
    assert (rules.reopen_completion, rules.done_then_canceled) == ("last", "delivered")
    assert (rules.healthy_min, rules.warning_min) == (70, 40)
    # Calibrated on live data (2026-10-09): service-level hit rates ran 42%-100%.
    assert rules.predictability_floor == 25
    # Efficiency reads 92-100% everywhere until queue-state waits exist.
    assert rules.weight_efficiency == 0.0
    assert (rules.stability_best_weeks, rules.stability_worst_weeks) == (1.0, 5.0)
    assert rules.aging_percentile == 85
    assert rules.timezone == "UTC"
    assert (rules.daily_bucket_max_days, rules.forecast_history_days) == (21, 90)


def test_team_layer_beats_workspace_layer_beats_built_in() -> None:
    rules = resolve_rules(
        {"aging_percentile": 90, "timezone": "America/Sao_Paulo"}, {"aging_percentile": 75}
    )

    assert rules.aging_percentile == 75
    assert rules.timezone == "America/Sao_Paulo"
    assert rules.healthy_min == 70


def test_layers_validate_together_not_one_by_one() -> None:
    # warning 75 alone breaks warning < healthy (70); the team's healthy 90 repairs it.
    rules = resolve_rules({"warning_min": 75}, {"healthy_min": 90})

    assert (rules.warning_min, rules.healthy_min) == (75, 90)


def test_json_integers_land_as_floats_in_float_rules() -> None:
    rules = apply_overrides(DEFAULT_RULES, {"stability_best_weeks": 2})

    assert rules.stability_best_weeks == 2.0
    assert isinstance(rules.stability_best_weeks, float)


def test_the_retired_worst_ratio_override_is_ignored() -> None:
    # Review focus 5: an install that tuned the old spread scale keeps working.
    overrides = {"predictability_worst_ratio": 3}

    assert apply_overrides(DEFAULT_RULES, overrides) == DEFAULT_RULES
    assert unknown_rule_names(overrides) == ["predictability_worst_ratio"]


def test_unknown_keys_are_ignored_and_reported() -> None:
    overrides = {"aging_percentile": 80, "renamed_rule": True}

    assert apply_overrides(DEFAULT_RULES, overrides).aging_percentile == 80
    assert unknown_rule_names(overrides) == ["renamed_rule"]


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"healthy_min": 0}, "healthy_min"),
        ({"warning_min": 70}, "warning_min must be below healthy_min"),
        ({"stability_worst_weeks": 1.0}, "stability_worst_weeks"),
        ({"predictability_floor": 99}, "predictability_floor"),
        ({"predictability_floor": 85}, "predictability_floor must be below aging_percentile"),
        ({"aging_percentile": 40}, "aging_percentile"),
        ({"daily_bucket_max_days": 0}, "daily_bucket_max_days"),
        ({"forecast_history_days": 3}, "forecast_history_days"),
        (
            {
                "weight_predictability": 0,
                "weight_efficiency": 0,
                "weight_flow": 0,
                "weight_stability": 0,
                "weight_risk": 0,
            },
            "at least one health weight",
        ),
        ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
        ({"timezone": 3}, "timezone"),
        ({"stability_best_weeks": -1}, "stability_best_weeks"),
        ({"stability_best_weeks": 53}, "stability_best_weeks"),
        ({"stability_worst_weeks": 53}, "stability_worst_weeks"),
        ({"weight_flow": -1}, "weight_flow"),
        ({"weight_risk": 11}, "weight_risk"),
        ({"reopen_completion": "middle"}, "reopen_completion"),
        ({"exclude_born_done": "yes"}, "exclude_born_done"),
        ({"healthy_min": 80.5}, "healthy_min"),
    ],
)
def test_invalid_rules_are_rejected_naming_the_rule(
    overrides: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        resolve_rules(overrides)


def test_a_non_string_timezone_is_rejected_even_if_it_prints_as_a_zone() -> None:
    class PrintsAsUtc:
        def __str__(self) -> str:
            return "UTC"

    with pytest.raises(ValueError, match="timezone"):
        MetricRules(timezone=PrintsAsUtc())  # type: ignore[arg-type]  # the point: bad type


def test_tz_is_the_named_zone() -> None:
    assert resolve_rules({"timezone": "America/Sao_Paulo"}).tz == ZoneInfo("America/Sao_Paulo")


def test_weight_reads_the_component_weight() -> None:
    assert resolve_rules({"weight_flow": 2.5}).weight("flow") == 2.5


def test_overrides_row_defaults_to_an_idle_recompute() -> None:
    row = RuleOverrides(organization_id=uuid4())

    assert row.team_id is None
    assert row.overrides == {}
    assert row.recompute == RecomputeStatus()
    assert row.recompute.state == "idle"
