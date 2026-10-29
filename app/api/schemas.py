import re
from datetime import date, datetime, time
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.api.sync_jobs import SyncJob, SyncKind, SyncState, SyncTrigger
from app.application.codebases.service import CodebaseOverview
from app.application.codebases.sync import CodeSyncSummary
from app.application.sync.service import SyncSummary
from app.domain.advisor.entities import DeliveryAdvice, MeetingPrep, MeetingType, Persona
from app.domain.advisor.runs import AdviceRun
from app.domain.events.entities import EventType
from app.domain.metric_rules.entities import DEFAULT_RULES
from app.domain.work_items.entities import DEFAULT_STATE, StateType, WorkItemType

_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _is_iso_day(value: object) -> bool:
    return isinstance(value, date) or (isinstance(value, str) and bool(_ISO_DAY.fullmatch(value)))


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
    # The team's effective rule; both team routes fill it in from the rules.
    sprint_length_days: int = DEFAULT_RULES.sprint_length_days


class ProjectCreate(BaseModel):
    team_id: UUID
    name: str = Field(min_length=1, max_length=255)
    external_id: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    # Every team the project spans, home team first; `team_id` is the home team.
    team_ids: list[UUID]
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


class CodeSyncRequest(BaseModel):
    organization_id: UUID | None = None


class CodeSyncSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codebases: int
    pull_requests: int
    deployments: int
    events: int


class SyncJobRead(BaseModel):
    """A background sync, Linear or code: running, or one of the last finished ones."""

    id: UUID
    organization_id: UUID
    kind: SyncKind
    team_id: UUID | None
    rebuild: bool
    trigger: SyncTrigger
    state: SyncState
    phase: str | None
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    # The Linear counts (an organization or team job).
    summary: SyncSummaryRead | None
    # The code-host counts (a code job).
    code_summary: CodeSyncSummaryRead | None

    @classmethod
    def of(cls, job: SyncJob) -> "SyncJobRead":
        request = job.request
        return cls(
            id=job.id,
            organization_id=request.organization_id,
            kind=request.kind,
            team_id=request.team_id,
            rebuild=request.rebuild,
            trigger=request.trigger,
            state=job.state,
            phase=job.phase,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error=job.error,
            summary=SyncSummaryRead.model_validate(job.summary)
            if isinstance(job.summary, SyncSummary)
            else None,
            code_summary=CodeSyncSummaryRead.model_validate(job.summary)
            if isinstance(job.summary, CodeSyncSummary)
            else None,
        )


class LinearStatusRead(IntegrationStatusRead):
    # The sync job running now, manual or automatic; a new request either
    # gets it back (it covers the request) or a 409.
    running: SyncJobRead | None


class GitHubStatusRead(IntegrationStatusRead):
    # The configured organization or user login; None while unset.
    owner: str | None
    # The sync job running now, of any kind; as on LinearStatusRead.
    running: SyncJobRead | None


class CodebaseRead(BaseModel):
    """A codebase with how many pull requests and deployments are stored for it."""

    id: UUID
    organization_id: UUID
    name: str
    url: str | None
    team_id: UUID | None
    production_environment: str
    last_synced_at: datetime | None
    pull_requests: int
    deployments: int

    @classmethod
    def of(cls, overview: CodebaseOverview) -> "CodebaseRead":
        codebase = overview.codebase
        return cls(
            id=codebase.id,
            organization_id=codebase.organization_id,
            name=codebase.name,
            url=codebase.url,
            team_id=codebase.team_id,
            production_environment=codebase.production_environment,
            last_synced_at=codebase.last_synced_at,
            pull_requests=overview.pull_requests,
            deployments=overview.deployments,
        )


class CodebaseWrite(BaseModel):
    """PUT body for a codebase: its team (None unmaps it) and production environment."""

    team_id: UUID | None
    production_environment: str = Field(min_length=1, max_length=255)


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
    p50_seconds: float | None
    p85_seconds: float | None


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
    last_completed_at: datetime | None


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


class AdviceRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["running", "succeeded", "failed"]
    requested_at: datetime
    finished_at: datetime | None
    error: str | None
    advice: DeliveryAdviceRead | None

    @classmethod
    def from_run(cls, run: AdviceRun) -> "AdviceRunRead":
        advice = run.result if isinstance(run.result, DeliveryAdvice) else None
        return cls(
            id=run.id,
            status=run.status.value,
            requested_at=run.requested_at,
            finished_at=run.finished_at,
            error=run.error,
            advice=DeliveryAdviceRead.model_validate(advice) if advice else None,
        )


class MeetingPrepRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["running", "succeeded", "failed"]
    requested_at: datetime
    finished_at: datetime | None
    error: str | None
    prep: MeetingPrepRead | None

    @classmethod
    def from_run(cls, run: AdviceRun) -> "MeetingPrepRunRead":
        prep = run.result if isinstance(run.result, MeetingPrep) else None
        return cls(
            id=run.id,
            status=run.status.value,
            requested_at=run.requested_at,
            finished_at=run.finished_at,
            error=run.error,
            prep=MeetingPrepRead.model_validate(prep) if prep else None,
        )


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
    assignee: str | None
    blocked: bool
    over_median: bool


class AgingWipRead(BaseModel):
    now: datetime
    cycle_time_percentile_seconds: float | None
    cycle_time_median_seconds: float | None
    items: list[AgingItemRead]
    percentile: int
    history_days: int


