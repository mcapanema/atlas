from datetime import UTC, datetime, timedelta

from app.domain.advisor.port import DeliveryContext
from app.domain.advisor.render import render_context
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    OutcomeBucket,
)
from app.domain.metrics.distribution import DurationBin, LeadTimeDistribution
from app.domain.metrics.summary import DurationStats, FlowMetrics

_NOW = datetime(2026, 7, 10, tzinfo=UTC)


def _context() -> DeliveryContext:
    stats = DurationStats(
        p50=timedelta(days=3),
        p75=timedelta(days=5),
        p85=timedelta(days=8),
        p95=timedelta(days=13),
        mean=timedelta(days=4, hours=12),
    )
    flow = FlowMetrics(
        window_start=_NOW - timedelta(days=30),
        window_end=_NOW,
        completed=12,
        wip=5,
        lead_time=stats,
        cycle_time=stats,
        blocked_time=timedelta(days=2),
        flow_efficiency=0.42,
    )
    distribution = LeadTimeDistribution(
        window_start=_NOW - timedelta(days=90),
        window_end=_NOW,
        bins=(DurationBin(start_days=0, end_days=1, count=3),),
    )
    forecast = DeliveryForecast(
        window_start=_NOW - timedelta(days=90),
        window_end=_NOW,
        remaining=14,
        completion=CompletionForecast(
            trials=500,
            remaining=14,
            p50_days=10,
            p75_days=14,
            p85_days=17,
            p95_days=23,
            outcomes=(OutcomeBucket(days=10, trials=250),),
        ),
        confidence=0.72,
    )
    return DeliveryContext(flow=flow, distribution=distribution, forecast=forecast)


def test_render_context_includes_key_figures() -> None:
    text = render_context(_context())
    assert "completed=12" in text
    assert "wip=5" in text
    assert "remaining=14" in text
    assert "3.0d" in text  # lead time p50 rendered in days
    assert "0.42" in text  # flow efficiency


def test_render_context_handles_empty_scope() -> None:
    empty = DeliveryContext(
        flow=FlowMetrics(
            window_start=_NOW - timedelta(days=30),
            window_end=_NOW,
            completed=0,
            wip=0,
            lead_time=None,
            cycle_time=None,
            blocked_time=timedelta(0),
            flow_efficiency=None,
        ),
        distribution=LeadTimeDistribution(
            window_start=_NOW - timedelta(days=90), window_end=_NOW, bins=()
        ),
        forecast=DeliveryForecast(
            window_start=_NOW - timedelta(days=90),
            window_end=_NOW,
            remaining=0,
            completion=None,
            confidence=None,
        ),
    )
    text = render_context(empty)
    assert "no completed items" in text
    assert "no forecast" in text
