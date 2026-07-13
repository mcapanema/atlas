import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from app.domain.advisor.entities import AdviceFeedback, MeetingType, Persona
from app.domain.advisor.port import AdvisorError, DeliveryContext, MeetingContext
from app.domain.advisor.render import render_context
from app.domain.forecasting.monte_carlo import (
    CompletionForecast,
    DeliveryForecast,
    OutcomeBucket,
)
from app.domain.metrics.aging import AgingWip
from app.domain.metrics.distribution import DurationBin, LeadTimeDistribution
from app.domain.metrics.health import DeliveryHealth, HealthComponent
from app.domain.metrics.summary import DurationStats, FlowMetrics
from app.infrastructure.ai.advisor import (
    AdviceOut,
    MeetingPrepOut,
    OpenRouterAdvisor,
    RecommendationOut,
    TalkingPointOut,
    _knowledge,
    _meeting_system_prompt,
    _system_prompt,
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


def test_knowledge_file_is_read_once() -> None:
    _knowledge.cache_clear()
    prompt = _system_prompt(Persona.AGILE_COACH)
    assert "Little's Law" in prompt  # knowledge base is embedded
    _system_prompt(Persona.AGILE_COACH)
    assert _knowledge.cache_info().misses == 1


def test_system_prompt_appends_learned_guidance() -> None:
    base = _system_prompt(Persona.AGILE_COACH)
    grown = _system_prompt(Persona.AGILE_COACH, "Prefer WIP actions over staffing advice.")
    assert grown.startswith(base)  # static base is untouched; learning only appends
    assert "Learned guidance" in grown
    assert "Prefer WIP actions" in grown
    assert _system_prompt(Persona.AGILE_COACH, None) == base


async def test_advise_puts_guidance_in_the_system_message() -> None:
    payload: dict[str, Any] = {
        "choices": [{"message": {"content": _advice_out().model_dump_json()}}]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    await advisor.advise(_context(), guidance="Prefer WIP actions over staffing advice.")

    body = json.loads(captured[0].content)
    assert "Prefer WIP actions" in body["messages"][0]["content"]


def test_system_prompt_varies_by_persona() -> None:
    coach = _system_prompt(Persona.AGILE_COACH)
    analyst = _system_prompt(Persona.DELIVERY_ANALYST)

    assert "Agile Coach" in coach
    assert "Delivery Analyst" in analyst
    assert coach != analyst
    # the shared grounding rules survive in every persona
    assert "never invent numbers" in coach and "never invent numbers" in analyst


def test_render_context_includes_queue_and_touch_time() -> None:
    now = datetime(2026, 7, 10, tzinfo=UTC)
    start = now - timedelta(days=30)
    stats = DurationStats(
        p50=timedelta(days=2), p75=timedelta(days=3), p85=timedelta(days=4),
        p95=timedelta(days=5), mean=timedelta(days=2, hours=12),
    )
    context = DeliveryContext(
        flow=FlowMetrics(
            window_start=start, window_end=now, completed=1, wip=0,
            lead_time=stats, cycle_time=stats, blocked_time=timedelta(0),
            flow_efficiency=1.0, queue_time=stats, touch_time=stats,
        ),
        distribution=LeadTimeDistribution(window_start=start, window_end=now, bins=()),
        forecast=DeliveryForecast(
            window_start=start, window_end=now, remaining=0, completion=None, confidence=None
        ),
    )

    text = render_context(context)

    assert "queue time p50=2.0d" in text
    assert "touch time p50=2.0d" in text


def _feedback_entries() -> list[AdviceFeedback]:
    return [
        AdviceFeedback(
            persona=Persona.AGILE_COACH,
            rating="down",
            advice_summary="Add staff to the team.",
            comment="staffing advice is out of my control",
            created_at=_NOW,
        ),
        AdviceFeedback(
            persona=Persona.AGILE_COACH,
            rating="up",
            advice_summary="Set a WIP limit of 4.",
            created_at=_NOW,
        ),
    ]


async def test_reflect_returns_distilled_guidance_and_sends_feedback() -> None:
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"guidance": "Prefer WIP actions."})}}
        ]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    guidance = await advisor.reflect(
        persona=Persona.AGILE_COACH,
        feedback=_feedback_entries(),
        current_guidance="Be concise.",
    )

    assert guidance == "Prefer WIP actions."
    body = json.loads(captured[0].content)
    assert body["response_format"]["json_schema"]["name"] == "persona_guidance"
    user_message = body["messages"][1]["content"]
    assert "staffing advice is out of my control" in user_message
    assert "[down]" in user_message and "[up]" in user_message
    assert "Be concise." in user_message  # current guidance is offered for carry-over
    assert "Agile Coach" in body["messages"][0]["content"]


