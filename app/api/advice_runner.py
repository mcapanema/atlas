"""Advice and meeting prep generated in background asyncio tasks, stored as runs.

`start_*` records a running `AdviceRun` and returns it at once; one asyncio
task per run (ADR-0002: no queue) generates the result. Runs for different
keys (scope + persona + params) are independent LLM calls and run
concurrently; a start for a key that already has a live run returns that run
and starts nothing. `begin` + commit are serialized under one lock, so a
double click makes one run — and the task never reads an uncommitted row.

A task never holds a transaction across the LLM call: one session builds
the context and reads the persona guidance, then commits and closes; the
port runs with no open session; a second session stores the outcome. A
cancelled task (shutdown) writes nothing (CancelledError is not an
Exception) — the next startup's `fail_interrupted` fails the row.

ponytail: one process, tasks not durable — a restart loses in-flight runs
(failed as interrupted at startup). Move to a job table + worker if advice
generation outgrows one process (same ceiling as `recompute.py`).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import advice_run_service_for, advisor_service_for, persona_service_for
from app.domain._time import utcnow
from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    meeting_persona,
)
from app.domain.advisor.port import AdvisorError, AdvisorPort
from app.domain.advisor.runs import AdviceRun, run_params

logger = logging.getLogger(__name__)

Result = DeliveryAdvice | MeetingPrep
# Reads what the LLM call needs inside `session`; returns the call itself,
# to run once that session is closed.
Prepare = Callable[[AsyncSession], Awaitable[Callable[[], Awaitable[Result]]]]


class AdviceRunner:
    """Runs advice / meeting-prep generations as background tasks."""

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker
        # Strong references: the event loop keeps only weak ones to tasks.
        self._tasks: set[asyncio.Task[None]] = set()
        self._lock = asyncio.Lock()

    async def start_advice(
        self,
        port: AdvisorPort,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        persona: Persona,
        window_days: int,
    ) -> AdviceRun:
        async def prepare(session: AsyncSession) -> Callable[[], Awaitable[Result]]:
            context = await advisor_service_for(session).build_context(
                team_id=team_id, project_id=project_id, window_days=window_days
            )
            active = await persona_service_for(session).active_guidance(persona)
            guidance = active.guidance if active else None
            return lambda: port.advise(context, persona=persona, guidance=guidance)

        return await self._start(
            team_id=team_id,
            project_id=project_id,
            persona=persona,
            params=run_params(window_days=window_days),
            prepare=prepare,
        )

    async def start_meeting_prep(
        self,
        port: AdvisorPort,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        meeting: MeetingType,
        window_days: int | None,
        remaining: int | None,
        target_date: date | None,
    ) -> AdviceRun:
        persona = meeting_persona(meeting)

        async def prepare(session: AsyncSession) -> Callable[[], Awaitable[Result]]:
            context = await advisor_service_for(session).build_meeting_context(
                meeting=meeting,
                team_id=team_id,
                project_id=project_id,
                window_days=window_days,
                remaining=remaining,
                target_date=target_date,
            )
            active = await persona_service_for(session).active_guidance(persona)
            guidance = active.guidance if active else None
            return lambda: port.prepare_meeting(context, meeting=meeting, guidance=guidance)

        return await self._start(
            team_id=team_id,
            project_id=project_id,
            persona=persona,
            params=run_params(
                window_days=window_days, remaining=remaining, target_date=target_date
            ),
            prepare=prepare,
        )

    async def _start(
        self,
        *,
        team_id: UUID | None,
        project_id: UUID | None,
        persona: Persona,
        params: str,
        prepare: Prepare,
    ) -> AdviceRun:
        # `begin` awaits between its read and its insert: unserialized, two
        # concurrent starts for one key would both insert.
        async with self._lock:
            async with self._sessionmaker() as session:
                run, created = await advice_run_service_for(session).begin(
                    team_id=team_id,
                    project_id=project_id,
                    persona=persona,
                    params=params,
                    now=utcnow(),
                )
                await session.commit()
            if created:
                task = asyncio.create_task(self._run(run.id, prepare))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        return run

    async def _run(self, run_id: UUID, prepare: Prepare) -> None:
        try:
            async with self._sessionmaker() as session:
                call = await prepare(session)
                # Release the read transaction before the LLM call — holding it
                # open would block every SQLite writer for up to
                # ATLAS_ADVISOR_TIMEOUT_SECONDS.
                await session.commit()
            result = await call()
        except AdvisorError as exc:
            logger.warning("Advice run %s failed: %s", run_id, exc)
            await self._finish(run_id, str(exc) or type(exc).__name__)
        except Exception as exc:
            logger.exception("Advice run %s failed", run_id)
            await self._finish(run_id, str(exc) or type(exc).__name__)
        else:
            await self._finish(run_id, result)

    async def _finish(self, run_id: UUID, outcome: Result | str) -> None:
        """Store the result, or the error message (a `str`)."""
        try:
            async with self._sessionmaker() as session:
                service = advice_run_service_for(session)
                if isinstance(outcome, str):
                    await service.fail(run_id, outcome, now=utcnow())
                else:
                    await service.succeed(run_id, outcome, now=utcnow())
                await session.commit()
        except Exception:
            # The row stays running until it goes stale (STALE_RUN_AFTER).
            logger.exception("Could not store the outcome of advice run %s", run_id)

    async def fail_interrupted(self) -> None:
        """Fail every run a restart left running (lifespan).

        Holds the start lock, so a run started during startup is never
        mistaken for an interrupted one once this has begun.
        """
        try:
            async with self._lock, self._sessionmaker() as session:
                count = await advice_run_service_for(session).fail_interrupted(now=utcnow())
                await session.commit()
        except Exception:
            logger.exception("Could not fail interrupted advice runs")
            return
        if count:
            logger.info("Failed %d advice run(s) interrupted by a restart", count)

    async def wait_idle(self) -> None:
        """Until no run is in flight (tests, shutdown).

        `asyncio.wait`, not `gather`: cancelling a waiter must not cancel a run.
        """
        async with self._lock:  # a start in progress has created its task once released
            pass
        while self._tasks:
            await asyncio.wait(set(self._tasks))

    async def close(self) -> None:
        tasks = set(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def get_advice_runner(request: Request) -> AdviceRunner:
    runner: AdviceRunner | None = getattr(request.app.state, "advice_runner", None)
    if runner is None:  # no lifespan ran (tests): create on first use
        runner = AdviceRunner(request.app.state.sessionmaker)
        request.app.state.advice_runner = runner
    return runner


AdviceRunnerDep = Annotated[AdviceRunner, Depends(get_advice_runner)]
