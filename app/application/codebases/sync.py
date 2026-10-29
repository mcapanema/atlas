import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.application.sync.service import PhaseCallback, SyncPhase, UnknownOrganizationError
from app.domain._time import utcnow
from app.domain.codebases.entities import Codebase, Deployment, PullRequest
from app.domain.codebases.repository import (
    CodebaseRepository,
    DeploymentRepository,
    PullRequestRepository,
)
from app.domain.events.entities import Event, EventType
from app.domain.events.repository import EventRepository
from app.domain.organizations.repository import OrganizationRepository
from app.domain.sync.port import CodeHostSource
from app.domain.teams.repository import TeamRepository
from app.domain.work_items.repository import WorkItemRepository

logger = logging.getLogger(__name__)

# ponytail: a codebase's first fetch reaches back BACKFILL; later fetches start
# OVERLAP before the last sync, or at its oldest pending deployment started within
# PENDING_REFRESH, whichever is earlier. A pending deployment is re-read until it
# settles or turns PENDING_REFRESH old, then it is treated as abandoned. If one
# ever matters, fetch the abandoned deployment by id. A repository whose deploy tool
# never posts deployment statuses (or whose deployments are superseded before a final
# status) keeps deployments PENDING, so each of its syncs fetches up to PENDING_REFRESH
# of deployments instead of about OVERLAP. That cost is expected and bounded, not a bug.
BACKFILL = timedelta(days=180)
OVERLAP = timedelta(days=1)
PENDING_REFRESH = timedelta(days=7)


@dataclass(frozen=True)
class CodeSyncSummary:
    """Counts of rows written by one code sync run."""

    organization_id: UUID
    # Created or renamed.
    codebases: int
    # Created or changed.
    pull_requests: int
    deployments: int
    # REVIEW/MERGED events inserted.
    events: int


