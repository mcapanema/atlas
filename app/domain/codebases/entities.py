from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow


class DeploymentStatus(StrEnum):
    """A deployment's normalized outcome, whatever the code host calls it."""

    # Queued, waiting, in progress, or no status yet.
    PENDING = "pending"
    SUCCESS = "success"
    # Failed or errored.
    FAILURE = "failure"


def _require_aware(owner: str, **values: datetime | None) -> None:
    for name, value in values.items():
        if value is not None and value.tzinfo is None:
            raise ValueError(f"{owner}.{name} must be timezone-aware")


@dataclass
class Codebase:
    """A source repository in a code host. Unmapped (no team) is never fetched."""

    organization_id: UUID
    name: str
    external_id: str
    url: str | None = None
    team_id: UUID | None = None
    production_environment: str = "production"
    last_synced_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Codebase name must not be empty")
        self.production_environment = self.production_environment.strip()
        if not self.production_environment:
            raise ValueError("Codebase production_environment must not be empty")
        _require_aware("Codebase", last_synced_at=self.last_synced_at)


@dataclass
class PullRequest:
    """A change proposed to a codebase; linked to work items by key."""

    codebase_id: UUID
    external_id: str
    number: int
    title: str
    opened_at: datetime
    url: str | None = None
    first_commit_at: datetime | None = None
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    merge_commit_sha: str | None = None
    work_item_keys: tuple[str, ...] = ()
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_aware(
            "PullRequest",
            opened_at=self.opened_at,
            first_commit_at=self.first_commit_at,
            merged_at=self.merged_at,
            closed_at=self.closed_at,
        )


@dataclass
class Deployment:
    """A release of a commit to an environment. Mutable: its status changes after creation."""

    codebase_id: UUID
    external_id: str
    environment: str
    sha: str
    started_at: datetime
    status: DeploymentStatus = DeploymentStatus.PENDING
    # When the terminal status was set.
    finished_at: datetime | None = None
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        _require_aware("Deployment", started_at=self.started_at, finished_at=self.finished_at)
