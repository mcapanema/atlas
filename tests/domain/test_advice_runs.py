from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    Recommendation,
    TalkingPoint,
)
from app.domain.advisor.runs import AdviceRun, RunStatus, run_params

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
NAIVE = datetime(2026, 1, 1)  # noqa: DTZ001 — naive on purpose


def _advice() -> DeliveryAdvice:
    rec = Recommendation("t", "high", "p", "r", "a")
    return DeliveryAdvice(generated_at=NOW, summary="s", recommendations=(rec,))


def _prep() -> MeetingPrep:
    return MeetingPrep(
        meeting=MeetingType.PLANNING,
        generated_at=NOW,
        headline="h",
        talking_points=(TalkingPoint("p", "d"),),
    )


def _run(**kw: object) -> AdviceRun:
    args: dict[str, object] = {
        "persona": Persona.AGILE_COACH,
        "params": "window_days=30",
        "team_id": uuid4(),
    }
    args.update(kw)
    return AdviceRun(**args)  # type: ignore[arg-type]


def test_run_params_is_canonical() -> None:
    assert run_params(window_days=30) == "window_days=30"
    assert (
        run_params(window_days=None, remaining=5, target_date=date(2026, 12, 1))
        == "remaining=5&target_date=2026-12-01"
    )
    assert run_params(a=1, b=2) == run_params(b=2, a=1)


def test_new_run_is_running() -> None:
    run = _run()
    assert run.status is RunStatus.RUNNING
    assert run.result is None
    assert run.error is None
    assert run.finished_at is None
    assert run.requested_at.tzinfo is not None


def test_succeed_sets_result_and_finished_at() -> None:
    run = _run().succeed(_advice(), at=NOW)
    assert run.status is RunStatus.SUCCEEDED
    assert run.result == _advice()
    assert run.finished_at == NOW


def test_succeed_with_meeting_prep_under_meeting_persona() -> None:
    run = _run(persona=Persona.PLANNING).succeed(_prep(), at=NOW)
    assert run.status is RunStatus.SUCCEEDED


def test_fail_requires_an_error_message() -> None:
    failed = _run().fail("boom", at=NOW)
    assert failed.status is RunStatus.FAILED
    assert failed.error == "boom"
    assert failed.finished_at == NOW
    with pytest.raises(ValueError, match="non-blank error"):
        _run().fail("  ", at=NOW)


def test_rejects_both_or_neither_scope() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        _run(project_id=uuid4())
    with pytest.raises(ValueError, match="exactly one"):
        _run(team_id=None)


def test_rejects_meeting_prep_under_an_advisory_persona() -> None:
    with pytest.raises(ValueError, match="meeting persona"):
        _run().succeed(_prep(), at=NOW)
    with pytest.raises(ValueError, match="non-meeting persona"):
        _run(persona=Persona.PLANNING).succeed(_advice(), at=NOW)


def test_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _run(requested_at=NAIVE)
    with pytest.raises(ValueError, match="timezone-aware"):
        _run().fail("boom", at=NAIVE)


def test_rejects_inconsistent_running_state() -> None:
    with pytest.raises(ValueError, match="running run"):
        _run(finished_at=NOW)
    with pytest.raises(ValueError, match="running run"):
        _run(error="x")
    with pytest.raises(ValueError, match="succeeded run"):
        _run(status=RunStatus.SUCCEEDED, finished_at=NOW)