class CodeSyncService:
    """Pulls a CodeHostSource into the codebases slice, idempotently.

    Codebases are matched by external_id across organizations and never
    pruned; new ones start unmapped and are never fetched until a team is set. Pull requests and
    deployments of mapped codebases are upserted by external_id (written only
    when changed). A final link pass turns stored pull requests into REVIEW and
    MERGED events of the work items their keys name, so items synced after the
    pull request, or rebuilt, are still linked. Running it twice is a no-op.
    """

    def __init__(  # noqa: PLR0913 — one port per repository the sync reads or writes
        self,
        source: CodeHostSource,
        organizations: OrganizationRepository,
        teams: TeamRepository,
        codebases: CodebaseRepository,
        pull_requests: PullRequestRepository,
        deployments: DeploymentRepository,
        work_items: WorkItemRepository,
        events: EventRepository,
    ) -> None:
        self._source = source
        self._organizations = organizations
        self._teams = teams
        self._codebases = codebases
        self._pull_requests = pull_requests
        self._deployments = deployments
        self._work_items = work_items
        self._events = events

    async def resolve_organization(self, organization_id: UUID | None) -> UUID:
        if organization_id is not None:
            if await self._organizations.get(organization_id) is None:
                raise UnknownOrganizationError(f"Organization {organization_id} does not exist")
            return organization_id
        existing = await self._organizations.list()
        if len(existing) == 1:
            return existing[0].id
        if len(existing) > 1:
            # ValueError on purpose: the global handler answers 422.
            raise ValueError("Multiple organizations exist; specify organization_id")
        raise ValueError("No organization yet; run a Linear sync first")

    async def sync(
        self,
        organization_id: UUID,
        *,
        now: datetime | None = None,
        on_phase: PhaseCallback | None = None,
    ) -> CodeSyncSummary:
        await self.resolve_organization(organization_id)
        now = now or utcnow()

        def report(phase: SyncPhase) -> None:
            if on_phase is not None:
                on_phase(phase)

        logger.info("Code sync started for organization %s", organization_id)
        report(SyncPhase.CODEBASES)
        written = await self._sync_codebases(organization_id)
        mapped = [c for c in await self._codebases.list(organization_id) if c.team_id is not None]
        report(SyncPhase.PULL_REQUESTS)
        pull_requests = sum([await self._fetch_pull_requests(c, now) for c in mapped])
        report(SyncPhase.DEPLOYMENTS)
        deployments = sum([await self._fetch_deployments(c, now) for c in mapped])
        events = await self._link(organization_id, mapped)
        await self._stamp(mapped, now)
        summary = CodeSyncSummary(organization_id, written, pull_requests, deployments, events)
        logger.info(
            "Code sync finished for organization %s: codebases=%d pull_requests=%d "
            "deployments=%d events=%d",
            organization_id,
            summary.codebases,
            summary.pull_requests,
            summary.deployments,
            summary.events,
        )
        return summary

    async def _stamp(self, fetched: list[Codebase], now: datetime) -> None:
        """Set last_synced_at on the fetched codebases, re-read so a concurrent edit survives."""
        for codebase in fetched:
            current = await self._codebases.get(codebase.id)
            if current is not None:
                await self._codebases.update(replace(current, last_synced_at=now))

    async def _sync_codebases(self, organization_id: UUID) -> int:
        """Add new codebases to this organization; rename stored ones, whoever owns them.

        Matched by external_id across all organizations (as the Linear sync
        matches teams): a codebase another organization already owns keeps its
        owner, so a second organization's sync never re-inserts it.
        """
        sources = await self._source.fetch_codebases()
        existing = await self._codebases.get_by_external_ids([s.external_id for s in sources])
        written = 0
        for source in sources:
            stored = existing.get(source.external_id)
            if stored is None:
                await self._codebases.add(
                    Codebase(
                        organization_id=organization_id,
                        name=source.name,
                        external_id=source.external_id,
                        url=source.url,
                    )
                )
            elif (stored.name, stored.url) != (source.name.strip(), source.url):
                await self._codebases.update(replace(stored, name=source.name, url=source.url))
            else:
                continue
            written += 1
        return written

    @staticmethod
    def _since(codebase: Codebase, now: datetime) -> datetime:
        if codebase.last_synced_at is None:
            return now - BACKFILL
        return codebase.last_synced_at - OVERLAP

    async def _fetch_pull_requests(self, codebase: Codebase, now: datetime) -> int:
        sources = await self._source.fetch_pull_requests(
            codebase.external_id, self._since(codebase, now)
        )
        rows = [
            PullRequest(
                codebase_id=codebase.id,
                external_id=s.external_id,
                number=s.number,
                title=s.title,
                opened_at=s.opened_at,
                url=s.url,
                first_commit_at=s.first_commit_at,
                merged_at=s.merged_at,
                closed_at=s.closed_at,
                merge_commit_sha=s.merge_commit_sha,
                work_item_keys=s.work_item_keys,
            )
            for s in sources
        ]
        return await _upsert(self._pull_requests, rows)

    async def _fetch_deployments(self, codebase: Codebase, now: datetime) -> int:
        since = self._since(codebase, now)
        pending = await self._deployments.oldest_pending_started_at(
            codebase.id, since=now - PENDING_REFRESH
        )
        if pending is not None:
            since = min(since, pending)
        sources = await self._source.fetch_deployments(codebase.external_id, since)
        rows = [
            Deployment(
                codebase_id=codebase.id,
                external_id=s.external_id,
                environment=s.environment,
                sha=s.sha,
                started_at=s.started_at,
                status=s.status,
                finished_at=s.finished_at,
            )
            for s in sources
        ]
        return await _upsert(self._deployments, rows)

    async def _link(self, organization_id: UUID, mapped: list[Codebase]) -> int:
        """Insert the REVIEW/MERGED events of every stored pull request that names a work item.

        Only work items of the syncing organization's teams are linked.
        """
        # ponytail: loads every stored pull request of the mapped codebases and
        # re-checks their events on each sync. Fine to tens of thousands of rows;
        # past that, link only pull requests changed since the last sync plus
        # those naming keys of newly synced items.
        names = {c.id: c.name for c in mapped}
        pull_requests = await self._pull_requests.list_for_codebases(list(names))
        keys = sorted({key for pr in pull_requests for key in pr.work_item_keys})
        team_ids = {t.id for t in await self._teams.list() if t.organization_id == organization_id}
        items = await self._work_items.get_by_keys(keys, team_ids=team_ids)
        candidates = [
            event
            for pr in pull_requests
            for key in pr.work_item_keys
            if key in items
            for event in _events_for(pr, names[pr.codebase_id], items[key].id)
        ]
        existing = await self._events.existing_external_ids(
            [e.external_id for e in candidates if e.external_id is not None]
        )
        fresh = [e for e in candidates if e.external_id not in existing]
        for event in fresh:
            await self._events.add(event)
        return len(fresh)


class _Upsertable[T: (PullRequest, Deployment)](Protocol):
    async def get_by_external_ids(self, external_ids: list[str]) -> dict[str, T]: ...

    async def add(self, row: T, /) -> None: ...

    async def update(self, row: T, /) -> None: ...


async def _upsert[T: (PullRequest, Deployment)](repository: _Upsertable[T], rows: list[T]) -> int:
    """Add new rows and update changed ones (matched by external_id); returns rows written.

    A row the source returned twice (updated mid-pagination) is written once,
    as its first, newest copy.
    """
    rows = list({row.external_id: row for row in reversed(rows)}.values())[::-1]
    stored = await repository.get_by_external_ids([r.external_id for r in rows])
    written = 0
    for row in rows:
        existing = stored.get(row.external_id)
        if existing is None:
            await repository.add(row)
        else:
            row = replace(row, id=existing.id)
            if row == existing:
                continue
            await repository.update(row)
        written += 1
    return written


def _events_for(pr: PullRequest, codebase_name: str, work_item_id: UUID) -> list[Event]:
    detail = f"{codebase_name}#{pr.number}"
    events = [
        Event(
            work_item_id=work_item_id,
            type=EventType.REVIEW,
            occurred_at=pr.opened_at,
            external_id=f"{pr.external_id}:review:{work_item_id}",
            detail=detail,
        )
    ]
    if pr.merged_at is not None:
        events.append(
            Event(
                work_item_id=work_item_id,
                type=EventType.MERGED,
                occurred_at=pr.merged_at,
                external_id=f"{pr.external_id}:merged:{work_item_id}",
                detail=detail,
            )
        )
    return events
