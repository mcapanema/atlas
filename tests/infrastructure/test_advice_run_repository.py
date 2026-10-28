from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    Recommendation,
    TalkingPoint,
)
from app.domain.advisor.runs import AdviceRun, RunStatus
from app.infrastructure.repositories.advice_runs import SqlAlchemyAdviceRunRepository

_T0 = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _advice() -> DeliveryAdvice:
    return DeliveryAdvice(
        generated_at=_T0,
        summary="Flow is slowing.",
        recommendations=(
            Recommendation(
                title="Cap WIP",
                priority="high",
                problem="Too much in progress",
                root_cause="No limits",
                action="Set a WIP limit of 3",
                evidence=("wip=9", "cycle_time=12d"),
            ),
            Recommendation(
                title="Slice work",
                priority="low",
                problem="Big items",
                root_cause="Vague scope",
                action="Split stories",
            ),
        ),
    )


async def test_round_trips_a_succeeded_advice_run(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceRunRepository(session)
    run = AdviceRun(
        persona=Persona.AGILE_COACH,
        params="window_days=30",
        team_id=uuid4(),
        requested_at=_T0,
    ).succeed(_advice(), at=_T0 + timedelta(seconds=5))
    await repo.add(run)
    session.expire_all()

    assert await repo.get(run.id) == run


async def test_round_trips_a_succeeded_meeting_prep_run(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceRunRepository(session)
    prep = MeetingPrep(
        meeting=MeetingType.RETROSPECTIVE,
        generated_at=_T0,
        headline="Talk about review latency",
        talking_points=(
            TalkingPoint(
                point="Reviews stall",
                detail="Median 3 days",
                evidence=("review_time=3d",),
                needs_decision=True,
            ),
            TalkingPoint(point="Celebrate", detail="Shipped X"),
        ),
    )
    run = AdviceRun(
        persona=Persona.RETROSPECTIVE,
        params="",
        project_id=uuid4(),
        requested_at=_T0,
    ).succeed(prep, at=_T0 + timedelta(seconds=5))
    await repo.add(run)
    session.expire_all()

    got = await repo.get(run.id)
    assert got == run
    assert got is not None
    assert isinstance(got.result, MeetingPrep)
    assert got.result.talking_points[0].needs_decision is True


async def test_get_unknown_returns_none(session: AsyncSession) -> None:
    assert await SqlAlchemyAdviceRunRepository(session).get(uuid4()) is None


async def test_latest_picks_the_newest_for_the_key_only(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceRunRepository(session)
    team = uuid4()

    def make(
        minutes: int,
        persona: Persona = Persona.AGILE_COACH,
        params: str = "a=1",
        team_id: UUID | None = team,
        project_id: UUID | None = None,
    ) -> AdviceRun:
        return AdviceRun(
            persona=persona,
            params=params,
            team_id=team_id,
            project_id=project_id,
            requested_at=_T0 + timedelta(minutes=minutes),
        )

    old, new = make(1), make(2)
    noise = [
        make(9, persona=Persona.DELIVERY_ANALYST),
        make(9, params="a=2"),
        make(9, team_id=uuid4()),
        make(9, team_id=None, project_id=uuid4()),
    ]
    for run in (new, old, *noise):
        await repo.add(run)

    got = await repo.latest(
        team_id=team, project_id=None, persona=Persona.AGILE_COACH, params="a=1"
    )
    assert got == new
    missing = await repo.latest(
        team_id=uuid4(), project_id=None, persona=Persona.AGILE_COACH, params="a=1"
    )
    assert missing is None


async def test_update_writes_status_and_finished_at(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceRunRepository(session)
    run = AdviceRun(persona=Persona.AGILE_COACH, params="", team_id=uuid4(), requested_at=_T0)
    await repo.add(run)

    failed = run.fail("boom", at=_T0 + timedelta(seconds=3))
    await repo.update(failed)
    session.expire_all()

    got = await repo.get(run.id)
    assert got == failed
    assert got is not None
    assert got.status is RunStatus.FAILED


async def test_list_running(session: AsyncSession) -> None:
    repo = SqlAlchemyAdviceRunRepository(session)
    running = AdviceRun(persona=Persona.AGILE_COACH, params="", team_id=uuid4(), requested_at=_T0)
    done = AdviceRun(
        persona=Persona.AGILE_COACH, params="", team_id=uuid4(), requested_at=_T0
    ).fail("x", at=_T0)
    await repo.add(running)
    await repo.add(done)

    assert await repo.list_running() == [running]
