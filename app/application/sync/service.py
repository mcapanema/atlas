import logging
from dataclasses import dataclass
from uuid import UUID

from app.domain.events.entities import Event, EventType
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

logger = logging.getLogger(__name__)


class UnknownOrganizationError(Exception):
    """Sync was requested for an organization that doesn't exist.

    Not a ValueError: the global ValueError handler answers 422 (malformed
    input), but a missing resource is a 404 — the router maps it there.
    """


@dataclass(frozen=True)
class SyncSummary:
    """Counts of entities written (created or updated) by one sync run."""

    teams: int
    projects: int
    work_items: int
    events: int
    # Items whose source state said done while their history had no
    # completion event; sync synthesized the terminal event for them.
    divergences: int


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
            raise UnknownOrganizationError(f"Organization {organization_id} does not exist")
        logger.info("Sync started for organization %s", organization_id)
        teams = await self._sync_teams(organization_id)
        projects = await self._sync_projects()
        work_items, events, divergences = await self._sync_work_items()
        summary = SyncSummary(
            teams=teams,
            projects=projects,
            work_items=work_items,
            events=events,
            divergences=divergences,
        )
        logger.info(
            "Sync finished for organization %s: teams=%d projects=%d work_items=%d "
            "events=%d divergences=%d",
            organization_id,
            summary.teams,
            summary.projects,
            summary.work_items,
            summary.events,
            summary.divergences,
        )
        return summary

    async def _sync_teams(self, organization_id: UUID) -> int:
        written = 0
        sources = await self._source.fetch_teams()
        existing_by_eid = {
            team.external_id: team
            for team in await self._teams.list()
            if team.external_id is not None
        }
        for source in sources:
            existing = existing_by_eid.get(source.external_id)
            if existing is None:
                team = Team(
                    organization_id=organization_id,
                    name=source.name,
                    external_id=source.external_id,
                )
                await self._teams.add(team)
                written += 1
            elif existing.name != source.name:
                updated = Team(
                    organization_id=existing.organization_id,
                    name=source.name,
                    external_id=existing.external_id,
                    id=existing.id,
                    created_at=existing.created_at,
                )
                await self._teams.update(updated)
                written += 1
        return written

    async def _sync_projects(self) -> int:
        written = 0
        sources = await self._source.fetch_projects()
        # snapshot after _sync_teams so this run's new teams are included
        teams_by_eid = {
            team.external_id: team
            for team in await self._teams.list()
            if team.external_id is not None
        }
        projects_by_eid = {
            project.external_id: project
            for project in await self._projects.list()
            if project.external_id is not None
        }
        for source in sources:
            if source.team_external_id is None:
                continue  # a Project requires an owning Team
            team = teams_by_eid.get(source.team_external_id)
            if team is None:
                continue
            existing = projects_by_eid.get(source.external_id)
            if existing is None:
                project = Project(
                    team_id=team.id, name=source.name, external_id=source.external_id
                )
                await self._projects.add(project)
                written += 1
            elif (existing.name, existing.team_id) != (source.name, team.id):
                updated = Project(
                    team_id=team.id,
                    name=source.name,
                    external_id=existing.external_id,
                    id=existing.id,
                    created_at=existing.created_at,
                )
                await self._projects.update(updated)
                written += 1
        return written

    async def _sync_work_items(self) -> tuple[int, int, int]:
        items_written = 0
        events_written = 0
        divergences = 0
        sources = await self._source.fetch_work_items()
        teams_by_eid = {
            team.external_id: team
            for team in await self._teams.list()
            if team.external_id is not None
        }
        projects_by_eid = {
            project.external_id: project
            for project in await self._projects.list()
            if project.external_id is not None
        }
        items_by_eid = {
            item.external_id: item
            for item in await self._work_items.list()
            if item.external_id is not None
        }
        candidate_event_eids = [
            event.external_id for source in sources for event in source.events
        ] + [
            f"{source.external_id}:completed"
            for source in sources
            if source.completed_at is not None
        ]
        existing_event_eids = await self._events.existing_external_ids(
            candidate_event_eids
        )
        for source in sources:
            team = teams_by_eid.get(source.team_external_id)
            if team is None:
                continue  # can't place a work item without its team
            project_id: UUID | None = None
            if source.project_external_id is not None:
                project = projects_by_eid.get(source.project_external_id)
                project_id = project.id if project is not None else None
            existing = items_by_eid.get(source.external_id)
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
                changed = (
                    existing.title,
                    existing.state,
                    existing.project_id,
                    existing.team_id,
                    existing.type,
                ) != (source.title, source.state, project_id, team.id, source.type)
                if changed:
                    work_item = WorkItem(
                        team_id=team.id,
                        title=source.title,
                        type=source.type,
                        state=source.state,
                        project_id=project_id,
                        external_id=existing.external_id,
                        id=existing.id,
                        created_at=existing.created_at,
                    )
                    await self._work_items.update(work_item)
                    items_written += 1
            written, diverged = await self._sync_events(
                work_item.id, source, existing_event_eids
            )
            events_written += written
            divergences += diverged
        return items_written, events_written, divergences

    async def _sync_events(
        self, work_item_id: UUID, source: SourceWorkItem, existing: set[str]
    ) -> tuple[int, int]:
        """Insert missing events; returns (events written, divergences found).

        `existing` is the run-wide set of already-persisted event external
        ids (one batched query per sync); ids written here are added to it,
        preserving idempotency without per-event SELECTs. A divergence is an
        item whose source state says done while its history shows no
        completion event — the terminal event is synthesized with a
        deterministic external_id (see Phase C).
        """
        written = 0
        for source_event in source.events:
            if source_event.external_id in existing:
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
            existing.add(source_event.external_id)
            written += 1

        has_completion = any(e.type is EventType.COMPLETED for e in source.events)
        if source.completed_at is None or has_completion:
            return written, 0
        external_id = f"{source.external_id}:completed"
        if external_id not in existing:
            await self._events.add(
                Event(
                    work_item_id=work_item_id,
                    type=EventType.COMPLETED,
                    occurred_at=source.completed_at,
                    to_state=source.state,
                    external_id=external_id,
                )
            )
            existing.add(external_id)
            written += 1
        return written, 1
