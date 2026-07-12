"""Render a DeliveryContext as compact text.

Shared by the OpenRouter advisor's user message and the advice-context API
(and therefore MCP chat clients) — one renderer, one vocabulary. Pure
stdlib over Domain types; belongs to the advisor slice's data.
"""

from datetime import timedelta

from app.domain.advisor.port import DeliveryContext


def _days(delta: timedelta) -> str:
    return f"{delta / timedelta(days=1):.1f}d"


def render_context(context: DeliveryContext) -> str:
    """Render the computed metrics as compact text for an LLM."""
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
    if flow.queue_time is not None and flow.touch_time is not None:
        lines.append(
            f"- queue time p50={_days(flow.queue_time.p50)}, "
            f"touch time p50={_days(flow.touch_time.p50)}"
        )

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
