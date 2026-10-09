import logging
from dataclasses import dataclass, replace
from uuid import UUID

from app.domain._time import utcnow
from app.domain.events.entities import Event, EventType
from app.domain.events.repository import EventRepository
from app.domain.organizations.entities import Organization
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


class UnknownTeamError(Exception):
    """A team sync was requested for a team that doesn't exist (404, not 422)."""


@dataclass(frozen=True)
class SyncSummary:
    """Counts of entities written (created or updated) by one sync run."""

    # The organization this run synced (bootstrapped or given).
    organization_id: UUID
    teams: int
    projects: int
    work_items: int
    events: int
    # Items whose source state said done while their history had no
    # completion event; sync synthesized the terminal event for them.
    divergences: int
    # Atlas work items (with their events) whose source item is gone —
    # deleted or trashed upstream (ADR-0009).
    deleted: int
    # Stored transition events given their state types (ADR-0011).
    state_types_filled: int
    # Synced items whose source events were deleted and re-inserted from the
    # current mapping (rebuild=True, ADR-0013); 0 for a plain sync.
    rebuilt: int


def _candidate_event_eids(sources: list[SourceWorkItem]) -> list[str]:
    """Every event external id a run may insert, incl. synthesized completions."""
    return [event.external_id for source in sources for event in source.events] + [
        f"{source.external_id}:completed" for source in sources if source.completed_at is not None
    ]