class StateTimeRead(BaseModel):
    state: str
    total_seconds: float
    share: float
    median_seconds: float
    items: int
    queue: int
    wait_state: bool
    team: str | None


class StateTimesRead(BaseModel):
    window_start: datetime
    window_end: datetime
    measured: int
    min_sample: int
    states: list[StateTimeRead]
    bottleneck: str | None
    bottleneck_team: str | None


class HealthComponentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    score: int
    band: Literal["healthy", "warning", "critical"]
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
    predictability_floor: int
    stability_best_weeks: float
    stability_worst_weeks: float
    aging_percentile: int
    aging_history_days: int
    health_min_sample: int
    weight_predictability: float
    weight_efficiency: float
    weight_flow: float
    weight_stability: float
    weight_risk: float
    timezone: str
    working_days: list[int]
    holidays: list[date]
    daily_bucket_max_days: int
    forecast_history_days: int
    tracked_since: date | None
    count_parent_issues: bool
    lead_time_start: Literal["created", "triage_exit"]
    done_then_reopened: Literal["delivered", "reopened"]
    canceled_then_reopened: Literal["canceled", "reopened"]
    blocked_label_pattern: bool
    blocked_label_names: list[str]
    blocked_by_relations: bool
    blocked_state_pattern: bool
    blocked_state_names: list[str]
    wait_state_names: list[str]
    incident_label_names: list[str]
    remaining_state_types: list[OpenStateType]
    type_labels: list[TypeLabelRead]
    sprint_length_days: int

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
    predictability_floor: int | None = None
    stability_best_weeks: float | None = None
    stability_worst_weeks: float | None = None
    aging_percentile: int | None = None
    aging_history_days: int | None = None
    health_min_sample: int | None = None
    weight_predictability: float | None = None
    weight_efficiency: float | None = None
    weight_flow: float | None = None
    weight_stability: float | None = None
    weight_risk: float | None = None
    timezone: str | None = None
    working_days: list[int] | None = None
    holidays: list[date] | None = None
    daily_bucket_max_days: int | None = None
    forecast_history_days: int | None = None
    tracked_since: date | None = None
    count_parent_issues: bool | None = None
    lead_time_start: Literal["created", "triage_exit"] | None = None
    done_then_reopened: Literal["delivered", "reopened"] | None = None
    canceled_then_reopened: Literal["canceled", "reopened"] | None = None
    blocked_label_pattern: bool | None = None
    blocked_label_names: list[str] | None = None
    blocked_by_relations: bool | None = None
    blocked_state_pattern: bool | None = None
    blocked_state_names: list[str] | None = None
    wait_state_names: list[str] | None = None
    incident_label_names: list[str] | None = None
    remaining_state_types: list[OpenStateType] | None = None
    type_labels: list[TypeLabelRead] | None = None
    sprint_length_days: int | None = None

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, mode="json")

    @field_validator("holidays", mode="before")
    @classmethod
    def _yyyy_mm_dd(cls, value: object) -> object:
        # Pydantic's date also takes Unix timestamps and midnight datetimes;
        # a holiday is a calendar day, written one way.
        if isinstance(value, list) and not all(_is_iso_day(day) for day in value):
            raise ValueError("holidays must be a list of dates, e.g. 2026-12-25")
        return value


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


SharedRulesFormat = Literal["atlas-metric-rules"]


class SharedTeamRulesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    external_id: str | None
    overrides: dict[str, Any]


class SharedRulesRead(BaseModel):
    """An exported rules file (ADR-0019): no Atlas UUIDs, teams by source id and name."""

    format: SharedRulesFormat = "atlas-metric-rules"
    version: Literal[1] = 1
    exported_at: datetime
    workspace: dict[str, Any]
    teams: list[SharedTeamRulesRead]


class SharedTeamRulesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    external_id: str | None = None
    overrides: MetricRulesOverridesWrite


class SharedRulesWrite(BaseModel):
    """An imported rules file; each layer is validated exactly like a PATCH body."""

    model_config = ConfigDict(extra="forbid")

    format: SharedRulesFormat
    version: Literal[1]
    exported_at: datetime | None = None
    workspace: MetricRulesOverridesWrite
    teams: list[SharedTeamRulesWrite] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _atlas_rules_file(cls, value: object) -> object:
        # Field errors ("format: Input should be…") don't tell a person they
        # picked the wrong file, or one from a newer Atlas.
        if not isinstance(value, dict) or value.get("format") != "atlas-metric-rules":
            raise PydanticCustomError("not_atlas_rules", "Not an Atlas metric rules file")
        version = value.get("version")
        if isinstance(version, bool):  # lax Literal[1] would read `true` as 1
            raise PydanticCustomError("rules_file_version", "version must be 1")
        if isinstance(version, int) and version > 1:
            raise PydanticCustomError(
                "newer_rules_file",
                "This rules file is version {version}; this Atlas reads version 1. "
                "Update Atlas to import it.",
                {"version": version},
            )
        return value


class MetricRulesImportRead(BaseModel):
    imported_teams: list[str]
    skipped_teams: list[str]
    ambiguous_teams: list[str]
    rules: MetricRulesViewRead


class PersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    display_name: str | None
    shown_name: str
    email: str | None


class PersonWrite(BaseModel):
    # Blank clears the override.
    display_name: str | None = Field(max_length=255)
