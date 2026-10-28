"""Linear syncs as in-process background jobs, one at a time.

One asyncio task (ADR-0002: no queue) runs the job. A request while a job
runs gets that job back when it covers the request (`covers`), or
`SyncBusyError` otherwise — never a second, overlapping sync. Every sync,
manual or automatic, holds `lock` and commits inside it, so the next sync
starts from this one's writes. A job is one session and one transaction
inside `recompute.paused()` (a running scope rewrite holds SQLite's write
lock): a failure or cancel rolls everything back. A cancelled job never
writes a finish state (CancelledError is not an Exception).

ponytail: job history lives in memory — the last HISTORY_SIZE finished
jobs, lost on restart (a client polling a lost job gets 404). Move to a
`sync_runs` table if outcomes must survive a restart.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import (
    metric_rules_service_for,
    snapshot_service_for,
    sync_schedule_service_for,
    sync_service_for,
)
from app.api.recompute import RecomputeRunner, get_recompute_runner
from app.application.metric_rules.service import ScopeRef
from app.application.sync.service import SyncPhase, SyncSummary
from app.domain._time import utcnow
from app.domain.sync.port import DataSourceError, DeliveryDataSource

logger = logging.getLogger(__name__)

HISTORY_SIZE = 20

SyncKind = Literal["organization", "team"]
SyncTrigger = Literal["manual", "auto"]
SyncState = Literal["running", "succeeded", "failed"]


@dataclass(frozen=True)
class SyncJobRequest:
    organization_id: UUID
    kind: SyncKind
    trigger: SyncTrigger
    team_id: UUID | None = None
    rebuild: bool = False

    def __post_init__(self) -> None:
        if (self.kind == "team") != (self.team_id is not None):
            raise ValueError("a team sync needs a team_id; an organization sync takes none")


@dataclass
class SyncJob:
    request: SyncJobRequest
    id: UUID = field(default_factory=uuid4)
    state: SyncState = "running"
    phase: SyncPhase | None = None
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    error: str | None = None
    summary: SyncSummary | None = None


def covers(running: SyncJobRequest, wanted: SyncJobRequest) -> bool:
    """Whether `running` already does everything `wanted` asks for.

    Same organization, and: an organization sync covers a plain organization
    sync and any of its team syncs; a rebuild only by a rebuild; a team sync
    covers only the same team.
    """
    if running.organization_id != wanted.organization_id:
        return False
    if wanted.rebuild:
        return running.rebuild
    if running.kind == "organization":
        return True
    return wanted.kind == "team" and wanted.team_id == running.team_id


class SyncBusyError(Exception):
    """A job is running that does not cover the request."""

    def __init__(self, job: SyncJob) -> None:
        super().__init__(
            f"A {job.request.kind} sync is already running (job {job.id}); try again when it ends"
        )
        self.job = job


class SyncJobRunner:
    """Runs Linear syncs one background job at a time."""

    def __init__(
        self, sessionmaker: async_sessionmaker[AsyncSession], *, recompute: RecomputeRunner
    ) -> None:
        self._sessionmaker = sessionmaker
        self._recompute = recompute
        self._running: SyncJob | None = None
        self._task: asyncio.Task[None] | None = None
        # Running and finished jobs by id, oldest first.
        self._jobs: dict[UUID, SyncJob] = {}
        # Held by every sync, manual or automatic: one at a time.
        self.lock = asyncio.Lock()

    @property
    def running(self) -> SyncJob | None:
        return self._running

    def get(self, job_id: UUID) -> SyncJob | None:
        return self._jobs.get(job_id)

    def start(self, request: SyncJobRequest, source: DeliveryDataSource) -> SyncJob:
        """Start a job and return it at once; or the running job, if it covers `request`."""
        running = self._running
        if running is not None:
            if covers(running.request, request):
                return running
            raise SyncBusyError(running)
        job, self._task = self._spawn(request, source)
        return job

    async def run(self, request: SyncJobRequest, source: DeliveryDataSource) -> SyncJob:
        """Wait for any running job, then run one to completion (a failure is in its state)."""
        while self._running is not None:
            await self.wait_idle()
        # No await since the check: nothing else can have claimed the runner.
        job, self._task = self._spawn(request, source)
        await self._task  # cancelling the caller cancels the job
        return job

    def _spawn(
        self, request: SyncJobRequest, source: DeliveryDataSource
    ) -> tuple[SyncJob, asyncio.Task[None]]:
        job = SyncJob(request)
        self._running = job
        self._jobs[job.id] = job
        task = asyncio.create_task(self._hold(job, source))
        # A done callback, not a `finally`: it also runs for a task cancelled
        # before its first step. Added first, so it runs before any awaiter wakes.
        task.add_done_callback(lambda _: self._release(job))
        return job, task

    def _release(self, job: SyncJob) -> None:
        if self._running is job:
            self._running = None
        while len(self._jobs) > HISTORY_SIZE:
            del self._jobs[next(iter(self._jobs))]

    async def wait_idle(self) -> None:
        """Until no job is in flight (tests, auto sync, shutdown)."""
        while (task := self._task) is not None and not task.done():
            await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        task = self._task
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _hold(self, job: SyncJob, source: DeliveryDataSource) -> None:
        async with self.lock:
            await self._execute(job, source)

    async def _execute(self, job: SyncJob, source: DeliveryDataSource) -> None:
        request = job.request
        try:
            async with self._recompute.paused() as queue, self._sessionmaker() as session:
                job.summary = await self._sync(session, job, source)
                scopes = await self._start_recompute(session, request)
                await session.commit()
                if request.rebuild:
                    queue(request.organization_id, scopes)
        except DataSourceError as exc:
            # Linear unreachable, an error response, or a malformed payload:
            # the message says which, so no traceback.
            logger.warning("Sync job %s failed for %s: %s", job.id, request.organization_id, exc)
            self._finish(job, error=str(exc) or type(exc).__name__)
        except Exception as exc:
            logger.exception("Sync job %s failed for %s", job.id, request.organization_id)
            self._finish(job, error=str(exc) or type(exc).__name__)
        else:
            logger.info("Sync job %s finished for %s", job.id, request.organization_id)
            self._finish(job, error=None)

    async def _sync(
        self, session: AsyncSession, job: SyncJob, source: DeliveryDataSource
    ) -> SyncSummary:
        """The sync, its snapshots and (manual organization sync) its schedule mark."""
        request = job.request

        def on_phase(phase: SyncPhase) -> None:
            job.phase = phase

        service = sync_service_for(session, source)
        snapshots = snapshot_service_for(session)
        if request.team_id is not None:  # a team sync (SyncJobRequest's invariant)
            summary = await service.sync_team(request.team_id, on_phase=on_phase)
            on_phase(SyncPhase.SNAPSHOTS)
            # One team's sync leaves the others stale: snapshot only its scopes.
            captured = await snapshots.capture_team(request.team_id)
        else:
            summary = await service.sync(
                request.organization_id, rebuild=request.rebuild, on_phase=on_phase
            )
            on_phase(SyncPhase.SNAPSHOTS)
            captured = await snapshots.capture_all()
        logger.info("Captured snapshots for %d scope(s) post-sync", captured)
        if request.trigger == "manual" and request.kind == "organization":
            # Skips a scheduled slot this sync made redundant (ADR-0014).
            await sync_schedule_service_for(session).record_manual_sync(request.organization_id)
        return summary

    async def _start_recompute(
        self, session: AsyncSession, request: SyncJobRequest
    ) -> tuple[ScopeRef, ...]:
        """On rebuild, mark the history rewrite running; its scopes (ADR-0013)."""
        if not request.rebuild:
            return ()
        # A rebuild rewrites stored events, so snapshot history computed from
        # the old ones is rewritten too.
        rules = metric_rules_service_for(session)
        scopes = await rules.organization_scopes(request.organization_id)
        await rules.start_recompute(request.organization_id)
        return scopes

    @staticmethod
    def _finish(job: SyncJob, *, error: str | None) -> None:
        job.state = "failed" if error is not None else "succeeded"
        job.error = error
        job.finished_at = utcnow()


def get_sync_job_runner(request: Request) -> SyncJobRunner:
    runner: SyncJobRunner | None = getattr(request.app.state, "sync_job_runner", None)
    if runner is None:  # no lifespan ran (tests): create on first use
        runner = SyncJobRunner(
            request.app.state.sessionmaker, recompute=get_recompute_runner(request)
        )
        request.app.state.sync_job_runner = runner
    return runner


SyncJobRunnerDep = Annotated[SyncJobRunner, Depends(get_sync_job_runner)]
