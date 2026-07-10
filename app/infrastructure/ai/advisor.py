"""OpenRouter adapter for the AdvisorPort.

The LLM explains metrics; it never computes them (VISION: "AI Explains,
Statistics Predict"). OpenRouter's OpenAI-compatible chat-completions API is
called directly with httpx (no provider SDK — same pattern as the Linear
connector); a strict JSON schema guarantees a parseable shape, and the
knowledge file grounds recommendations in named flow principles.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from app.domain.advisor.entities import DeliveryAdvice, Recommendation
from app.domain.advisor.port import DeliveryContext

_API_URL = "https://openrouter.ai/api/v1/chat/completions"

_KNOWLEDGE = (Path(__file__).parent / "knowledge" / "flow_coaching.md").read_text()

_SYSTEM_PROMPT = f"""You are Atlas's Agile Coach and Engineering Advisor. You help \
Engineering Managers improve software delivery using Lean and Kanban flow thinking.

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

{_KNOWLEDGE}"""


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


def _days(delta: timedelta) -> str:
    return f"{delta / timedelta(days=1):.1f}d"


def _render_context(context: DeliveryContext) -> str:
    """Render the computed metrics as compact text for the user message."""
    flow = context.flow
    flow_days = (flow.window_end - flow.window_start).days
    lines = [f"Flow metrics (trailing {flow_days} days, ending {flow.window_end.date()}):"]
    lines.append(f"- completed={flow.completed}, wip={flow.wip}")
    if flow.lead_time is not None:
        lt = flow.lead_time
        lines.append(
            f"- lead time p50={_days(lt.p50)}, p75={_days(lt.p75)}, "
            f"p85={_days(lt.p85)}, p95={_days(lt.p95)}, mean={_days(lt.mean)}"
        )
    else:
        lines.append("- lead time: no completed items in window")
    if flow.cycle_time is not None:
        ct = flow.cycle_time
        lines.append(f"- cycle time p50={_days(ct.p50)}, p85={_days(ct.p85)}")
    lines.append(f"- blocked time total={_days(flow.blocked_time)}")
    if flow.flow_efficiency is not None:
        lines.append(f"- flow efficiency={flow.flow_efficiency:.2f}")

    dist = context.distribution
    dist_days = (dist.window_end - dist.window_start).days
    if dist.bins:
        histogram = ", ".join(
            f"{b.start_days}-{b.end_days}d:{b.count}" for b in dist.bins if b.count
        )
        lines.append(f"Lead-time histogram (trailing {dist_days} days): {histogram}")
    else:
        lines.append(f"Lead-time histogram (trailing {dist_days} days): empty")

    forecast = context.forecast
    lines.append(f"Monte Carlo forecast: remaining={forecast.remaining} open items")
    if forecast.completion is not None:
        c = forecast.completion
        lines.append(
            f"- days to complete remaining scope ({c.trials} trials): "
            f"p50={c.p50_days}, p75={c.p75_days}, p85={c.p85_days}, p95={c.p95_days}"
        )
    else:
        lines.append("- no forecast (no historical throughput)")
    if forecast.confidence is not None:
        lines.append(f"- delivery confidence vs target date={forecast.confidence:.2f}")
    return "\n".join(lines)


class OpenRouterAdvisor:
    """AdvisorPort adapter backed by OpenRouter's chat-completions API."""

    def __init__(
        self, api_key: str, model: str, client: httpx.AsyncClient | None = None
    ) -> None:
        # `client` injection exists for tests; production opens a fresh client
        # per call (see advise()), same pattern as the Linear connector.
        self._injected_client = client
        self._api_key = api_key
        self._model = model

    async def advise(self, context: DeliveryContext) -> DeliveryAdvice:
        request_kwargs: dict[str, Any] = {
            "headers": {"Authorization": f"Bearer {self._api_key}"},
            "json": {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _render_context(context)},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "delivery_advice",
                        "strict": True,
                        "schema": AdviceOut.model_json_schema(),
                    },
                },
            },
        }
        if self._injected_client is not None:
            response = await self._injected_client.post(_API_URL, **request_kwargs)
        else:
            # ponytail: a fresh connection per call, same as the Linear
            # connector. Hold a pooled AsyncClient (with aclose() on app
            # shutdown) if sustained-throughput latency ever matters.
            # Generation takes tens of seconds — httpx's 5s default would
            # cut it off.
            async with httpx.AsyncClient(timeout=120.0) as owned_client:
                response = await owned_client.post(_API_URL, **request_kwargs)
        # ponytail: a failed generation (bad key, model without structured-output
        # support, no credits) propagates as HTTPStatusError → a 500 from our
        # API; the UI shows its generic error alert. Map to friendlier statuses
        # only if that ever matters.
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed = AdviceOut.model_validate_json(content)
        return DeliveryAdvice(
            generated_at=datetime.now(UTC),
            summary=parsed.summary,
            recommendations=[
                Recommendation(
                    title=r.title,
                    priority=r.priority,
                    problem=r.problem,
                    root_cause=r.root_cause,
                    action=r.action,
                    evidence=r.evidence,
                )
                for r in parsed.recommendations
            ],
        )
