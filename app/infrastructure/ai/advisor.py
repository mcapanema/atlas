"""OpenRouter adapter for the AdvisorPort.

The LLM explains metrics; it never computes them (VISION: "AI Explains,
Statistics Predict"). OpenRouter's OpenAI-compatible chat-completions API is
called directly with httpx (no provider SDK — same pattern as the Linear
connector); a strict JSON schema guarantees a parseable shape, and the
knowledge file grounds recommendations in named flow principles.
"""

import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.domain.advisor.entities import (
    AdviceFeedback,
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    Recommendation,
    TalkingPoint,
    meeting_persona,
)
from app.domain.advisor.port import AdvisorError, DeliveryContext, MeetingContext
from app.domain.advisor.render import render_context, render_meeting_context

_API_URL = "https://openrouter.ai/api/v1/chat/completions"

logger = logging.getLogger(__name__)

_PERSONA_ROLE: dict[Persona, str] = {
    Persona.AGILE_COACH: (
        "You are Atlas's Agile Coach. Focus on Lean and Kanban flow: bottlenecks, "
        "waste, WIP discipline, anti-patterns, and the single most valuable process "
        "improvement to make next."
    ),
    Persona.ENGINEERING_ADVISOR: (
        "You are Atlas's Engineering Advisor. Focus on team execution: delivery "
        "capacity, risk, staffing signals, and where management attention is "
        "needed first."
    ),
    Persona.PROJECT_ADVISOR: (
        "You are Atlas's Project Advisor. Focus on delivery planning: forecasts, "
        "deadlines, dependencies, milestones, and whether the current scope will "
        "land on time."
    ),
    Persona.DELIVERY_ANALYST: (
        "You are Atlas's Delivery Analyst. Focus on the metrics themselves: "
        "distributions, trends, outliers, and historical comparisons — a deep, "
        "numbers-first read of the delivery data."
    ),
    Persona.DAILY_STANDUP: (
        "You are Atlas's Standup Facilitator. Focus on today's execution: stuck "
        "and blocked items, WIP discipline, and what needs a decision in the "
        "next 24 hours."
    ),
    Persona.RETROSPECTIVE: (
        "You are Atlas's Retrospective Facilitator. Focus on how the last "
        "iteration actually flowed: trends, weak delivery-health components, "
        "and open questions worth a team discussion."
    ),
    Persona.PLANNING: (
        "You are Atlas's Planning Facilitator. Focus on whether the plan is "
        "realistic: forecast dates, confidence against targets, and what to "
        "drop or move to make commitments credible."
    ),
}


_CRITIQUE_PROMPT = (
    "You review draft delivery advice before it reaches an Engineering "
    "Manager. Check, tersely and concretely: (1) every evidence value "
    "literally appears in the provided metrics; (2) each root cause actually "
    "follows from the evidence; (3) each action is one concrete next step; "
    "(4) priorities match impact. List only real problems, one line each. "
    "If the draft is sound, reply exactly: No issues."
)


@lru_cache(maxsize=1)
def _knowledge() -> str:
    return (Path(__file__).parent / "knowledge" / "flow_coaching.md").read_text()


def _system_prompt(persona: Persona, guidance: str | None = None) -> str:
    """Compose the persona prompt: static role + knowledge base + learned guidance.

    The static parts are the immutable safe base; learning (the reflected
    guidance note) can only append — it can never rewrite the persona.
    """
    prompt = f"""{_PERSONA_ROLE[persona]} You help Engineering Managers improve \
software delivery using Lean and Kanban flow thinking.

Ground every claim in the knowledge base below and in the metrics provided by \
the user message. You never compute metrics yourself and never invent numbers: \
every evidence entry must quote a value that literally appears in the provided \
metrics (e.g. "wip=12", "lead time p85=8.0d").

Rules:
- Write for an Engineering Manager: plain language, no jargon without a gloss.
- Produce a short delivery summary (3-6 sentences) describing what is actually \
happening, then 1 to 5 recommendations ordered most important first.
- Each recommendation names the problem, its most likely root cause given the \
evidence, and one concrete next action.
- If the data is too sparse to support a recommendation, say so in the summary \
and return fewer (or zero) recommendations rather than speculating.

Knowledge base:

{_knowledge()}"""
    if guidance:
        prompt += (
            "\n\nLearned guidance (distilled from Engineering Manager feedback on "
            "your past advice; follow it unless it conflicts with the rules above):\n\n"
            f"{guidance}"
        )
    return prompt


