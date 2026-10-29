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
from datetime import date, datetime, time, tzinfo
from functools import cached_property
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain._time import utcnow
from app.domain.metric_rules.calendar import WorkCalendar
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
MAX_HOLIDAYS = 500
_HOLIDAYS_MESSAGE = "holidays must be a list of dates, e.g. 2026-12-25"
_TRACKED_SINCE_MESSAGE = "tracked_since must be a date, e.g. 2026-08-20"
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WEEKDAYS_MESSAGE = (
    "working_days must be a non-empty list of ISO weekdays (1 = Monday … 7 = Sunday)"
)

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


def _named(name: str, *, pattern: bool, listed: tuple[str, ...]) -> bool:
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
    # Wait signal: workflow-state names (exact, any case) where work waits
    # rather than progresses, e.g. In Review or Waiting for Deploy. Their
    # in-cycle time counts as wait in flow efficiency and queue/touch time;
    # blocked time is unchanged. None by default (ADR-0018).
    wait_state_names: tuple[str, ...] = ()
    # Incident signal: label names (exact, any case) that mark an item as an
    # incident for DORA's change failure rate and time to restore.
    # ponytail: an ordinary rule, so a change marks the team's rules custom and
    # queues the snapshot recompute, which rewrites identical snapshots
    # (DORA is not snapshotted). Upgrade path: a non-snapshot rule set beside
    # MEETING_RULES.
    incident_label_names: tuple[str, ...] = ("incident", "incidente")
    # Delivery-health scoring. Calibrated on live data (review 2026-10-09):
    # flow efficiency read 92-100% everywhere with blocked periods as its
    # only wait signal. Wait states (ADR-0018) are a per-team list, empty by
    # default, so efficiency stays out of the built-in score until enough
    # teams list theirs to recalibrate it.
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
    # Predictability's service level reads the same span, ending where its
    # window starts (ADR-0016).
    aging_history_days: int = 90
    # A component backed by fewer items (window completions, and for
    # predictability also the completions before the window; in-progress
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
    # ISO weekdays (1 = Monday ... 7 = Sunday) that count as working time:
    # duration metrics skip the other days.
    working_days: tuple[int, ...] = (1, 2, 3, 4, 5)
    # Whole local days off on top of the non-working weekdays.
    holidays: tuple[date, ...] = ()
    daily_bucket_max_days: int = 21
    forecast_history_days: int = 90
    # When this team began tracking its work here. Older items (moved in from
    # another team) don't stretch its history; unset, the start is estimated
    # (observed_history_days).
    tracked_since: date | None = None
    # Open state types whose items count as forecast remaining.
    remaining_state_types: tuple[StateType, ...] = OPEN_STATE_TYPES
    # Label -> work-item type, first match wins (Linear has no type field).
    type_labels: tuple[tuple[str, WorkItemType], ...] = ()
    # Meetings: a retrospective covers the team's last sprint unless a
    # window is asked for. Changes no metric (MEETING_RULES).
    sprint_length_days: int = 14

    def __post_init__(self) -> None:
        _normalize_collections(self)
        object.__setattr__(self, "tracked_since", _tracked_since(self.tracked_since))
        _check_types(self)
        _check_ranges(self)
        _check_order(self)
        _check_timezone(self.timezone)

    @property
    def tz(self) -> tzinfo:
        return ZoneInfo(self.timezone)

    @cached_property
    def work_calendar(self) -> WorkCalendar:
        return WorkCalendar(frozenset(self.working_days), self.timezone, self.holidays)

    @property
    def tracked_since_at(self) -> datetime | None:
        """The start of tracked_since on the team's calendar."""
        if self.tracked_since is None:
            return None
        return datetime.combine(self.tracked_since, time(), tzinfo=self.tz)

    def weight(self, component: str) -> float:
        """The health weight of `component` (one of HEALTH_COMPONENTS)."""
        return float(getattr(self, f"weight_{component}"))

    def is_blocked_label(self, name: str) -> bool:
        """Whether a label named `name` marks blocked work under these rules."""
        return _named(name, pattern=self.blocked_label_pattern, listed=self.blocked_label_names)

    def is_blocked_state(self, name: str) -> bool:
        """Whether a workflow state named `name` holds blocked work under these rules."""
        return _named(name, pattern=self.blocked_state_pattern, listed=self.blocked_state_names)

    def is_wait_state(self, name: str) -> bool:
        """Whether time in a workflow state named `name` counts as wait under these rules."""
        return _named(name, pattern=False, listed=self.wait_state_names)

    def is_incident_label(self, name: str) -> bool:
        """Whether a label named `name` marks an incident under these rules."""
        return _named(name, pattern=False, listed=self.incident_label_names)

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
    object.__setattr__(
        rules, "wait_state_names", _names("wait_state_names", rules.wait_state_names)
    )
    object.__setattr__(
        rules, "incident_label_names", _names("incident_label_names", rules.incident_label_names)
    )
    object.__setattr__(rules, "remaining_state_types", _state_types(rules.remaining_state_types))
    object.__setattr__(rules, "type_labels", _type_labels(rules.type_labels))
    object.__setattr__(rules, "working_days", _weekdays(rules.working_days))
    object.__setattr__(rules, "holidays", _holidays(rules.holidays))


def _entries(name: str, value: object, cap: int = MAX_LIST_RULE_ENTRIES) -> list[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise ValueError(f"{name} must be a list")
    entries = list(value)
    if len(entries) > cap:
        raise ValueError(f"{name} must have at most {cap} entries")
    return entries


def _label(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} entries must be non-empty names")
    return value.strip()


def _names(rule: str, value: object) -> tuple[str, ...]:
    return tuple(_label(rule, entry) for entry in _entries(rule, value))


def _weekday(day: object) -> int:
    if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 7:
        raise ValueError(_WEEKDAYS_MESSAGE)
    return day


def _weekdays(value: object) -> tuple[int, ...]:
    days = {_weekday(day) for day in _entries("working_days", value)}
    if not days:
        raise ValueError(_WEEKDAYS_MESSAGE)
    return tuple(sorted(days))


def _holidays(value: object) -> tuple[date, ...]:
    entries = _entries("holidays", value, cap=MAX_HOLIDAYS)
    return tuple(sorted({_calendar_date(entry, _HOLIDAYS_MESSAGE) for entry in entries}))


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


def _calendar_date(value: object, message: str) -> date:
    """A date from the domain (a date) or stored JSON (a YYYY-MM-DD string).

    Only the extended YYYY-MM-DD form: `date.fromisoformat` alone also takes
    20261225 and 2026-W52-5, which nothing in Atlas writes.
    """
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:  # 2026-02-30
            pass
    raise ValueError(message)


def _tracked_since(value: object) -> date | None:
    return None if value is None else _calendar_date(value, _TRACKED_SINCE_MESSAGE)


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