async def test_reflect_raises_on_blank_guidance() -> None:
    payload = {"choices": [{"message": {"content": json.dumps({"guidance": "  "})}}]}
    advisor = _advisor_returning(httpx.Response(200, json=payload))

    with pytest.raises(AdvisorError, match="empty guidance"):
        await advisor.reflect(
            persona=Persona.AGILE_COACH, feedback=_feedback_entries(), current_guidance=None
        )


async def test_reflect_raises_advisor_error_on_api_error() -> None:
    advisor = _advisor_returning(httpx.Response(500, json={}))

    with pytest.raises(AdvisorError, match="request failed"):
        await advisor.reflect(
            persona=Persona.AGILE_COACH, feedback=_feedback_entries(), current_guidance=None
        )


def _sequenced_client(
    responses: list[httpx.Response], captured: list[httpx.Request]
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return responses[len(captured) - 1]

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_self_critique_runs_draft_critique_revise() -> None:
    revised = AdviceOut(summary="Revised after critique.", recommendations=[])
    responses = [
        httpx.Response(
            200, json={"choices": [{"message": {"content": _advice_out().model_dump_json()}}]}
        ),
        httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Evidence 'wip=99' is not in the metrics."}}
                ]
            },
        ),
        httpx.Response(
            200, json={"choices": [{"message": {"content": revised.model_dump_json()}}]}
        ),
    ]
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _sequenced_client(responses, captured),
        self_critique=True,
    )

    advice = await advisor.advise(_context())

    assert advice.summary == "Revised after critique."
    assert len(captured) == 3
    critique_body = json.loads(captured[1].content)
    assert "response_format" not in critique_body  # critique is free text
    assert "wip=5" in critique_body["messages"][1]["content"]  # sees the metrics
    revise_body = json.loads(captured[2].content)
    assert revise_body["messages"][2]["role"] == "assistant"  # draft is in-context
    assert "wip=99" in revise_body["messages"][3]["content"]  # critique is quoted
    assert revise_body["response_format"]["json_schema"]["name"] == "delivery_advice"


