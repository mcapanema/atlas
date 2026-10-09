from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.advisor.entities import MeetingType, Persona
from app.domain.events.entities import EventType
from app.domain.work_items.entities import DEFAULT_STATE, StateType, WorkItemType


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime


class TeamCreate(BaseModel):
    organization_id: UUID
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = None


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    external_id: str | None
    created_at: datetime
    has_custom_rules: bool = False


class ProjectCreate(BaseModel):
    team_id: UUID
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    name: str
    external_id: str | None
    created_at: datetime


class WorkItemCreate(BaseModel):
    team_id: UUID
    title: str = Field(min_length=1, max_length=1024)
    type: WorkItemType = WorkItemType.TASK
    state: str = Field(default=DEFAULT_STATE, min_length=1, max_length=255)
    project_id: UUID | None = None
    external_id: str | None = None


class WorkItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    project_id: UUID | None
    title: str
    type: WorkItemType
    state: str
    state_type: StateType | None
    labels: list[str]
    external_id: str | None
    url: str | None
    created_at: datetime


class WorkItemPageRead(BaseModel):
    """One page of the work-items list plus the scope's total row count."""

    items: list[WorkItemRead]
    total: int


class EventCreate(BaseModel):
    work_item_id: UUID
    type: EventType
    occurred_at: datetime
    from_state: str | None = None
    to_state: str | None = None
    external_id: str | None = None


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    work_item_id: UUID
    type: EventType
    occurred_at: datetime
    from_state: str | None
    to_state: str | None
    from_state_type: StateType | None
    to_state_type: StateType | None
    detail: str | None
    external_id: str | None
    recorded_at: datetime


class IntegrationStatusRead(BaseModel):
    """Configured-or-not status for an external integration (connector, advisor)."""

    configured: bool


class LinearStatusRead(IntegrationStatusRead):
    # An automatic sync is running now; a manual sync waits for it (ADR-0014).
    auto_syncing: bool


class SyncRequest(BaseModel):
    organization_id: UUID | None = None
    # Re-derive every returned item's source events from the current mapping,
    # then rewrite snapshot history (ADR-0013). Use after a connector upgrade.
    rebuild: bool = False


class SyncSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    teams: int
    projects: int
    work_items: int
    events: int
    divergences: int
    deleted: int
    state_types_filled: int
    rebuilt: int


class SyncScheduleWrite(BaseModel):
    """PUT body for an organization's auto-sync schedule (ADR-0014).

    Ranges are the domain's to enforce (SyncSchedule.__post_init__ -> 422).
    """

    enabled: bool
    # ISO weekdays: 1 = Monday … 7 = Sunday.
    days: list[int]
    # Wall-clock times in `timezone`; the window includes both ends.
    window_start: time
    window_end: time
    interval_minutes: int
    # IANA zone name, e.g. "America/Sao_Paulo".
    timezone: str = Field(max_length=64)


class SyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slot_at: datetime
    finished_at: datetime
    error: str | None


class SyncScheduleRead(BaseModel):
    enabled: bool
    days: list[int]
    window_start: time
    window_end: time
    interval_minutes: int
    timezone: str
    updated_at: datetime
    last_run: SyncRunRead | None
    # When a manual "Sync now" last finished; it skips slots just after it.
    last_manual_sync_at: datetime | None
    # None while auto sync is off.
    next_run_at: datetime | None


class StatePeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: str
    entered_at: datetime
    exited_at: datetime | None


class BlockedPeriodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    started_at: datetime
    ended_at: datetime | None


class WorkItemTimelineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state_periods: list[StatePeriodRead]
    blocked_periods: list[BlockedPeriodRead]


class DurationStatsRead(BaseModel):
    p50_seconds: float
    p75_seconds: float
    p85_seconds: float
    p95_seconds: float
    mean_seconds: float


class FlowMetricsRead(BaseModel):
    window_start: datetime
    window_end: datetime
    completed: int
    wip: int
    lead_time: DurationStatsRead | None
    cycle_time: DurationStatsRead | None
    blocked_seconds: float
    flow_efficiency: float | None
    queue_time: DurationStatsRead | None
    touch_time: DurationStatsRead | None


class DailyFlowCountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: date
    todo: int
    in_progress: int
    done: int


class ThroughputBucketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start: datetime
    end: datetime
    completed: int


class FlowHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window_start: datetime
    window_end: datetime
    days: list[DailyFlowCountRead]
    buckets: list[ThroughputBucketRead]
    bucket_days: int
    data_as_of: datetime | None


class DurationBinRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_days: int
    end_days: int
    count: int


class LeadTimeDistributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window_start: datetime
    window_end: datetime
    bins: list[DurationBinRead]


class OutcomeBucketRead(BaseModel):
    days: int
    trials: int


class CompletionForecastRead(BaseModel):
    trials: int
    p50_date: datetime
    p75_date: datetime
    p85_date: datetime
    p95_date: datetime
    outcomes: list[OutcomeBucketRead]


class ForecastRead(BaseModel):
    window_start: datetime
    window_end: datetime
    remaining: int
    completion: CompletionForecastRead | None
    confidence: float | None


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    priority: Literal["high", "medium", "low"]
    problem: str
    root_cause: str
    action: str
    evidence: list[str]


class DeliveryAdviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    summary: str
    recommendations: list[RecommendationRead]


class AdviceContextRead(BaseModel):
    """The compact metrics digest the advisor reasons over, as plain text."""

    context: str


class TalkingPointRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    point: str
    detail: str
    evidence: list[str]
    needs_decision: bool


class MeetingPrepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting: MeetingType
    generated_at: datetime
    headline: str
    talking_points: list[TalkingPointRead]


class MetricSnapshotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    captured_on: date
    window_days: int
    completed: int
    wip: int
    lead_time_p50_seconds: float | None
    lead_time_p85_seconds: float | None
    cycle_time_p50_seconds: float | None
    cycle_time_p85_seconds: float | None
    blocked_seconds: float
    flow_efficiency: float | None


class ForecastAccuracyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evaluated: int
    pending: int
    p50_hit_rate: float | None
    p85_hit_rate: float | None
    mean_abs_error_days: float | None


class AgingItemRead(BaseModel):
    work_item_id: UUID
    title: str
    state: str
    age_seconds: float
    over_percentile: bool


class AgingWipRead(BaseModel):
    now: datetime
    cycle_time_percentile_seconds: float | None
    items: list[AgingItemRead]
    percentile: int


class HealthComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    score: int
    reason: str


class DeliveryHealthRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window_start: datetime
    window_end: datetime
    score: int | None
    band: Literal["healthy", "warning", "critical"] | None
    components: list[HealthComponentRead]


class ScopeOverviewRead(BaseModel):
    """One scope's dashboard row, from a single scope load (Executive Dashboard)."""

    metrics: FlowMetricsRead
    health: DeliveryHealthRead
    accuracy: ForecastAccuracyRead
    snapshots: list[MetricSnapshotRead]


class AdviceFeedbackCreate(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=2000)
    advice_summary: str = Field(min_length=1, max_length=4000)


class AdviceFeedbackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    persona: Persona
    rating: Literal["up", "down"]
    comment: str | None
    advice_summary: str
    created_at: datetime


class PersonaGuidanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    persona: Persona
    version: int
    guidance: str
    created_at: datetime


OpenStateType = Literal["triage", "backlog", "unstarted", "started"]


class TypeLabelRead(BaseModel):
    """One label -> work-item type mapping row."""

    label: str
    type: WorkItemType


class MetricRulesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exclude_born_done: bool
    move_back_ends_wip: bool
    restart_clock_after_move_back: bool
    reopen_completion: Literal["last", "first"]
    done_then_canceled: Literal["delivered", "canceled"]
    healthy_min: int
    warning_min: int
    predictability_worst_ratio: float
    stability_best_weeks: float
    stability_worst_weeks: float
    aging_percentile: int
    health_min_sample: int
    weight_predictability: float
    weight_efficiency: float
    weight_flow: float
    weight_stability: float
    weight_risk: float
    timezone: str
    daily_bucket_max_days: int
    forecast_history_days: int
    count_parent_issues: bool
    lead_time_start: Literal["created", "triage_exit"]
    done_then_reopened: Literal["delivered", "reopened"]
    canceled_then_reopened: Literal["canceled", "reopened"]
    blocked_label_pattern: bool
    blocked_label_names: list[str]
    blocked_by_relations: bool
    blocked_state_pattern: bool
    blocked_state_names: list[str]
    remaining_state_types: list[OpenStateType]
    type_labels: list[TypeLabelRead]

    @field_validator("type_labels", mode="before")
    @classmethod
    def _type_label_rows(cls, value: object) -> object:
        # The domain holds (label, type) pairs; the API speaks objects.
        if isinstance(value, tuple):
            return [{"label": label, "type": work_type} for label, work_type in value]
        return value


class MetricRulesOverridesWrite(BaseModel):
    """PATCH body: a value overrides the rule, null makes it inherit again, absent = unchanged.

    Ranges and cross-field rules are validated in the domain (MetricRules), so
    a violation comes back as a 422 naming the rule.
    """

    model_config = ConfigDict(extra="forbid")

    exclude_born_done: bool | None = None
    move_back_ends_wip: bool | None = None
    restart_clock_after_move_back: bool | None = None
    reopen_completion: Literal["last", "first"] | None = None
    done_then_canceled: Literal["delivered", "canceled"] | None = None
    healthy_min: int | None = None
    warning_min: int | None = None
    predictability_worst_ratio: float | None = None
    stability_best_weeks: float | None = None
    stability_worst_weeks: float | None = None
    aging_percentile: int | None = None
    health_min_sample: int | None = None
    weight_predictability: float | None = None
    weight_efficiency: float | None = None
    weight_flow: float | None = None
    weight_stability: float | None = None
    weight_risk: float | None = None
    timezone: str | None = None
    daily_bucket_max_days: int | None = None
    forecast_history_days: int | None = None
    count_parent_issues: bool | None = None
    lead_time_start: Literal["created", "triage_exit"] | None = None
    done_then_reopened: Literal["delivered", "reopened"] | None = None
    canceled_then_reopened: Literal["canceled", "reopened"] | None = None
    blocked_label_pattern: bool | None = None
    blocked_label_names: list[str] | None = None
    blocked_by_relations: bool | None = None
    blocked_state_pattern: bool | None = None
    blocked_state_names: list[str] | None = None
    remaining_state_types: list[OpenStateType] | None = None
    type_labels: list[TypeLabelRead] | None = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, mode="json")


class RecomputeStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: Literal["idle", "running", "failed"]
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class MetricRulesViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    built_in: MetricRulesRead
    inherited: MetricRulesRead
    overrides: dict[str, Any]
    effective: MetricRulesRead
    recompute: RecomputeStatusRead
