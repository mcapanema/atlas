"""Render advisor inputs as compact text.

Shared by the OpenRouter advisor's user message, the advice-context API and
the MCP chat tools — one renderer, one vocabulary. Pure stdlib over Domain
types; belongs to the advisor slice's data.
"""

import json
from datetime import timedelta

from app.domain.advisor.port import DeliveryContext, MeetingContext
from app.domain.metrics.aging import AgingWip


def _days(delta: timedelta) -> str:
    """A duration in working days, named so it isn't read as calendar days."""
    return f"{delta / timedelta(days=1):.1f} working days"


def render_context(context: DeliveryContext) -> str:
    """Render the computed metrics as compact text for an LLM."""
    flow = context.flow
    flow_days = (flow.window_end - flow.window_start).days
    lines = [f"Flow metrics (trailing {flow_days} calendar days, ending {flow.window_end.date()}):"]
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
    if flow.wait_time > flow.blocked_time:
        lines.append(f"- wait time total={_days(flow.wait_time)} (blocked + waiting states)")
    if flow.flow_efficiency is not None:
        lines.append(f"- flow efficiency={flow.flow_efficiency:.2f}")
    if flow.queue_time is not None and flow.touch_time is not None:
        lines.append(
            f"- queue time p50={_days(flow.queue_time.p50)}, "
            f"touch time p50={_days(flow.touch_time.p50)}"
        )

    dist = context.distribution
    dist_days = (dist.window_end - dist.window_start).days
    histogram_header = (
        f"Lead-time histogram (bins in working days; trailing {dist_days} calendar days)"
    )
    if dist.bins:
        histogram = ", ".join(
            f"{b.start_days}-{b.end_days}:{b.count}" for b in dist.bins if b.count
        )
        lines.append(f"{histogram_header}: {histogram}")
    else:
        lines.append(f"{histogram_header}: empty")

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


_AGING_LIMIT = 10
_TITLE_MAX = 120


def quote_title(title: str) -> str:
    """An issue-tracker title as quoted, one-line, bounded data — never prompt text.

    Anyone who can file an issue writes titles; quoting and truncating keeps
    one from posing as instructions to the LLM or flooding its context.
    """
    one_line = " ".join(title.split())
    if len(one_line) > _TITLE_MAX:
        one_line = one_line[: _TITLE_MAX - 1] + "…"
    return json.dumps(one_line, ensure_ascii=False)


def render_aging(aging: AgingWip, *, limit: int = _AGING_LIMIT, more_hint: str = "") -> str:
    """Aging WIP as text: the reference line, the `limit` oldest items, then every
    blocked item past them (a standup asks for anything blocked, however young).

    `more_hint` follows the "... and N more" line, e.g. which tool lists the rest.
    """
    if not aging.items:
        return "Aging WIP: nothing in progress."
    header = "Aging WIP"
    if aging.cycle_time_percentile is not None:
        header += (
            f" (cycle-time p{aging.percentile} over the last {aging.history_days} calendar days"
            f" = {_days(aging.cycle_time_percentile)})"
        )
    lines = [header + ":"]
    # ponytail: blocked rows are uncapped — a scope with dozens blocked grows the
    # brief past the token budget the cap protects; cap them too, with their own
    # "N more blocked" line, if that ever happens.
    listed = [item for i, item in enumerate(aging.items) if i < limit or item.blocked]
    for item in listed:
        flag = f" [over p{aging.percentile}]" if item.over_percentile else ""
        flag += " [blocked]" if item.blocked else ""
        lines.append(f"- {quote_title(item.title)} — {item.state}, {_days(item.age)}{flag}")
    hidden = len(aging.items) - len(listed)
    if hidden > 0:
        lines.append(f"... and {hidden} more{more_hint}")
    return "\n".join(lines)


def render_meeting_context(context: MeetingContext) -> str:
    """Render the meeting digest: advisor context + delivery health + aging WIP.

    The aging block is `render_aging`, the same text the MCP meeting_brief
    tool shows — one meeting-prep rendering whether the LLM is external
    (MCP) or internal (OpenRouter).
    """
    blocks = [render_context(context.delivery)]

    health = context.health
    if health.score is None:
        blocks.append("Delivery health: not enough data to score.")
    else:
        lines = [f"Delivery health: {health.score}/100 ({health.band})"]
        lines += [f"- {c.name} {c.score}: {c.reason}" for c in health.components]
        blocks.append("\n".join(lines))

    blocks.append(render_aging(context.aging))
    return "\n\n".join(blocks)
