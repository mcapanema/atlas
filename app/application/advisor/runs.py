"""Lifecycle of stored advice / meeting-prep generation runs."""

from datetime import datetime, timedelta
from uuid import UUID

from app.domain.advisor.entities import DeliveryAdvice, MeetingPrep, Persona
from app.domain.advisor.repository import AdviceRunRepository
from app.domain.advisor.runs import AdviceRun, RunStatus

STALE_RUN_AFTER = timedelta(minutes=15)
INTERRUPTED = "Interrupted by a restart; generate again."
ABANDONED = "Abandoned; generate again."


class AdviceRunService:
    def __init__(self, runs: AdviceRunRepository) -> None:
        self._runs = runs

    async def begin(
        self,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        persona: Persona,
        params: str,
        now: datetime,
    ) -> tuple[AdviceRun, bool]:
        """Start a run, or return the live one for the same key as `(run, False)`."""
        current = await self._runs.latest(
            team_id=team_id, project_id=project_id, persona=persona, params=params
        )
        if current is not None and current.status is RunStatus.RUNNING:
            if now - current.requested_at < STALE_RUN_AFTER:
                return current, False
            await self._runs.update(current.fail(ABANDONED, at=now))
        run = AdviceRun(
            persona=persona,
            params=params,
            team_id=team_id,
            project_id=project_id,
            requested_at=now,
        )
        await self._runs.add(run)
        return run, True

    async def latest(
        self,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        persona: Persona,
        params: str,
    ) -> AdviceRun | None:
        return await self._runs.latest(
            team_id=team_id, project_id=project_id, persona=persona, params=params
        )

    async def succeed(
        self, run_id: UUID, result: DeliveryAdvice | MeetingPrep, *, now: datetime
    ) -> None:
        run = await self._runs.get(run_id)
        if run is not None and run.status is RunStatus.RUNNING:
            await self._runs.update(run.succeed(result, at=now))

    async def fail(self, run_id: UUID, error: str, *, now: datetime) -> None:
        run = await self._runs.get(run_id)
        if run is not None and run.status is RunStatus.RUNNING:
            await self._runs.update(run.fail(error, at=now))

    async def fail_interrupted(self, *, now: datetime) -> int:
        running = await self._runs.list_running()
        for run in running:
            await self._runs.update(run.fail(INTERRUPTED, at=now))
        return len(running)
