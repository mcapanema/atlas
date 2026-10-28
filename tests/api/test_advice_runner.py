import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from unittest import mock
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.advice_runner import AdviceRunner
from app.api.deps import advice_run_service_for, persona_service_for
from app.domain.advisor.entities import (
    AdviceFeedback,
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
)
from app.domain.advisor.port import AdvisorError, DeliveryContext, MeetingContext
from app.domain.advisor.runs import AdviceRun, RunStatus, run_params
from app.domain.organizations.entities import Organization
from app.domain.teams.entities import Team
from app.infrastructure.repositories.advice_runs import SqlAlchemyAdviceRunRepository
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository

Sessions = async_sessionmaker[AsyncSession]


class FakePort:
    """An AdvisorPort double: records its calls, optionally blocks or raises."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls = 0
        self.guidance: list[str | None] = []
        self.error = error
        self.release: asyncio.Event | None = None
        self.on_call: list[Any] = []

    async def _called(self, guidance: str | None) -> None:
        self.calls += 1
        self.guidance.append(guidance)
        for hook in self.on_call:
            hook()
        if self.release is not None:
            await self.release.wait()
        if self.error is not None:
            raise self.error

    async def advise(
        self,
        context: DeliveryContext,
        *,
        persona: Persona = Persona.AGILE_COACH,
        guidance: str | None = None,
    ) -> DeliveryAdvice:
        await self._called(guidance)
        return DeliveryAdvice(
            generated_at=datetime(2026, 10, 28, tzinfo=UTC),
            summary="Flow is healthy.",
            recommendations=(),
        )

    async def prepare_meeting(
        self,
        context: MeetingContext,
        *,
        meeting: MeetingType,
        guidance: str | None = None,
    ) -> MeetingPrep:
        await self._called(guidance)
        return MeetingPrep(
            meeting=meeting,
            generated_at=datetime(2026, 10, 28, tzinfo=UTC),
            headline="Nothing is stuck.",
            talking_points=(),
        )

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        raise NotImplementedError


async def _team(sessionmaker: Sessions) -> UUID:
    async with sessionmaker() as session:
        org = Organization(name="Acme")
        await SqlAlchemyOrganizationRepository(session).add(org)
        team = Team(organization_id=org.id, name="Platform")
        await SqlAlchemyTeamRepository(session).add(team)
        await session.commit()
    return team.id


async def _stored(sessionmaker: Sessions, run: AdviceRun) -> AdviceRun:
    async with sessionmaker() as session:
        stored = await advice_run_service_for(session).latest(
            team_id=run.team_id, project_id=run.project_id, persona=run.persona, params=run.params
        )
    assert stored is not None
    return stored


async def _start(runner: AdviceRunner, port: FakePort, team_id: UUID) -> AdviceRun:
    return await runner.start_advice(
        port, team_id=team_id, project_id=None, persona=Persona.AGILE_COACH, window_days=30
    )


async def test_start_advice_stores_the_result(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    runner = AdviceRunner(file_sessionmaker)

    run = await _start(runner, FakePort(), team_id)
    assert run.status is RunStatus.RUNNING
    assert run.params == run_params(window_days=30)
    await runner.wait_idle()

    stored = await _stored(file_sessionmaker, run)
    assert stored.id == run.id
    assert stored.status is RunStatus.SUCCEEDED
    assert isinstance(stored.result, DeliveryAdvice)
    assert stored.result.summary == "Flow is healthy."


async def test_port_runs_without_an_open_session(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    sessions: list[AsyncSession] = []

    class RecordingSession(AsyncSession):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            sessions.append(self)

    recording: Sessions = async_sessionmaker(
        file_sessionmaker.kw["bind"], class_=RecordingSession, expire_on_commit=False
    )
    runner = AdviceRunner(recording)
    port = FakePort()
    in_transaction: list[list[bool]] = []
    port.on_call.append(lambda: in_transaction.append([s.in_transaction() for s in sessions]))

    await _start(runner, port, team_id)
    await runner.wait_idle()

    assert len(in_transaction) == 1
    assert in_transaction[0]  # the runner opened sessions before the call
    assert not any(in_transaction[0])


async def test_second_start_for_the_same_key_reuses_the_run(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    runner = AdviceRunner(file_sessionmaker)
    port = FakePort()
    port.release = asyncio.Event()
    latest = SqlAlchemyAdviceRunRepository.latest

    async def slow_latest(self: SqlAlchemyAdviceRunRepository, **key: Any) -> AdviceRun | None:
        found = await latest(self, **key)
        await asyncio.sleep(0.05)  # widen the read-then-insert window in `begin`
        return found

    with mock.patch.object(SqlAlchemyAdviceRunRepository, "latest", slow_latest):
        first, second = await asyncio.gather(
            _start(runner, port, team_id), _start(runner, port, team_id)
        )
    third = await _start(runner, port, team_id)
    port.release.set()
    await runner.wait_idle()

    assert first.id == second.id == third.id
    assert port.calls == 1
    assert (await _stored(file_sessionmaker, first)).status is RunStatus.SUCCEEDED


async def test_advisor_error_marks_the_run_failed(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    runner = AdviceRunner(file_sessionmaker)

    run = await _start(runner, FakePort(error=AdvisorError("OpenRouter request failed")), team_id)
    await runner.wait_idle()

    stored = await _stored(file_sessionmaker, run)
    assert stored.status is RunStatus.FAILED
    assert stored.error == "OpenRouter request failed"


async def test_unexpected_error_marks_the_run_failed(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    runner = AdviceRunner(file_sessionmaker)

    run = await _start(runner, FakePort(error=RuntimeError()), team_id)
    await runner.wait_idle()

    stored = await _stored(file_sessionmaker, run)
    assert stored.status is RunStatus.FAILED
    assert stored.error == "RuntimeError"


async def test_start_meeting_prep_uses_the_meeting_persona_guidance(
    file_sessionmaker: Sessions,
) -> None:
    team_id = await _team(file_sessionmaker)
    async with file_sessionmaker() as session:
        personas = persona_service_for(session)
        await personas.add_guidance(Persona.DAILY_STANDUP, "Lead with stuck items.")
        await personas.add_guidance(Persona.AGILE_COACH, "Not this one.")
        await session.commit()
    runner = AdviceRunner(file_sessionmaker)
    port = FakePort()

    run = await runner.start_meeting_prep(
        port,
        team_id=team_id,
        project_id=None,
        meeting=MeetingType.DAILY_STANDUP,
        window_days=None,
        remaining=5,
        target_date=None,
    )
    await runner.wait_idle()

    assert run.persona is Persona.DAILY_STANDUP
    assert run.params == run_params(remaining=5)
    assert port.guidance == ["Lead with stuck items."]
    stored = await _stored(file_sessionmaker, run)
    assert stored.status is RunStatus.SUCCEEDED
    assert isinstance(stored.result, MeetingPrep)


async def test_close_cancels_a_running_task_without_writing(file_sessionmaker: Sessions) -> None:
    team_id = await _team(file_sessionmaker)
    runner = AdviceRunner(file_sessionmaker)
    port = FakePort()
    port.release = asyncio.Event()
    entered = asyncio.Event()
    port.on_call.append(entered.set)

    run = await _start(runner, port, team_id)
    await asyncio.wait_for(entered.wait(), 5)
    await runner.close()

    assert (await _stored(file_sessionmaker, run)).status is RunStatus.RUNNING