async def test_self_critique_off_is_a_single_call() -> None:
    payload: dict[str, Any] = {
        "choices": [{"message": {"content": _advice_out().model_dump_json()}}]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    await advisor.advise(_context())

    assert len(captured) == 1


def _meeting_context() -> MeetingContext:
    return MeetingContext(
        delivery=_context(),
        health=DeliveryHealth(
            window_start=_NOW - timedelta(days=30),
            window_end=_NOW,
            score=61,
            band="warning",
            components=(
                HealthComponent(name="efficiency", score=42, reason="flow efficiency 42%"),
            ),
        ),
        aging=AgingWip(now=_NOW, cycle_time_p85=timedelta(days=4), items=()),
    )


def _prep_out() -> MeetingPrepOut:
    return MeetingPrepOut(
        headline="One item is past the p85 age line.",
        talking_points=[
            TalkingPointOut(
                point="Unstick 'Fix login'",
                detail="In progress 6.0d against a 4.0d p85.",
                evidence=["cycle-time p85 = 4.0d"],
                needs_decision=True,
            )
        ],
    )


async def test_prepare_meeting_maps_structured_output_to_domain() -> None:
    payload: dict[str, Any] = {
        "choices": [{"message": {"content": _prep_out().model_dump_json()}}]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    prep = await advisor.prepare_meeting(_meeting_context(), meeting=MeetingType.DAILY_STANDUP)

    assert prep.meeting is MeetingType.DAILY_STANDUP
    assert prep.headline == "One item is past the p85 age line."
    assert prep.talking_points[0].needs_decision is True
    assert prep.talking_points[0].evidence == ("cycle-time p85 = 4.0d",)
    assert prep.generated_at.tzinfo is not None
    (request,) = captured
    body = json.loads(request.content)
    assert body["response_format"]["json_schema"]["name"] == "meeting_prep"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"]["additionalProperties"] is False
    # the user message carries the full meeting digest, health and aging included
    assert "Delivery health: 61/100 (warning)" in body["messages"][1]["content"]
    assert "completed=12" in body["messages"][1]["content"]


def test_meeting_system_prompt_varies_by_meeting_and_keeps_grounding() -> None:
    standup = _meeting_system_prompt(MeetingType.DAILY_STANDUP)
    retro = _meeting_system_prompt(MeetingType.RETROSPECTIVE)
    planning = _meeting_system_prompt(MeetingType.PLANNING)

    assert "Standup Facilitator" in standup
    assert "Retrospective Facilitator" in retro
    assert "Planning Facilitator" in planning
    assert standup != retro != planning
    for prompt in (standup, retro, planning):
        assert "never invent numbers" in prompt  # shared grounding survives
        assert "Little's Law" in prompt  # knowledge base is embedded


def test_meeting_system_prompt_appends_learned_guidance() -> None:
    base = _meeting_system_prompt(MeetingType.PLANNING)
    grown = _meeting_system_prompt(MeetingType.PLANNING, "Always show p95.")

    assert grown.startswith(base)  # static base untouched; learning only appends
    assert "Always show p95." in grown


async def test_prepare_meeting_raises_advisor_error_on_bad_shape() -> None:
    payload = {"choices": [{"message": {"content": json.dumps({"nope": 1})}}]}
    advisor = _advisor_returning(httpx.Response(200, json=payload))

    with pytest.raises(AdvisorError, match="unexpected shape"):
        await advisor.prepare_meeting(_meeting_context(), meeting=MeetingType.PLANNING)


async def test_prepare_meeting_raises_advisor_error_on_api_error() -> None:
    advisor = _advisor_returning(httpx.Response(500, json={}))

    with pytest.raises(AdvisorError, match="request failed"):
        await advisor.prepare_meeting(_meeting_context(), meeting=MeetingType.RETROSPECTIVE)


async def test_reflect_works_for_meeting_personas() -> None:
    # _PERSONA_ROLE must cover meeting personas or reflect() raises KeyError.
    payload = {
        "choices": [
            {"message": {"content": json.dumps({"guidance": "Lead with stuck items."})}}
        ]
    }
    captured: list[httpx.Request] = []
    advisor = OpenRouterAdvisor(
        api_key="test-key",
        model="anthropic/claude-sonnet-5",
        client_factory=lambda: _mock_client(httpx.Response(200, json=payload), captured),
    )

    guidance = await advisor.reflect(
        persona=Persona.DAILY_STANDUP,
        feedback=[
            AdviceFeedback(
                persona=Persona.DAILY_STANDUP,
                rating="up",
                advice_summary="Good prep.",
                created_at=_NOW,
            )
        ],
        current_guidance=None,
    )

    assert guidance == "Lead with stuck items."
    body = json.loads(captured[0].content)
    assert "Standup Facilitator" in body["messages"][0]["content"]
