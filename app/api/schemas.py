from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.advisor.entities import MeetingType, Persona
from app.domain.events.entities import EventType
from app.domain.work_items.entities import DEFAULT_STATE, WorkItemType


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
    external_id: str | None
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
    external_id: str | None
    recorded_at: datetime


class IntegrationStatusRead(BaseModel):
    """Configured-or-not status for an external integration (connector, advisor)."""

    configured: bool


class SyncRequest(BaseModel):
    organization_id: UUID | None = None


class SyncSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    teams: int
    projects: int
    work_items: int
    events: int
    divergences: int


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
    weeks: list[ThroughputBucketRead]


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
    over_p85: bool


class AgingWipRead(BaseModel):
    now: datetime
    cycle_time_p85_seconds: float | None
    items: list[AgingItemRead]


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
