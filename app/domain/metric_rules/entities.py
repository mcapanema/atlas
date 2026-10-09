"""Metric rules: the per-team knobs behind every computed metric.

Teams work differently (one parks work in Backlog and restarts it, another
never does), so each interpretation Atlas makes of delivery data is a rule.
Built-in defaults reproduce Atlas's original behavior; an organization's
overrides (the workspace default) layer on top, then a team's. Analytics
only ever see one resolved MetricRules.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, tzinfo
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain._time import utcnow
from app.domain.work_items.entities import OPEN_STATE_TYPES, StateType, WorkItem, WorkItemType

ReopenCompletion = Literal["last", "first"]
DoneThenCanceled = Literal["delivered", "canceled"]
LeadTimeStart = Literal["created", "triage_exit"]
DoneThenReopened = Literal["delivered", "reopened"]
CanceledThenReopened = Literal["canceled", "reopened"]
RecomputeState = Literal["idle", "running", "failed"]

HEALTH_COMPONENTS = ("predictability", "efficiency", "flow", "stability", "risk")

_FLAGS = (
    "exclude_born_done",
    "move_back_ends_wip",
    "restart_clock_after_move_back",
    "count_parent_issues",
    "blocked_label_pattern",
    "blocked_by_relations",
    "blocked_state_pattern",
)
_CHOICES: dict[str, tuple[str, ...]] = {
    "reopen_completion": ("last", "first"),
    "done_then_canceled": ("delivered", "canceled"),
    "lead_time_start": ("created", "triage_exit"),
    "done_then_reopened": ("delivered", "reopened"),
    "canceled_then_reopened": ("canceled", "reopened"),
}
MAX_LIST_RULE_ENTRIES = 50

# Built-in blocked-name match for labels and workflow states: whole words,
# where "_" separates words too. English "Blocked", "Blockers", "blocker:
# external", "Blocking", "blocked_by" and Portuguese "Bloqueado(s)/a(s)",
# "Bloqueante(s)", "Bloqueio(s)" match; "regras-blockly" (a Blockly label),
# "blocks", "unblocked" and "Desbloqueado" don't — the 2026-10-03 audit
# found a "block" substring match flagging "regras-blockly".
_BLOCKED_NAME = re.compile(
    r"(?<![a-z0-9])(?:block(?:ed|ers?|ing)?|bloque(?:ad[ao]s?|antes?|ios?))(?![a-z0-9])",
    re.IGNORECASE,
)


def _named_blocked(name: str, *, pattern: bool, listed: tuple[str, ...]) -> bool:
    """`name` matches the built-in pattern (when on) or a listed name (any case)."""
    if pattern and _BLOCKED_NAME.search(name):
        return True
    folded = name.strip().casefold()
    return any(folded == entry.strip().casefold() for entry in listed)


_INTEGERS = (
    "healthy_min",
    "warning_min",
    "predictability_floor",
    "aging_percentile",
    "aging_history_days",
    "health_min_sample",
    "daily_bucket_max_days",
    "forecast_history_days",
    "sprint_length_days",
)
_RANGES: dict[str, tuple[float, float]] = {
    "healthy_min": (1, 100),
    "warning_min": (0, 99),
    "predictability_floor": (0, 98),
    "stability_best_weeks": (0, 52),
    "stability_worst_weeks": (0.1, 52),
    "aging_percentile": (50, 99),
    "aging_history_days": (7, 365),
    "health_min_sample": (1, 50),
    **{f"weight_{name}": (0, 10) for name in HEALTH_COMPONENTS},
    "daily_bucket_max_days": (1, 90),
    "forecast_history_days": (7, 365),
    "sprint_length_days": (7, 365),
}


@dataclass(frozen=True)
class MetricRules:
    """Every per-team rule: how metrics are computed, plus meeting defaults; defaults = built-in."""

    # Lifecycle: how one item's events fold into its flow sample.
    exclude_born_done: bool = True
    move_back_ends_wip: bool = True
    restart_clock_after_move_back: bool = False
    reopen_completion: ReopenCompletion = "last"
    done_then_canceled: DoneThenCanceled = "delivered"
    count_parent_issues: bool = True
    lead_time_start: LeadTimeStart = "created"
    done_then_reopened: DoneThenReopened = "delivered"
    canceled_then_reopened: CanceledThenReopened = "canceled"
    # Blocked signal: label names and workflow-state names (each by the
    # built-in pattern and/or a list), and Linear "blocked by" relations
    # (history only — ADR-0011). Every source is on by default (ADR-0015).
    blocked_label_pattern: bool = True
    blocked_label_names: tuple[str, ...] = ()
    blocked_by_relations: bool = True
    blocked_state_pattern: bool = True
    blocked_state_names: tuple[str, ...] = ()
    # Delivery-health scoring. Calibrated on live data (review 2026-10-09):
    # flow efficiency reads 92-100% everywhere because blocked periods are
    # its only wait signal, so efficiency stays out of the built-in score
    # until queue-state waits are measured (see flow_efficiency.py).
    healthy_min: int = 70
    warning_min: int = 40
    # Predictability is the share of window completions within the service
    # level (the aging percentile of cycle times over the aging history
    # before the window, ADR-0016): at that percentile's own rate it scores
    # 100, at this share 0. Live hit rates ran 42%-100% (2026-10-09).
    predictability_floor: int = 25
    stability_best_weeks: float = 1.0
    stability_worst_weeks: float = 5.0
    aging_percentile: int = 85
    # Completed cycles the aging line (and health risk) read: the trailing
    # days, so a team's 2025 pace doesn't set its 2026 aging flags.
    aging_history_days: int = 90
    # A component backed by fewer items (window completions; in-progress
    # items for risk) is left out: one stuck item is an anecdote, not a
    # team's health.
    health_min_sample: int = 5
    weight_predictability: float = 1.0
    weight_efficiency: float = 0.0
    weight_flow: float = 1.0
    weight_stability: float = 1.0
    weight_risk: float = 1.0
    # Calendar and windows. Short windows have no weekly shape to read (a
    # 7-day window is one weekly bar), so they chart throughput per day.
    timezone: str = "UTC"
    daily_bucket_max_days: int = 21
    forecast_history_days: int = 90
    # Open state types whose items count as forecast remaining.
    remaining_state_types: tuple[StateType, ...] = OPEN_STATE_TYPES
    # Label -> work-item type, first match wins (Linear has no type field).
    type_labels: tuple[tuple[str, WorkItemType], ...] = ()
    # Meetings: a retrospective covers the team's last sprint unless a
    # window is asked for. Changes no metric (MEETING_RULES).
    sprint_length_days: int = 14

    def __post_init__(self) -> None:
        _normalize_collections(self)
        _check_types(self)
        _check_ranges(self)
        _check_order(self)
        _check_timezone(self.timezone)

    @property
    def tz(self) -> tzinfo:
        return ZoneInfo(self.timezone)

    def weight(self, component: str) -> float:
        """The health weight of `component` (one of HEALTH_COMPONENTS)."""
        return float(getattr(self, f"weight_{component}"))

    def is_blocked_label(self, name: str) -> bool:
        """Whether a label named `name` marks blocked work under these rules."""
        return _named_blocked(
            name, pattern=self.blocked_label_pattern, listed=self.blocked_label_names
        )

    def is_blocked_state(self, name: str) -> bool:
        """Whether a workflow state named `name` holds blocked work under these rules."""
        return _named_blocked(
            name, pattern=self.blocked_state_pattern, listed=self.blocked_state_names
        )

    def type_of(self, item: WorkItem) -> WorkItemType:
        """The item's type: its first type_labels hit among its labels, else its stored type.

        ponytail: labels are the item's current labels, applied to as-of
        replays too. Upgrade path: label history (LABEL_ADDED/REMOVED events).
        """
        carried = {label.strip().casefold() for label in item.labels}
        return next(
            (
                work_type
                for label, work_type in self.type_labels
                if label.strip().casefold() in carried
            ),
            item.type,
        )


def _normalize_collections(rules: MetricRules) -> None:
    """Coerce JSON-shaped collection rules (lists, {"label","type"} objects) into tuples.

    Frozen dataclass, so the canonical values are written with
    object.__setattr__. Every malformed shape raises ValueError naming the
    rule: the resolver falls back to built-ins on ValueError only.
    """
    object.__setattr__(
        rules, "blocked_label_names", _names("blocked_label_names", rules.blocked_label_names)
    )
    object.__setattr__(
        rules, "blocked_state_names", _names("blocked_state_names", rules.blocked_state_names)
    )
    object.__setattr__(rules, "remaining_state_types", _state_types(rules.remaining_state_types))
    object.__setattr__(rules, "type_labels", _type_labels(rules.type_labels))


def _entries(name: str, value: object) -> list[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise ValueError(f"{name} must be a list")
    entries = list(value)
    if len(entries) > MAX_LIST_RULE_ENTRIES:
        raise ValueError(f"{name} must have at most {MAX_LIST_RULE_ENTRIES} entries")
    return entries


def _label(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} entries must be non-empty names")
    return value.strip()


def _names(rule: str, value: object) -> tuple[str, ...]:
    return tuple(_label(rule, entry) for entry in _entries(rule, value))


def _state_types(value: object) -> tuple[StateType, ...]:
    message = "remaining_state_types must be a non-empty subset of: " + ", ".join(OPEN_STATE_TYPES)
    try:
        chosen = {StateType(str(entry)) for entry in _entries("remaining_state_types", value)}
    except (TypeError, ValueError) as exc:  # TypeError: an unhashable entry
        if "remaining_state_types" in str(exc):
            raise
        raise ValueError(message) from exc
    if not chosen or not chosen <= set(OPEN_STATE_TYPES):
        raise ValueError(message)
    return tuple(state for state in OPEN_STATE_TYPES if state in chosen)


def _type_label(entry: object) -> tuple[str, WorkItemType]:
    """One mapping row: a {"label", "type"} object (stored JSON, API) or a pair."""
    pair = (entry.get("label"), entry.get("type")) if isinstance(entry, Mapping) else entry
    if not isinstance(pair, tuple | list) or len(pair) != 2:
        raise ValueError("type_labels entries must each be a label and a work-item type")
    label = _label("type_labels", pair[0])
    try:
        return label, WorkItemType(pair[1])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"type_labels types must be one of: {', '.join(WorkItemType)}") from exc


def _type_labels(value: object) -> tuple[tuple[str, WorkItemType], ...]:
    pairs = tuple(_type_label(entry) for entry in _entries("type_labels", value))
    folded = [label.casefold() for label, _ in pairs]
    if len(set(folded)) != len(folded):
        raise ValueError("type_labels must not map the same label twice")
    return pairs


def _check_types(rules: MetricRules) -> None:
    for name in _FLAGS:
        if not isinstance(getattr(rules, name), bool):
            raise ValueError(f"{name} must be true or false")
    for name, allowed in _CHOICES.items():
        if getattr(rules, name) not in allowed:
            raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    for name in _INTEGERS:
        value = getattr(rules, name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be a whole number")


def _check_ranges(rules: MetricRules) -> None:
    for name, (low, high) in _RANGES.items():
        value = getattr(rules, name)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not low <= value <= high
        ):
            raise ValueError(f"{name} must be between {low:g} and {high:g}")


def _check_order(rules: MetricRules) -> None:
    if rules.warning_min >= rules.healthy_min:
        raise ValueError("warning_min must be below healthy_min")
    if rules.predictability_floor >= rules.aging_percentile:
        raise ValueError("predictability_floor must be below aging_percentile")
    if rules.stability_worst_weeks <= rules.stability_best_weeks:
        raise ValueError("stability_worst_weeks must be above stability_best_weeks")
    if not any(rules.weight(name) > 0 for name in HEALTH_COMPONENTS):
        raise ValueError("at least one health weight must be above 0")


def _check_timezone(name: object) -> None:
    try:
        if not isinstance(name, str):
            raise ValueError(name)
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be an IANA time zone name, e.g. America/Sao_Paulo") from exc


DEFAULT_RULES = MetricRules()
RULE_NAMES = frozenset(f.name for f in fields(MetricRules))

# Rules that only set a meeting's default window. They change no metric, so
# changing one rewrites no snapshot history and doesn't make a team's rules
# custom.
MEETING_RULES = frozenset({"sprint_length_days"})
METRIC_RULE_NAMES = RULE_NAMES - MEETING_RULES
_FLOAT_RULES = frozenset(f.name for f in fields(MetricRules) if f.type is float)


def _coerce(name: str, value: object) -> object:
    # JSON has one number type: a stored 4 must land as 4.0 in a float rule.
    if name in _FLOAT_RULES and isinstance(value, int) and not isinstance(value, bool):
        return float(value)
    return value


def apply_overrides(base: MetricRules, overrides: Mapping[str, object]) -> MetricRules:
    """`base` with each known rule in `overrides` applied and validated; unknown keys ignored."""
    known: dict[str, Any] = {
        name: _coerce(name, value) for name, value in overrides.items() if name in RULE_NAMES
    }
    return replace(base, **known)


def resolve_rules(*layers: Mapping[str, object]) -> MetricRules:
    """Built-in defaults, then each override layer in order (workspace, then team).

    The layers merge first and validate once: only the combined result has
    to hold, not each layer on its own.
    """
    merged: dict[str, object] = {}
    for layer in layers:
        merged.update(layer)
    return apply_overrides(DEFAULT_RULES, merged)


def unknown_rule_names(overrides: Mapping[str, object]) -> list[str]:
    return sorted(set(overrides) - RULE_NAMES)


@dataclass(frozen=True)
class RecomputeStatus:
    """Progress of an organization's snapshot-history rewrite after a rule change."""

    state: RecomputeState = "idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


@dataclass(frozen=True)
class RuleOverrides:
    """One layer's sparse overrides: an organization's (team_id None) or a team's.

    The organization row also carries the recompute status of its scopes'
    snapshot history (one history rewrite runs per organization at a time).
    """

    organization_id: UUID
    team_id: UUID | None = None
    overrides: Mapping[str, object] = field(default_factory=dict)
    recompute: RecomputeStatus = field(default_factory=RecomputeStatus)
    id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=utcnow)
