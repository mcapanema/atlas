from dataclasses import dataclass
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.organizations.repository import OrganizationRepository
from app.domain.projects.entities import Project
from app.domain.projects.repository import ProjectRepository
from app.domain.sync.port import DeliveryDataSource
from app.domain.sync.source import SourceWorkItem
from app.domain.teams.entities import Team
from app.domain.teams.repository import TeamRepository
from app.domain.work_items.entities import WorkItem
from app.domain.work_items.repository import WorkItemRepository


@dataclass(frozen=True)
class SyncSummary:
    """Counts of entities written (created or updated) by one sync run."""

    teams: int
    projects: int
    work_items: int
    events: int


class SyncService:
    """Pulls a DeliveryDataSource into the domain model, idempotently.

    Everything is matched by external_id: missing entities are created,
    changed ones updated, unchanged ones left alone. Events are immutable —
    insert if absent, never update. Running sync twice in a row is a no-op.
    Projects and work items whose team can't be resolved are skipped.
    """

    def __init__(
        self,
        source: DeliveryDataSource,
        organizations: OrganizationRepository,
        teams: TeamRepository,
        projects: ProjectRepository,
        work_items: WorkItemRepository,
        events: EventRepository,
    ) -> None:
        self._source = source
        self._organizations = organizations
        self._teams = teams
        self._projects = projects
        self._work_items = work_items
        self._events = events

    async def sync(self, organization_id: UUID) -> SyncSummary:
        if await self._organizations.get(organization_id) is None:
            raise ValueError(f"Organization {organization_id} does not exist")
        # ponytail: one get_by_external_id query per source entity (N+1).
        # Batch the lookups if syncing a large workspace ever gets slow.
        teams = await self._sync_teams(organization_id)
        projects = await self._sync_projects()
        work_items, events = await self._sync_work_items()
        return SyncSummary(teams=teams, projects=projects, work_items=work_items, events=events)

    async def _sync_teams(self, organization_id: UUID) -> int:
        written = 0
        for source in await self._source.fetch_teams():
            existing = await self._teams.get_by_external_id(source.external_id)
            if existing is None:
                team = Team(
                    organization_id=organization_id,
                    name=source.name,
                    external_id=source.external_id,
                )
                await self._teams.add(team)
                written += 1
            elif existing.name != source.name:
                existing.name = source.name
                await self._teams.update(existing)
                written += 1
        return written

    async def _sync_projects(self) -> int:
        written = 0
        for source in await self._source.fetch_projects():
            if source.team_external_id is None:
                continue  # a Project requires an owning Team
            team = await self._teams.get_by_external_id(source.team_external_id)
            if team is None:
                continue
            existing = await self._projects.get_by_external_id(source.external_id)
            if existing is None:
                project = Project(
                    team_id=team.id, name=source.name, external_id=source.external_id
                )
                await self._projects.add(project)
                written += 1
            elif existing.name != source.name:
                existing.name = source.name
                await self._projects.update(existing)
                written += 1
        return written

    async def _sync_work_items(self) -> tuple[int, int]:
        items_written = 0
        events_written = 0
        for source in await self._source.fetch_work_items():
            team = await self._teams.get_by_external_id(source.team_external_id)
            if team is None:
                continue  # can't place a work item without its team
            project_id = await self._resolve_project_id(source.project_external_id)
            existing = await self._work_items.get_by_external_id(source.external_id)
            if existing is None:
                work_item = WorkItem(
                    team_id=team.id,
                    title=source.title,
                    type=source.type,
                    state=source.state,
                    project_id=project_id,
                    external_id=source.external_id,
                    created_at=source.created_at,
                )
                await self._work_items.add(work_item)
                items_written += 1
            else:
                work_item = existing
                changed = (existing.title, existing.state, existing.project_id) != (
                    source.title,
                    source.state,
                    project_id,
                )
                if changed:
                    existing.title = source.title
                    existing.state = source.state
                    existing.project_id = project_id
                    await self._work_items.update(existing)
                    items_written += 1
            events_written += await self._sync_events(work_item.id, source)
        return items_written, events_written

    async def _resolve_project_id(self, project_external_id: str | None) -> UUID | None:
        if project_external_id is None:
            return None
        project = await self._projects.get_by_external_id(project_external_id)
        return project.id if project is not None else None

    async def _sync_events(self, work_item_id: UUID, source: SourceWorkItem) -> int:
        written = 0
        for source_event in source.events:
            if await self._events.get_by_external_id(source_event.external_id) is not None:
                continue
            event = Event(
                work_item_id=work_item_id,
                type=source_event.type,
                occurred_at=source_event.occurred_at,
                from_state=source_event.from_state,
                to_state=source_event.to_state,
                external_id=source_event.external_id,
            )
            await self._events.add(event)
            written += 1
        return written
