from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkItemType(StrEnum):
    """Normalized delivery unit type. External issue types map onto these."""

    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SPIKE = "spike"
    OTHER = "other"


@dataclass
class WorkItem:
    """The atomic unit of delivery. Owned by a Team, optionally within a Project."""

    team_id: UUID
    title: str
    type: WorkItemType = WorkItemType.TASK
    state: str = "backlog"
    project_id: UUID | None = None
    external_id: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        stripped = self.title.strip()
        if not stripped:
            raise ValueError("WorkItem title must not be empty")
        self.title = stripped
