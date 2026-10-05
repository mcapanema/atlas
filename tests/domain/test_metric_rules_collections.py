from uuid import uuid4

import pytest

from app.domain.metric_rules.entities import (
    DEFAULT_RULES,
    MetricRules,
    resolve_rules,
)
from app.domain.work_items.entities import OPEN_STATE_TYPES, StateType, WorkItem, WorkItemType


def _item(*labels: str) -> WorkItem:
    return WorkItem(team_id=uuid4(), title="Item", labels=labels)


def test_new_rule_defaults_reproduce_todays_behavior() -> None:
    assert DEFAULT_RULES.count_parent_issues is True
    assert DEFAULT_RULES.lead_time_start == "created"
    assert DEFAULT_RULES.done_then_reopened == "delivered"
    assert DEFAULT_RULES.canceled_then_reopened == "canceled"
    assert DEFAULT_RULES.blocked_label_pattern is True
    assert DEFAULT_RULES.blocked_label_names == ()
    assert DEFAULT_RULES.blocked_by_relations is False
    assert DEFAULT_RULES.remaining_state_types == OPEN_STATE_TYPES
    assert DEFAULT_RULES.type_labels == ()


def test_json_shaped_collections_normalize_to_tuples() -> None:
    rules = resolve_rules(
        {
            "blocked_label_names": [" On hold ", "Waiting"],
            "remaining_state_types": ["started", "unstarted"],
            "type_labels": [{"label": "Bug", "type": "bug"}, ["Feature", "story"]],
        }
    )

    assert rules.blocked_label_names == ("On hold", "Waiting")
    # canonical workflow order, so equal sets compare equal
    assert rules.remaining_state_types == (StateType.UNSTARTED, StateType.STARTED)
    assert rules.type_labels == (("Bug", WorkItemType.BUG), ("Feature", WorkItemType.STORY))


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"blocked_label_names": [""]}, "blocked_label_names"),
        ({"blocked_label_names": ["x"] * 51}, "blocked_label_names"),
        ({"remaining_state_types": []}, "remaining_state_types"),
        ({"remaining_state_types": ["completed"]}, "remaining_state_types"),
        ({"type_labels": [{"label": "Bug", "type": "epic"}]}, "type_labels"),
        (
            {"type_labels": [{"label": "Bug", "type": "bug"}, {"label": "bug", "type": "task"}]},
            "type_labels",
        ),
        ({"lead_time_start": "started"}, "lead_time_start"),
        ({"done_then_reopened": "maybe"}, "done_then_reopened"),
        ({"canceled_then_reopened": "maybe"}, "canceled_then_reopened"),
        ({"blocked_by_relations": "yes"}, "blocked_by_relations"),
    ],
)
def test_invalid_new_rules_name_the_field(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(ValueError, match=field):
        resolve_rules(overrides)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"type_labels": [{"label": "Bug"}]}, "type_labels"),
        ({"type_labels": [["Bug"]]}, "type_labels"),
        ({"type_labels": "Bug"}, "type_labels"),
        ({"remaining_state_types": [{}]}, "remaining_state_types"),
        ({"blocked_label_names": "Blocked"}, "blocked_label_names"),
        ({"blocked_label_names": [3]}, "blocked_label_names"),
    ],
)
def test_malformed_collection_json_is_a_value_error(
    overrides: dict[str, object], field: str
) -> None:
    # Review focus 2: the resolver only falls back on ValueError.
    with pytest.raises(ValueError, match=field):
        resolve_rules(overrides)


def test_builtin_pattern_matches_whole_words_only() -> None:
    blocked = ["Blocked", "blocker: external", "Blocking", "block", "blocked_by", "Blockers"]
    not_blocked = ["regras-blockly", "unblock-me-later", "blocks", "unblocked", "bug"]

    assert all(DEFAULT_RULES.is_blocked_label(name) for name in blocked)
    assert not any(DEFAULT_RULES.is_blocked_label(name) for name in not_blocked)


def test_listed_names_count_and_pattern_can_be_turned_off() -> None:
    rules = MetricRules(blocked_label_pattern=False, blocked_label_names=("On hold",))

    assert rules.is_blocked_label("On hold")
    assert not rules.is_blocked_label("Blocked")


def test_label_matching_ignores_case_and_surrounding_whitespace() -> None:
    # Review focus 3.
    rules = MetricRules(
        blocked_label_names=("waiting on vendor ",),
        type_labels=(("bug", WorkItemType.BUG),),
    )

    assert rules.is_blocked_label("Waiting on Vendor")
    assert rules.type_of(_item(" Bug")) is WorkItemType.BUG


def test_type_of_takes_the_first_mapped_label_else_the_stored_type() -> None:
    rules = MetricRules(type_labels=(("Bug", WorkItemType.BUG), ("Feature", WorkItemType.STORY)))

    assert rules.type_of(_item("Feature", "Bug")) is WorkItemType.BUG
    assert rules.type_of(_item("Feature")) is WorkItemType.STORY
    assert rules.type_of(_item("Chore")) is WorkItemType.TASK
    assert DEFAULT_RULES.type_of(_item("Bug")) is WorkItemType.TASK
