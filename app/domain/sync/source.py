"""Platform-neutral snapshots of an external delivery system.

Connectors (Infrastructure) produce these; the sync use case (Application)
consumes them. They carry external identity only — internal UUIDs are
resolved during sync.
"""

from dataclasses import dataclass
from datetime import datetime

from app.domain.codebases.entities import DeploymentStatus
from app.domain.events.entities import EventType
from app.domain.work_items.entities import StateType, WorkItemType


@dataclass(frozen=True)
class SourceTeam:
    external_id: str
    name: str


@dataclass(frozen=True)
class SourcePerson:
    external_id: str
    name: str
    email: str | None = None


@dataclass(frozen=True)
class SourceProject:
    external_id: str
    name: str
    team_external_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceEvent:
    external_id: str
    type: EventType
    occurred_at: datetime
    from_state: str | None = None
    to_state: str | None = None
    # Categories of from_state/to_state on a state transition; None when
    # unknown (REST-created events, or not filled yet — ADR-0011).
    from_state_type: StateType | None = None
    to_state_type: StateType | None = None
    # Label name (label events) or blocker identifier (blocker events).
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None:
            raise ValueError("SourceEvent.occurred_at must be timezone-aware")


@dataclass(frozen=True)
class SourceWorkItem:
    external_id: str
    title: str
    type: WorkItemType
    state: str
    team_external_id: str
    project_external_id: str | None
    created_at: datetime
    # When the source system says the item reached a done state — set even
    # when the event history (e.g. a truncated changelog) never recorded a
    # completion. Sync uses the mismatch to synthesize the terminal event.
    completed_at: datetime | None = None
    events: tuple[SourceEvent, ...] = ()
    # Deep link to the issue in the source system.
    url: str | None = None
    # Current state category, label names, and parent issue (source identity).
    state_type: StateType | None = None
    labels: tuple[str, ...] = ()
    parent_external_id: str | None = None
    # Person the issue is currently assigned to; None when unassigned.
    assignee: SourcePerson | None = None
    # The item's human-readable key in the source, e.g. "DEP-123".
    key: str | None = None


def _require_aware(owner: str, **values: datetime | None) -> None:
    for name, value in values.items():
        if value is not None and value.tzinfo is None:
            raise ValueError(f"{owner}.{name} must be timezone-aware")


@dataclass(frozen=True)
class SourceCodebase:
    external_id: str
    name: str
    url: str | None = None


@dataclass(frozen=True)
class SourcePullRequest:
    external_id: str
    number: int
    title: str
    opened_at: datetime
    url: str | None = None
    first_commit_at: datetime | None = None
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    merge_commit_sha: str | None = None
    # Work-item keys found in the branch name, title and body (upper-case).
    work_item_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_aware(
            "SourcePullRequest",
            opened_at=self.opened_at,
            first_commit_at=self.first_commit_at,
            merged_at=self.merged_at,
            closed_at=self.closed_at,
        )


@dataclass(frozen=True)
class SourceDeployment:
    external_id: str
    environment: str
    sha: str
    started_at: datetime
    status: DeploymentStatus
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware("SourceDeployment", started_at=self.started_at, finished_at=self.finished_at)
