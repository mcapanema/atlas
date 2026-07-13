from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.domain.advisor.port import DeliveryContext, MeetingContext
from app.domain.advisor.render import render_context, render_meeting_context
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    OutcomeBucket,
)
from app.domain.metrics.aging import AgingItem, AgingWip
from app.domain.metrics.distribution import DurationBin, LeadTimeDistribution
from app.domain.metrics.health import DeliveryHealth, HealthComponent
from app.domain.metrics.summary import DurationStats, FlowMetrics

_NOW = datetime(2026, 7, 10, tzinfo=UTC)
_START = _NOW - timedelta(days=30)


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


def _delivery() -> DeliveryContext:
    return DeliveryContext(
        flow=FlowMetrics(
            window_start=_START,
            window_end=_NOW,
            completed=3,
            wip=4,
            lead_time=None,
            cycle_time=None,
            blocked_time=timedelta(0),
            flow_efficiency=None,
        ),
        distribution=LeadTimeDistribution(window_start=_START, window_end=_NOW, bins=()),
        forecast=DeliveryForecast(
            window_start=_START, window_end=_NOW, remaining=2, completion=None, confidence=None
        ),
    )


def _aging_item(title: str, days: int, over: bool) -> AgingItem:
    return AgingItem(
        work_item_id=uuid4(),
        title=title,
        state="In Progress",
        age=timedelta(days=days),
        over_p85=over,
    )


def test_render_meeting_context_includes_health_and_aging() -> None:
    context = MeetingContext(
        delivery=_delivery(),
        health=DeliveryHealth(
            window_start=_START,
            window_end=_NOW,
            score=61,
            band="warning",
            components=(
                HealthComponent(name="efficiency", score=42, reason="flow efficiency 42%"),
            ),
        ),
        aging=AgingWip(
            now=_NOW,
            cycle_time_p85=timedelta(days=4),
            items=(_aging_item("Fix login", 6, True),),
        ),
    )

    text = render_meeting_context(context)

    assert render_context(_delivery()) in text  # the advisor digest is embedded whole
    assert "Delivery health: 61/100 (warning)" in text
    assert "- efficiency 42: flow efficiency 42%" in text
    assert "Aging WIP (cycle-time p85 = 4.0d):" in text
    assert "- Fix login — In Progress, 6.0d [over p85]" in text


def test_render_meeting_context_handles_missing_health_and_empty_aging() -> None:
    context = MeetingContext(
        delivery=_delivery(),
        health=DeliveryHealth(
            window_start=_START, window_end=_NOW, score=None, band=None, components=()
        ),
        aging=AgingWip(now=_NOW, cycle_time_p85=None, items=()),
    )

    text = render_meeting_context(context)

    assert "Delivery health: not enough data to score." in text
    assert "Aging WIP: nothing in progress." in text


def test_render_meeting_context_caps_aging_at_ten_items() -> None:
    items = tuple(_aging_item(f"Item {i}", 12 - i, False) for i in range(12))
    context = MeetingContext(
        delivery=_delivery(),
        health=DeliveryHealth(
            window_start=_START, window_end=_NOW, score=None, band=None, components=()
        ),
        aging=AgingWip(now=_NOW, cycle_time_p85=None, items=items),
    )

    text = render_meeting_context(context)

    assert "- Item 9 —" in text
    assert "- Item 10 —" not in text
    assert "... and 2 more" in text
