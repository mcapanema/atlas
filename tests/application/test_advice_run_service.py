from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.application.advisor.runs import INTERRUPTED, AdviceRunService
from app.domain.advisor.entities import DeliveryAdvice, Persona
from app.domain.advisor.runs import RunStatus, run_params
from tests.fakes import InMemoryAdviceRunRepository

NOW = datetime(2026, 7, 10, tzinfo=UTC)
PERSONA = Persona.AGILE_COACH


def _advice() -> DeliveryAdvice:
    return DeliveryAdvice(generated_at=NOW, summary="All good.", recommendations=())


def _service() -> tuple[AdviceRunService, InMemoryAdviceRunRepository]:
    runs = InMemoryAdviceRunRepository()
    return AdviceRunService(runs), runs


async def test_begin_creates_a_running_run() -> None:
    service, runs = _service()

    run, started = await service.begin(
        team_id=uuid4(),
        project_id=None,
        persona=PERSONA,
        params=run_params(window_days=30),
        now=NOW,
    )

    assert started is True
    assert run.status is RunStatus.RUNNING
    assert run.requested_at == NOW
    assert await runs.get(run.id) == run


async def test_begin_returns_the_running_run_for_the_same_key() -> None:
    service, _ = _service()
    team_id = uuid4()

    first, _ = await service.begin(
        team_id=team_id, project_id=None, persona=PERSONA, params="a=1", now=NOW
    )
    second, started = await service.begin(
        team_id=team_id,
        project_id=None,
        persona=PERSONA,
        params="a=1",
        now=NOW + timedelta(minutes=1),
    )

    assert started is False
    assert second.id == first.id


async def test_begin_starts_a_new_run_for_other_params() -> None:
    service, _ = _service()
    team_id = uuid4()

    first, _ = await service.begin(
        team_id=team_id,
        project_id=None,
        persona=PERSONA,
        params=run_params(window_days=30),
        now=NOW,
    )
    second, started = await service.begin(
        team_id=team_id,
        project_id=None,
        persona=PERSONA,
        params=run_params(window_days=60),
        now=NOW,
    )

    assert started is True
    assert second.id != first.id


async def test_begin_replaces_a_stale_running_run() -> None:
    service, runs = _service()
    team_id = uuid4()
    old, _ = await service.begin(
        team_id=team_id, project_id=None, persona=PERSONA, params="", now=NOW
    )

    new, started = await service.begin(
        team_id=team_id,
        project_id=None,
        persona=PERSONA,
        params="",
        now=NOW + timedelta(minutes=16),
    )

    assert started is True
    assert new.id != old.id
    failed = await runs.get(old.id)
    assert failed is not None
    assert failed.status is RunStatus.FAILED
    assert failed.error == "Abandoned; generate again."


async def test_begin_after_a_finished_run_starts_a_new_one() -> None:
    service, _ = _service()
    team_id = uuid4()
    old, _ = await service.begin(
        team_id=team_id, project_id=None, persona=PERSONA, params="", now=NOW
    )
    await service.succeed(old.id, _advice(), now=NOW)

    new, started = await service.begin(
        team_id=team_id,
        project_id=None,
        persona=PERSONA,
        params="",
        now=NOW + timedelta(minutes=1),
    )

    assert started is True
    assert new.id != old.id
    latest = await service.latest(team_id=team_id, project_id=None, persona=PERSONA, params="")
    assert latest == new


async def test_succeed_after_fail_is_ignored() -> None:
    service, runs = _service()
    run, _ = await service.begin(
        team_id=uuid4(), project_id=None, persona=PERSONA, params="", now=NOW
    )
    await service.fail(run.id, "boom", now=NOW)

    await service.succeed(run.id, _advice(), now=NOW)

    stored = await runs.get(run.id)
    assert stored is not None
    assert stored.status is RunStatus.FAILED
    assert stored.result is None


async def test_fail_interrupted_fails_every_running_run() -> None:
    service, runs = _service()
    first, _ = await service.begin(
        team_id=uuid4(), project_id=None, persona=PERSONA, params="", now=NOW
    )
    second, _ = await service.begin(
        team_id=None, project_id=uuid4(), persona=PERSONA, params="", now=NOW
    )

    assert await service.fail_interrupted(now=NOW) == 2

    for run_id in (first.id, second.id):
        stored = await runs.get(run_id)
        assert stored is not None
        assert stored.status is RunStatus.FAILED
        assert stored.error == INTERRUPTED
    assert await runs.list_running() == []