class SyncService:
    """Pulls a DeliveryDataSource into the domain model, idempotently.

    Everything is matched by external_id: missing entities are created,
    changed ones updated, unchanged ones left alone. Events are immutable —
    insert if absent, never update. Running sync twice in a row is a no-op.
    Work items the source no longer returns are deleted with their events
    (ADR-0009). Projects and work items whose team can't be resolved are skipped. When
    no organization_id is given, sync reuses the single existing
    organization or creates one named after the source workspace. With
    rebuild=True, every returned item's source-derived events are deleted and
    re-inserted from the current mapping (ADR-0013). sync_team() syncs one
    team's work items and never prunes.
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

    async def sync(
        self, organization_id: UUID | None = None, *, rebuild: bool = False
    ) -> SyncSummary:
        resolved = await self._resolve_organization(organization_id)
        logger.info("Sync started for organization %s (rebuild=%s)", resolved, rebuild)
        return await self._run(resolved, None, rebuild=rebuild)

    async def sync_team(self, team_id: UUID) -> SyncSummary:
        """Sync one team's work items; teams and projects still sync org-wide.

        Nothing is pruned: a team-filtered fetch can't tell an item deleted
        upstream from one moved to another team, so deletions wait for the
        next organization sync (manual or scheduled).
        """
        team = await self._teams.get(team_id)
        if team is None:
            raise UnknownTeamError(f"Team {team_id} does not exist")
        if team.external_id is None:
            # ValueError on purpose: the global handler answers 422.
            raise ValueError(
                f"Team {team.name!r} was not synced from a source; there is nothing to sync"
            )
        logger.info("Sync started for team %s (%s)", team.id, team.name)
        return await self._run(team.organization_id, team.external_id, rebuild=False)

    async def _run(
        self, organization_id: UUID, team_external_id: str | None, *, rebuild: bool
    ) -> SyncSummary:
        teams = await self._sync_teams(organization_id)
        projects = await self._sync_projects()
        sources = await self._source.fetch_work_items(team_external_id=team_external_id)
        work_items, events, divergences, deleted, rebuilt = await self._sync_work_items(
            sources, rebuild=rebuild, prune=team_external_id is None
        )
        # After the work-item sync: rebuilt and newly inserted events already carry
        # their types, so only stored events left untyped are filled — exact in both
        # modes, including items a rebuild skips (team unresolved).
        filled = await self._fill_state_types(sources)
        await self._stamp_synced(organization_id, team_external_id)
        summary = SyncSummary(
            organization_id=organization_id,
            teams=teams,
            projects=projects,
            work_items=work_items,
            events=events,
            divergences=divergences,
            deleted=deleted,
            state_types_filled=filled,
            rebuilt=rebuilt,
        )
        logger.info(
            "Sync finished for organization %s: teams=%d projects=%d work_items=%d "
            "events=%d divergences=%d deleted=%d state_types_filled=%d rebuilt=%d",
            organization_id,
            summary.teams,
            summary.projects,
            summary.work_items,
            summary.events,
            summary.divergences,
            summary.deleted,
            summary.state_types_filled,
            summary.rebuilt,
        )
        return summary

    async def _resolve_organization(self, organization_id: UUID | None) -> UUID:
        if organization_id is not None:
            if await self._organizations.get(organization_id) is None:
                raise UnknownOrganizationError(f"Organization {organization_id} does not exist")
            return organization_id
        existing = await self._organizations.list()
        if len(existing) == 1:
            return existing[0].id
        if len(existing) > 1:
            # ValueError on purpose: the global handler answers 422 — the
            # client's request is underspecified, not a missing resource.
            raise ValueError("Multiple organizations exist; specify organization_id")
        # First run: bootstrap the organization from the source workspace.
        organization = Organization(name=await self._source.fetch_organization_name())
        await self._organizations.add(organization)
        logger.info("Created organization %r from the source workspace", organization.name)
        return organization.id

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
                updated = replace(existing, name=source.name)
                await self._teams.update(updated)
                written += 1
        return written

    async def _stamp_synced(self, organization_id: UUID, team_external_id: str | None) -> None:
        """Date the synced teams' data: every source team of the org, or the one team."""
        synced = [
            team.id
            for team in await self._teams.list()
            if team.organization_id == organization_id
            and team.external_id is not None
            and team_external_id in (None, team.external_id)
        ]
        await self._teams.mark_synced(synced, utcnow())

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
                project = Project(team_id=team.id, name=source.name, external_id=source.external_id)
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

    async def _fill_state_types(self, sources: list[SourceWorkItem]) -> int:
        """Give already-stored transition events their state types, once (ADR-0011).

        The one exception to insert-only events: a type that's still empty
        is filled, never changed. After the first sync under this code
        nothing is missing, and this is a single batched lookup.
        """
        typed = {
            event.external_id: (event.from_state_type, event.to_state_type)
            for source in sources
            for event in source.events
            if event.to_state_type is not None
        }
        missing = await self._events.external_ids_missing_state_types(list(typed))
        if not missing:
            return 0
        filled = await self._events.fill_state_types({eid: typed[eid] for eid in missing})
        logger.info("Filled state types on %d stored event(s)", filled)
        return filled

    async def _upsert_item(
        self,
        source: SourceWorkItem,
        team_id: UUID,
        project_id: UUID | None,
        existing: WorkItem | None,
    ) -> tuple[WorkItem, bool]:
        """Create or update the item from its source; (item, written?). Parents link later."""
        if existing is None:
            item = WorkItem(
                team_id=team_id,
                title=source.title,
                type=source.type,
                state=source.state,
                project_id=project_id,
                external_id=source.external_id,
                url=source.url,
                state_type=source.state_type,
                labels=source.labels,
                created_at=source.created_at,
            )
            await self._work_items.add(item)
            return item, True
        item = replace(
            existing,
            team_id=team_id,
            title=source.title,
            type=source.type,
            state=source.state,
            project_id=project_id,
            url=source.url,
            state_type=source.state_type,
            labels=source.labels,
        )
        if item == existing:
            return existing, False
        await self._work_items.update(item)
        return item, True

    async def _link_parents(
        self, sources: list[SourceWorkItem], items_by_eid: dict[str, WorkItem]
    ) -> set[UUID]:
        """Point each synced item at its parent, once every item exists; ids written.

        A parent may sync after its child, so links resolve in this second
        pass. A parent outside Atlas leaves the link empty.
        """
        written: set[UUID] = set()
        for source in sources:
            item = items_by_eid.get(source.external_id)
            if item is None:
                continue
            parent = items_by_eid.get(source.parent_external_id or "")
            parent_id = parent.id if parent is not None else None
            if item.parent_id != parent_id:
                await self._work_items.update(replace(item, parent_id=parent_id))
                written.add(item.id)
        return written

    async def _sync_work_items(
        self, sources: list[SourceWorkItem], *, rebuild: bool = False, prune: bool = True
    ) -> tuple[int, int, int, int, int]:
        events_written = 0
        divergences = 0
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
        rebuilt = (
            await self._drop_source_events(sources, teams_by_eid, items_by_eid) if rebuild else 0
        )
        existing_event_eids = await self._events.existing_external_ids(
            _candidate_event_eids(sources)
        )
        synced: dict[str, WorkItem] = {}
        written: set[UUID] = set()
        for source in sources:
            team = teams_by_eid.get(source.team_external_id)
            if team is None:
                continue  # can't place a work item without its team
            project = projects_by_eid.get(source.project_external_id or "")
            item, changed = await self._upsert_item(
                source,
                team.id,
                project.id if project is not None else None,
                items_by_eid.get(source.external_id),
            )
            synced[source.external_id] = item
            if changed:
                written.add(item.id)
            n, diverged = await self._sync_events(item.id, source, existing_event_eids)
            events_written += n
            divergences += diverged
        written |= await self._link_parents(sources, {**items_by_eid, **synced})
        deleted = await self._prune_vanished(sources, teams_by_eid, items_by_eid) if prune else 0
        return len(written), events_written, divergences, deleted, rebuilt

    async def _drop_source_events(
        self,
        sources: list[SourceWorkItem],
        teams_by_eid: dict[str, Team],
        items_by_eid: dict[str, WorkItem],
    ) -> int:
        """Delete the source-derived events of every stored item this run returned.

        The sync loop then re-inserts each from the current mapping, so a
        mapping fix reaches events stored by older code (ADR-0013). Only
        events with an external_id go — the events API records none. Items
        this run didn't return are pruning's business, not a rebuild's.
        """
        ids = [
            items_by_eid[source.external_id].id
            for source in sources
            if source.external_id in items_by_eid and source.team_external_id in teams_by_eid
        ]
        if ids:
            await self._events.delete_sourced_for_work_items(ids)
            logger.info("Rebuild: replacing the source events of %d work item(s)", len(ids))
        return len(ids)

    async def _prune_vanished(
        self,
        sources: list[SourceWorkItem],
        teams_by_eid: dict[str, Team],
        items_by_eid: dict[str, WorkItem],
    ) -> int:
        """Delete synced items the source no longer returns (deleted or trashed upstream).

        Scoped to teams that returned live work this run: a team the
        credentials can no longer see returns nothing, which is lost access,
        not deletion — so an empty fetch deletes nothing. Items without an
        external_id never came from the source and are never touched.

        ponytail: a node the datasource skips as malformed reads as vanished
        and is deleted; the next clean sync recreates it from source history.
        A team whose every issue was deleted upstream keeps its items — prune
        per team only if that ever shows up.
        """
        live = {source.external_id for source in sources}
        live_team_ids = {
            teams_by_eid[source.team_external_id].id
            for source in sources
            if source.team_external_id in teams_by_eid
        }
        vanished = [
            item.id
            for external_id, item in items_by_eid.items()
            if external_id not in live and item.team_id in live_team_ids
        ]
        if vanished:
            await self._events.delete_for_work_items(vanished)
            await self._work_items.delete(vanished)
            logger.info("Deleted %d work item(s) gone from the source", len(vanished))
        return len(vanished)

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
                from_state_type=source_event.from_state_type,
                to_state_type=source_event.to_state_type,
                detail=source_event.detail,
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