_MEETING_INSTRUCTIONS: dict[MeetingType, str] = {
    MeetingType.DAILY_STANDUP: (
        "Prepare talking points for today's daily standup. Report, in order: "
        "items over the cycle-time p85 age line (by name), anything blocked, and "
        "how WIP compares to the recent completion rate. At most 10 points, "
        "ordered by what needs a decision in the meeting; mark those with "
        "needs_decision. Flag anything the data cannot answer instead of guessing."
    ),
    MeetingType.RETROSPECTIVE: (
        "Prepare talking points for a retrospective covering the flow window in "
        "the metrics. Contrast that window against the trailing 90-day "
        "distribution, call out the weakest delivery-health components, and "
        "propose 2-3 discussion topics phrased as open questions for the team — "
        "not verdicts — each grounded in a quoted number. Note explicitly where "
        "the window is too small to trust a trend."
    ),
    MeetingType.PLANNING: (
        "Prepare talking points for a planning session. Report the p50/p85/p95 "
        "completion outlook and, when present, the confidence against the target "
        "date; say plainly what would have to be dropped or moved for the plan "
        "to be realistic. Recommend committing at p85, not p50, with a "
        "one-sentence reason."
    ),
}


def _meeting_system_prompt(meeting: MeetingType, guidance: str | None = None) -> str:
    """Compose the meeting-prep prompt: persona role + task + knowledge + learning.

    Same append-only learning contract as _system_prompt: the static parts
    are the immutable safe base; guidance can only append.
    """
    prompt = f"""{_PERSONA_ROLE[meeting_persona(meeting)]} You help Engineering \
Managers run better meetings using Lean and Kanban flow thinking.

Ground every claim in the knowledge base below and in the metrics provided by \
the user message. You never compute metrics yourself and never invent numbers: \
every evidence entry must quote a value that literally appears in the provided \
metrics (e.g. "wip=12", "lead time p85=8.0d").

{_MEETING_INSTRUCTIONS[meeting]}

Rules:
- Write for an Engineering Manager: plain language, no jargon without a gloss.
- Produce a one-sentence headline naming the single most important thing, then \
the talking points, most important first.
- Each talking point has a short point, a detail explaining it, and evidence \
quoting the supporting values.
- If the data is too sparse, say so in the headline and return fewer (or zero) \
talking points rather than speculating.

Knowledge base:

{_knowledge()}"""
    if guidance:
        prompt += (
            "\n\nLearned guidance (distilled from Engineering Manager feedback on "
            "your past meeting preps; follow it unless it conflicts with the rules "
            f"above):\n\n{guidance}"
        )
    return prompt


class RecommendationOut(BaseModel):
    """Structured-output shape for one recommendation (wire format only)."""

    # extra="forbid" renders additionalProperties: false, which strict
    # JSON-schema mode requires on every object.
    model_config = ConfigDict(extra="forbid")

    title: str
    priority: Literal["high", "medium", "low"]
    problem: str
    root_cause: str
    action: str
    evidence: list[str]


