"""Automatic Linear and GitHub sync on each organization's schedule (ADR-0014).

One in-process asyncio task (ADR-0002: no queue, no cron) ticks every
TICK_SECONDS, starting at once so a slot missed while Atlas was off
catches up on startup. Each tick asks SyncScheduleService which
organizations have a slot due and syncs them one at a time. That's the
same sync + snapshot capture as `POST /api/connectors/linear/sync`, run as
a SyncJobRunner job (its own session and transaction). The outcome is recorded on the schedule in a
second session, so a failed sync's rollback can't erase its own error.
When GitHub is configured, a Linear sync that succeeds is followed by a code
sync (a `code` job); its failure logs a warning and does not change the
recorded outcome, which is the Linear one.
An upstream failure (DataSourceError) logs a one-line warning; anything
else logs a traceback. A failure still consumes its slot: no retry until
the next one. Each slot is also attempted at most once per process, so a
run whose outcome can't be recorded isn't re-synced every tick; a restart
retries it once.

Manual and automatic syncs share the job runner's lock. A tick that finds
a sync running skips and retries next tick; a manual sync while an auto
sync runs gets that job back when it covers the request, a 409 otherwise.

ponytail: one scheduler per process, so run Atlas as a single uvicorn
worker (the Dockerfile does). Move to a DB lease or a job table if Atlas
ever runs several workers.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import LINEAR_NOT_CONFIGURED, sync_schedule_service_for
from app.api.sync_jobs import SyncJobRequest, SyncJobRunner
from app.application.sync_schedules.service import DueSync
from app.domain.sync.port import CodeHostSource, DeliveryDataSource

logger = logging.getLogger(__name__)

TICK_SECONDS = 60.0
_NEVER = datetime.min.replace(tzinfo=UTC)


class AutoSyncRunner:
    """Runs scheduled syncs, one organization at a time."""

    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        source_factory: Callable[[], DeliveryDataSource | None],
        *,
        jobs: SyncJobRunner,
        code_source_factory: Callable[[], CodeHostSource | None] = lambda: None,
        tick_seconds: float = TICK_SECONDS,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._source_factory = source_factory
        self._jobs = jobs
        self._code_source_factory = code_source_factory
        self._tick_seconds = tick_seconds
        self._task: asyncio.Task[None] | None = None
        # The last slot attempted per organization, recorded or not.
        self._attempted: dict[UUID, datetime] = {}

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if not self.running:
            self._task = asyncio.create_task(self._loop())

    async def close(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def tick(self) -> int:
        """Sync every organization with a due slot; how many ran (0 while a sync is running)."""
        if self._jobs.lock.locked():
            return 0
        async with self._sessionmaker() as session:
            due = [
                job
                for job in await sync_schedule_service_for(session).due()
                if job.slot_at > self._attempted.get(job.organization_id, _NEVER)
            ]
        for slot in due:
            self._attempted[slot.organization_id] = slot.slot_at
            await self._record(slot, await self._sync(slot.organization_id))
        return len(due)

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Auto-sync tick failed")
            await asyncio.sleep(self._tick_seconds)

    async def _sync(self, organization_id: UUID) -> str | None:
        """Run one organization's sync job; the error message, if it failed."""
        source = self._source_factory()
        if source is None:
            logger.warning("Auto sync skipped for %s: %s", organization_id, LINEAR_NOT_CONFIGURED)
            return LINEAR_NOT_CONFIGURED
        job = await self._jobs.run(SyncJobRequest(organization_id, "organization", "auto"), source)
        if job.error is None:
            await self._sync_code(organization_id)
        return job.error

    async def _sync_code(self, organization_id: UUID) -> None:
        """Pull GitHub after a good Linear sync; a failure only logs."""
        code_source = self._code_source_factory()
        if code_source is None:
            return
        job = await self._jobs.run_code(
            SyncJobRequest(organization_id, "code", "auto"), code_source
        )
        if job.error is not None:
            logger.warning("Auto code sync of %s failed: %s", organization_id, job.error)

    async def _record(self, job: DueSync, error: str | None) -> None:
        try:
            async with self._sessionmaker() as session:
                await sync_schedule_service_for(session).record_run(
                    job.organization_id, job.slot_at, error=error
                )
                await session.commit()
        except Exception:
            logger.exception("Could not record the auto sync of %s", job.organization_id)
