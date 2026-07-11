from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.forecasting.accuracy import evaluate_forecast_accuracy
from app.domain.snapshots.entities import ForecastSnapshot

ORIGIN = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
TEAM = uuid4()


def _snapshot(
    *, remaining: int = 2, p50: int | None = 5, p85: int | None = 10
) -> ForecastSnapshot:
    return ForecastSnapshot(
        captured_on=ORIGIN.date(),
        window_days=90,
        remaining=remaining,
        p50_days=p50,
        p85_days=p85,
        team_id=TEAM,
        created_at=ORIGIN,
    )


def _completions(*day_offsets: int) -> list[datetime]:
    return [ORIGIN + timedelta(days=offset) for offset in day_offsets]


def test_resolved_forecast_within_both_percentiles_hits() -> None:
    accuracy = evaluate_forecast_accuracy([_snapshot()], _completions(2, 4))

    assert accuracy.evaluated == 1
    assert accuracy.pending == 0
    assert accuracy.p50_hit_rate == 1.0
    assert accuracy.p85_hit_rate == 1.0
    assert accuracy.mean_abs_error_days == 1.0  # actual 4d vs p50 5d


def test_resolved_forecast_beyond_p85_misses_both() -> None:
    accuracy = evaluate_forecast_accuracy([_snapshot()], _completions(2, 12))

    assert accuracy.evaluated == 1
    assert accuracy.p50_hit_rate == 0.0
    assert accuracy.p85_hit_rate == 0.0
    assert accuracy.mean_abs_error_days == 7.0  # actual 12d vs p50 5d


def test_unresolved_forecast_is_pending() -> None:
    accuracy = evaluate_forecast_accuracy([_snapshot()], _completions(2))

    assert accuracy.evaluated == 0
    assert accuracy.pending == 1
    assert accuracy.p50_hit_rate is None
    assert accuracy.mean_abs_error_days is None


def test_completions_before_capture_do_not_count() -> None:
    accuracy = evaluate_forecast_accuracy([_snapshot()], _completions(-3, 2))

    assert accuracy.evaluated == 0
    assert accuracy.pending == 1


def test_snapshot_without_prediction_is_ignored() -> None:
    accuracy = evaluate_forecast_accuracy(
        [_snapshot(p50=None, p85=None), _snapshot(remaining=0)], _completions(1)
    )

    assert accuracy.evaluated == 0
    assert accuracy.pending == 0


def test_no_snapshots_yields_empty_accuracy() -> None:
    accuracy = evaluate_forecast_accuracy([], [])

    assert accuracy.evaluated == 0
    assert accuracy.pending == 0
    assert accuracy.p85_hit_rate is None


def test_mixed_snapshots_average_hit_rates() -> None:
    hit = _snapshot()                      # resolves at 4d: hits both
    miss = _snapshot(p50=1, p85=3)         # resolves at 4d: misses both

    accuracy = evaluate_forecast_accuracy([hit, miss], _completions(2, 4))

    assert accuracy.evaluated == 2
    assert accuracy.p50_hit_rate == 0.5
    assert accuracy.p85_hit_rate == 0.5
    assert accuracy.mean_abs_error_days == 2.0  # |4-5| and |4-1|