class AdviceOut(BaseModel):
    """Structured-output shape for the whole response (wire format only)."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    recommendations: list[RecommendationOut]


class GuidanceOut(BaseModel):
    """Structured-output shape for a reflected guidance note (wire format only)."""

    model_config = ConfigDict(extra="forbid")

    guidance: str


class TalkingPointOut(BaseModel):
    """Structured-output shape for one talking point (wire format only)."""

    model_config = ConfigDict(extra="forbid")

    point: str
    detail: str
    evidence: list[str]
    needs_decision: bool


class MeetingPrepOut(BaseModel):
    """Structured-output shape for a meeting prep (wire format only)."""

    model_config = ConfigDict(extra="forbid")

    headline: str
    talking_points: list[TalkingPointOut]


_ADVICE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "delivery_advice",
        "strict": True,
        "schema": AdviceOut.model_json_schema(),
    },
}

_GUIDANCE_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "persona_guidance",
        "strict": True,
        "schema": GuidanceOut.model_json_schema(),
    },
}

_MEETING_FORMAT: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "meeting_prep",
        "strict": True,
        "schema": MeetingPrepOut.model_json_schema(),
    },
}


def _render_feedback(feedback: Sequence[AdviceFeedback]) -> str:
    # ponytail: unbounded list in the prompt; cap or pre-summarize at ~50
    # entries if reflections ever bloat the context window.
    lines = []
    for entry in feedback:
        line = f"- [{entry.rating}] advice: {entry.advice_summary}"
        if entry.comment:
            line += f" | EM comment: {entry.comment}"
        lines.append(line)
    return "\n".join(lines)


def _message_content(response: httpx.Response) -> str:
    """Validate the chat-completions envelope before indexing into it."""
    try:
        envelope = response.json()
    except ValueError as exc:
        raise AdvisorError("OpenRouter response is not JSON") from exc
    try:
        content = envelope["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AdvisorError(
            "OpenRouter response missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str):
        raise AdvisorError("OpenRouter message content is not a string")
    return content


class OpenRouterAdvisor:
    """AdvisorPort adapter backed by OpenRouter's chat-completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        *,
        self_critique: bool = False,
    ) -> None:
        # One code path serves tests and production: tests inject a factory
        # returning a MockTransport-backed client; production builds a real
        # one per call. Generation takes tens of seconds — httpx's 5s default
        # timeout would cut it off.
        # ponytail: a fresh connection per call, same as the Linear connector.
        # Hold a pooled AsyncClient (with aclose() on app shutdown) if
        # sustained-throughput latency ever matters.
        self._client_factory = client_factory or (
            lambda: httpx.AsyncClient(timeout=120.0)
        )
        self._api_key = api_key
        self._model = model
        self._self_critique = self_critique

    async def _complete(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        body: dict[str, Any] = {"model": self._model, "messages": messages}
        if response_format is not None:
            body["response_format"] = response_format
        try:
            response = await client.post(
                _API_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("OpenRouter request failed: %s", exc)
            raise AdvisorError(f"OpenRouter request failed: {exc}") from exc
        return _message_content(response)

    async def advise(
        self,
        context: DeliveryContext,
        *,
        persona: Persona = Persona.AGILE_COACH,
        guidance: str | None = None,
    ) -> DeliveryAdvice:
        user_content = render_context(context)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _system_prompt(persona, guidance)},
            {"role": "user", "content": user_content},
        ]
        async with self._client_factory() as client:
            content = await self._complete(client, messages, _ADVICE_FORMAT)
            if self._self_critique:
                # ponytail: fixed single critique round (~3x cost); make the
                # round count configurable only if quality data ever demands it.
                critique = await self._complete(
                    client,
                    [
                        {"role": "system", "content": _CRITIQUE_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                f"Metrics provided to the advisor:\n{user_content}\n\n"
                                f"Draft advice JSON:\n{content}"
                            ),
                        },
                    ],
                )
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            f"A reviewer critiqued your draft:\n{critique}\n\n"
                            "Produce the final advice, fixing every valid point. "
                            "Same JSON schema as before."
                        ),
                    },
                ]
                content = await self._complete(client, messages, _ADVICE_FORMAT)
        try:
            parsed = AdviceOut.model_validate_json(content)
        except ValidationError as exc:
            # ValidationError is a ValueError; letting it escape would hit the
            # global ValueError handler and blame the client with a 422.
            logger.error("OpenRouter reply did not match the advice schema: %s", exc)
            raise AdvisorError("OpenRouter returned advice in an unexpected shape") from exc
        return DeliveryAdvice(
            generated_at=datetime.now(UTC),
            summary=parsed.summary,
            recommendations=tuple(
                Recommendation(
                    title=r.title,
                    priority=r.priority,
                    problem=r.problem,
                    root_cause=r.root_cause,
                    action=r.action,
                    evidence=tuple(r.evidence),
                )
                for r in parsed.recommendations
            ),
        )

    async def prepare_meeting(
        self,
        context: MeetingContext,
        *,
        meeting: MeetingType,
        guidance: str | None = None,
    ) -> MeetingPrep:
        # ponytail: no self-critique round for meeting prep — reuse advise()'s
        # draft-critique-revise pattern here if prep quality ever demands it.
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _meeting_system_prompt(meeting, guidance)},
            {"role": "user", "content": render_meeting_context(context)},
        ]
        async with self._client_factory() as client:
            content = await self._complete(client, messages, _MEETING_FORMAT)
        try:
            parsed = MeetingPrepOut.model_validate_json(content)
        except ValidationError as exc:
            logger.error("OpenRouter reply did not match the meeting-prep schema: %s", exc)
            raise AdvisorError(
                "OpenRouter returned meeting prep in an unexpected shape"
            ) from exc
        return MeetingPrep(
            meeting=meeting,
            generated_at=datetime.now(UTC),
            headline=parsed.headline,
            talking_points=tuple(
                TalkingPoint(
                    point=p.point,
                    detail=p.detail,
                    evidence=tuple(p.evidence),
                    needs_decision=p.needs_decision,
                )
                for p in parsed.talking_points
            ),
        )

    async def reflect(
        self,
        *,
        persona: Persona,
        feedback: Sequence[AdviceFeedback],
        current_guidance: str | None,
    ) -> str:
        system = f"""{_PERSONA_ROLE[persona]}

You maintain this persona's "learned guidance" — a short note appended to your \
system prompt on every future advice request, distilled from Engineering \
Manager feedback on your past advice.

Rewrite the guidance note now:
- Keep it under 200 words, as imperative bullet points.
- Carry forward still-useful points from the current note; drop anything the \
new feedback contradicts.
- Generalize durable preferences ("lead with the single highest-impact \
action"), not one-off details.
- Never weaken the grounding rules: metrics are computed elsewhere and \
numbers are never invented."""
        user = (
            f"Current guidance note:\n{current_guidance or '(none yet)'}\n\n"
            f"Feedback since the last reflection:\n{_render_feedback(feedback)}"
        )
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        async with self._client_factory() as client:
            content = await self._complete(client, messages, _GUIDANCE_FORMAT)
        try:
            parsed = GuidanceOut.model_validate_json(content)
        except ValidationError as exc:
            logger.error("OpenRouter reply did not match the guidance schema: %s", exc)
            raise AdvisorError(
                "OpenRouter returned guidance in an unexpected shape"
            ) from exc
        if not parsed.guidance.strip():
            raise AdvisorError("OpenRouter returned empty guidance")
        return parsed.guidance
