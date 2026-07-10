import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.domain.advisor.port import AdvisorError, DeliveryContext
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    OutcomeBucket,
)
from app.domain.metrics.distribution import DurationBin, LeadTimeDistribution
from app.domain.metrics.summary import DurationStats, FlowMetrics
from app.infrastructure.ai.advisor import (
    AdviceOut,
    OpenRouterAdvisor,
    RecommendationOut,
    _render_context,
)

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
        bins=[DurationBin(start_days=0, end_days=1, count=3)],
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
            outcomes=[OutcomeBucket(days=10, trials=250)],
        ),
        confidence=0.72,
    )
    return DeliveryContext(flow=flow, distribution=distribution, forecast=forecast)


def test_render_context_includes_key_figures() -> None:
    text = _render_context(_context())
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
            window_start=_NOW - timedelta(days=90), window_end=_NOW, bins=[]
        ),
        forecast=DeliveryForecast(
            window_start=_NOW - timedelta(days=90),
            window_end=_NOW,
            remaining=0,
            completion=None,
            confidence=None,
        ),
    )
    text = _render_context(empty)
    assert "no completed items" in text
    assert "no forecast" in text


def _mock_client(
    handler_response: httpx.Response, captured: list[httpx.Request]
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler_response

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _advice_out() -> AdviceOut:
    return AdviceOut(
        summary="Flow is healthy.",
        recommendations=[
            RecommendationOut(
                title="Lower WIP",
                priority="high",
                problem="WIP is 5 with throughput 12/30d",
                root_cause="Work is started faster than it finishes",
                action="Set a WIP limit of 4",
                evidence=["wip=5", "completed=12"],
            )
        ],
    )


async def test_advise_maps_structured_output_to_domain() -> None:
    payload: dict[str, Any] = {
        "choices": [{"message": {"content": _advice_out().model_dump_json()}}]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    advice = await advisor.advise(_context())

    assert advice.summary == "Flow is healthy."
    assert advice.recommendations[0].title == "Lower WIP"
    assert advice.recommendations[0].priority == "high"
    assert advice.generated_at.tzinfo is not None
    (request,) = captured
    assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["model"] == "anthropic/claude-sonnet-5"
    assert "completed=12" in body["messages"][1]["content"]
    assert body["response_format"]["json_schema"]["strict"] is True
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False


async def test_advise_raises_advisor_error_on_api_error() -> None:
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(
            httpx.Response(402, json={"error": {"message": "insufficient credits"}}), []
        ),
    )

    with pytest.raises(AdvisorError, match="request failed"):
        await advisor.advise(_context())


def _advisor_returning(response: httpx.Response) -> OpenRouterAdvisor:
    return OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(response, []),
    )


async def test_advise_raises_advisor_error_on_empty_choices() -> None:
    advisor = _advisor_returning(httpx.Response(200, json={"choices": []}))

    with pytest.raises(AdvisorError, match="choices"):
        await advisor.advise(_context())


async def test_advise_raises_advisor_error_on_missing_content() -> None:
    advisor = _advisor_returning(
        httpx.Response(200, json={"choices": [{"message": {}}]})
    )

    with pytest.raises(AdvisorError, match="choices"):
        await advisor.advise(_context())


async def test_advise_raises_advisor_error_when_model_ignores_schema() -> None:
    # A model that ignores the JSON schema must NOT surface as a pydantic
    # ValidationError (a ValueError → global handler blames the client, 422).
    payload = {"choices": [{"message": {"content": json.dumps({"nope": 1})}}]}
    advisor = _advisor_returning(httpx.Response(200, json=payload))

    with pytest.raises(AdvisorError, match="unexpected shape"):
        await advisor.advise(_context())


async def test_advise_raises_advisor_error_on_non_json_body() -> None:
    advisor = _advisor_returning(httpx.Response(200, text="<html>gateway</html>"))

    with pytest.raises(AdvisorError, match="not JSON"):
        await advisor.advise(_context())
