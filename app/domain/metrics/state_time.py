"""Time in state: where work spends its cycle, and the statistical bottleneck.

For each item completed in the trailing window, every stay in a workflow
state (events/timeline.py's state_periods) is clipped to the item's cycle,
started_at -> completed_at, and measured on its working calendar: backlog
and Done time never count. The bottleneck is the state with the most total
time. Total, not the median: total / window is about the average number of
items sitting in that state (Little's Law), so it weighs how long items stay
and how many pass through. The queue is the items in progress in each state
at the window's end, read from their events (so a past period replays it).

ponytail: states group by name, so one project spanning teams that share a
state name merges them. Upgrade path: key by (team, state) if multi-team
projects show a misleading bottleneck.
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event
from app.domain.events.timeline import state_periods
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.samples import FlowSample, in_progress
from app.domain.metrics.stats import percentile
from app.domain.metrics.windows import STATS_WINDOW_DAYS


@dataclass(frozen=True)
class StateTime:
    """In-cycle time items completed in the window spent in one state, and its queue now."""

    state: str
    total: timedelta
    # total / the sum of every state's total; 0.0 when that sum is 0.
    share: float
    # P50 over the measured items that spent time here; zero when none did.
    median: timedelta
    items: int
    # Items in progress in this state at the window's end.
    queue: int
    wait_state: bool


@dataclass(frozen=True)
class StateTimes:
    """Time in each state over (window_start, window_end], most total time first.

    `measured` counts completed items with time in at least one state.
    `bottleneck` is the first state, when at least `min_sample` items were
    measured and it holds any time; None otherwise.
    """

    window_start: datetime
    window_end: datetime
    measured: int
    min_sample: int
    states: tuple[StateTime, ...]
    bottleneck: str | None


def _in_cycle_stays(events: Sequence[Event], sample: FlowSample) -> dict[str, timedelta]:
    """The sample's time in each state inside its cycle; empty if it has none."""
    if sample.started_at is None or sample.completed_at is None:
        return {}
    stays: dict[str, timedelta] = defaultdict(timedelta)
    for period in state_periods(list(events)):
        exited_at = period.exited_at or sample.completed_at
        begin = max(period.entered_at, sample.started_at)
        end = min(exited_at, sample.completed_at)
        if end > begin:
            stays[period.state] += sample.elapsed(begin, end)
    return dict(stays)


def _state_at(events: Sequence[Event], at: datetime) -> str | None:
    """The state the item was in at `at`, from its events; None without state moves."""
    entered = [p for p in state_periods(list(events)) if p.entered_at <= at]
    return entered[-1].state if entered else None


def _queues(
    streams: Sequence[Sequence[Event]], samples: Sequence[FlowSample], now: datetime
) -> Counter[str]:
    queue: Counter[str] = Counter()
    for events, sample in zip(streams, samples, strict=True):
        state = _state_at(events, now) if in_progress(sample, now) else None
        if state is not None:
            queue[state] += 1
    return queue


def _median(durations: list[timedelta]) -> timedelta:
    if not durations:
        return timedelta(0)
    return timedelta(seconds=percentile([d.total_seconds() for d in durations], 50))


def compute_state_times(
    streams: Sequence[Sequence[Event]],
    samples: Sequence[FlowSample],
    *,
    now: datetime,
    window_days: int = STATS_WINDOW_DAYS,
    rules: MetricRules = DEFAULT_RULES,
) -> StateTimes:
    """Time in each state for samples completed in (now - window_days, now].

    `streams[i]` folds into `samples[i]`. A state is listed when it holds
    time or a queue. `rules` name the wait states and the minimum sample
    (health_min_sample) a bottleneck needs.
    """
    window_start = now - timedelta(days=window_days)
    per_state: dict[str, list[timedelta]] = defaultdict(list)
    measured = 0
    for events, sample in zip(streams, samples, strict=True):
        if sample.completed_at is None or not window_start < sample.completed_at <= now:
            continue
        stays = _in_cycle_stays(events, sample)
        measured += bool(stays)
        for state, duration in stays.items():
            per_state[state].append(duration)
    queue = _queues(streams, samples, now)
    totals = {state: sum(d, timedelta(0)) for state, d in per_state.items()}
    grand = sum(totals.values(), timedelta(0))
    states = sorted(
        (
            StateTime(
                state=state,
                total=totals.get(state, timedelta(0)),
                share=totals.get(state, timedelta(0)) / grand if grand else 0.0,
                median=_median(per_state.get(state, [])),
                items=len(per_state.get(state, [])),
                queue=queue[state],
                wait_state=rules.is_wait_state(state),
            )
            for state in {*totals, *queue}
        ),
        key=lambda s: (-s.total, -s.queue, s.state),
    )
    enough = measured >= rules.health_min_sample
    bottleneck = states[0].state if states and enough and states[0].total else None
    return StateTimes(
        window_start=window_start,
        window_end=now,
        measured=measured,
        min_sample=rules.health_min_sample,
        states=tuple(states),
        bottleneck=bottleneck,
    )
