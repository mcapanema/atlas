"""Metric rules: the per-team knobs behind every computed metric.

Teams work differently (one parks work in Backlog and restarts it, another
never does), so each interpretation Atlas makes of delivery data is a rule.
Built-in defaults reproduce Atlas's original behavior; an organization's
overrides (the workspace default) layer on top, then a team's. Analytics
only ever see one resolved MetricRules.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, tzinfo
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain._time import utcnow

ReopenCompletion = Literal["last", "first"]
DoneThenCanceled = Literal["delivered", "canceled"]
RecomputeState = Literal["idle", "running", "failed"]

HEALTH_COMPONENTS = ("predictability", "efficiency", "flow", "stability", "risk")

_FLAGS = ("exclude_born_done", "move_back_ends_wip", "restart_clock_after_move_back")
_CHOICES: dict[str, tuple[str, ...]] = {
    "reopen_completion": ("last", "first"),
    "done_then_canceled": ("delivered", "canceled"),
}
_INTEGERS = (
    "healthy_min",
    "warning_min",
    "aging_percentile",
    "daily_bucket_max_days",
    "forecast_history_days",
)
_RANGES: dict[str, tuple[float, float]] = {
    "healthy_min": (1, 100),
    "warning_min": (0, 99),
    "predictability_worst_ratio": (1.1, 20),
    "stability_best_weeks": (0, 52),
    "stability_worst_weeks": (0.1, 52),
    "aging_percentile": (50, 99),
    **{f"weight_{name}": (0, 10) for name in HEALTH_COMPONENTS},
    "daily_bucket_max_days": (1, 90),
    "forecast_history_days": (7, 365),
}


@dataclass(frozen=True)
class MetricRules:
    """Every rule that changes how a metric is computed; defaults = built-in behavior."""

    # Lifecycle: how one item's events fold into its flow sample.
    exclude_born_done: bool = True
    move_back_ends_wip: bool = True
    restart_clock_after_move_back: bool = False
    reopen_completion: ReopenCompletion = "last"
    done_then_canceled: DoneThenCanceled = "delivered"
    # Delivery-health scoring.
    healthy_min: int = 70
    warning_min: int = 40
    predictability_worst_ratio: float = 4.0
    stability_best_weeks: float = 1.0
    stability_worst_weeks: float = 5.0
    aging_percentile: int = 85
    weight_predictability: float = 1.0
    weight_efficiency: float = 1.0
    weight_flow: float = 1.0
    weight_stability: float = 1.0
    weight_risk: float = 1.0
    # Calendar and windows. Short windows have no weekly shape to read (a
    # 7-day window is one weekly bar), so they chart throughput per day.
    timezone: str = "UTC"
    daily_bucket_max_days: int = 21
    forecast_history_days: int = 90

    def __post_init__(self) -> None:
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
