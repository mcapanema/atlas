from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.events.entities import EventType
from app.domain.work_items.entities import WorkItemType


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
    state: str = Field(default="backlog", min_length=1, max_length=255)
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


class ConnectorStatusRead(BaseModel):
    configured: bool


class SyncRequest(BaseModel):
    organization_id: UUID


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


class DailyFlowCountRead(BaseModel):
    day: date
    todo: int
    in_progress: int
    done: int


class ThroughputBucketRead(BaseModel):
    start: datetime
    end: datetime
    completed: int


class FlowHistoryRead(BaseModel):
    window_start: datetime
    window_end: datetime
    days: list[DailyFlowCountRead]
    weeks: list[ThroughputBucketRead]


class DurationBinRead(BaseModel):
    start_days: int
    end_days: int
    count: int


class LeadTimeDistributionRead(BaseModel):
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


class AdvisorStatusRead(BaseModel):
    configured: bool


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    priority: str
    problem: str
    root_cause: str
    action: str
    evidence: list[str]


class DeliveryAdviceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    generated_at: datetime
    summary: str
    recommendations: list[RecommendationRead]
