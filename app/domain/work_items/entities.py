from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain._time import utcnow

DEFAULT_STATE = "backlog"


class WorkItemType(StrEnum):
    """Normalized delivery unit type. External issue types map onto these."""

    STORY = "story"
    TASK = "task"
    BUG = "bug"
    SPIKE = "spike"
    OTHER = "other"


class StateType(StrEnum):
    """A workflow state's category — the vocabulary Linear (and most trackers) share."""

    TRIAGE = "triage"
    BACKLOG = "backlog"
    UNSTARTED = "unstarted"
    STARTED = "started"
    COMPLETED = "completed"
    CANCELED = "canceled"


# The open categories in workflow order: the forecast-remaining choices.
OPEN_STATE_TYPES = (StateType.TRIAGE, StateType.BACKLOG, StateType.UNSTARTED, StateType.STARTED)
# Not started yet: where a Done or Canceled item lands when it is reopened.
NOT_STARTED_STATE_TYPES = frozenset({StateType.TRIAGE, StateType.BACKLOG, StateType.UNSTARTED})


@dataclass
class WorkItem:
    """The atomic unit of delivery. Owned by a Team, optionally within a Project."""

    team_id: UUID
    title: str
    type: WorkItemType = WorkItemType.TASK
    state: str = DEFAULT_STATE
    project_id: UUID | None = None
    external_id: str | None = None
    # Deep link to the item in the origin system; None for manually created items.
    url: str | None = None
    # The current state's category; None when unknown (created via the REST API).
    state_type: StateType | None = None
    # Current label names, as the source system spells them.
    labels: tuple[str, ...] = ()
    # The parent issue, when it is in Atlas too; None otherwise.
    parent_id: UUID | None = None
    # Name of the person the item is assigned to in the source system, as of
    # the last sync; None when unassigned or created via the REST API.
    assignee: str | None = None
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        stripped = self.title.strip()
        if not stripped:
            raise ValueError("WorkItem title must not be empty")
        self.title = stripped
