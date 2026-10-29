"""Time in state: where work spends its cycle, and the statistical bottleneck.

For each item completed in the trailing window, every stay in a workflow
state (events/timeline.py's state_periods) is clipped to the item's cycle,
started_at -> completed_at, and to the spans it was actually in progress
(STARTED until STOPPED, COMPLETED or CANCELED), then measured on its working
calendar: backlog time, a move-back, and Done before a reopen never count.
The bottleneck is the state with the most total time. Total, not the median:
total / window is about the average number of items sitting in that state
(Little's Law), so it weighs how long items stay and how many pass through.
The queue is the items in progress in each state at the window's end, read
from their events (so a past period replays it).

Rows group by (team, state) when the caller labels each stream with its
team (a multi-team project), and by state alone otherwise.
"""

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.domain.events.entities import Event, EventType, event_order
from app.domain.events.timeline import StatePeriod, state_periods
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.metrics.windows import STATS_WINDOW_DAYS

# A span of work ends at any of these; STOPPED counts whatever the team's
# move_back_ends_wip rule says: a moved-back item is not in a work state.
_ENDS_WORK = (EventType.STOPPED, EventType.COMPLETED, EventType.CANCELED)

# (start, end) of a span in progress; end None means still in progress.
_Span = tuple[datetime, datetime | None]

# A row's identity: (team label, state); the label is None when unsplit.
_Key = tuple[str | None, str]


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
    # The team the row belongs to, in a scope split by team; None otherwise.
    team: str | None = None


@dataclass(frozen=True)
class StateTimes:
    """Time in each state over (window_start, window_end], most total time first.

    `measured` counts completed items with time in at least one state.
    `bottleneck` is the first state, when at least `min_sample` items were
    measured and it holds any time; None otherwise. `bottleneck_team` is
    that row's team.
    """

    window_start: datetime
    window_end: datetime
    measured: int
    min_sample: int
    states: tuple[StateTime, ...]
    bottleneck: str | None
    bottleneck_team: str | None = None


def _work_spans(events: Sequence[Event]) -> list[_Span]:
    """The spans the item was in progress, from its STARTED and work-ending events."""
    spans: list[_Span] = []
    opened: datetime | None = None
    for event in sorted(events, key=event_order):
        if event.type is EventType.STARTED and opened is None:
            opened = event.occurred_at
        elif event.type in _ENDS_WORK and opened is not None:
            spans.append((opened, event.occurred_at))
            opened = None
    if opened is not None:
        spans.append((opened, None))
    return spans


def _overlap(period: StatePeriod, span: _Span, cycle: _Span, sample: FlowSample) -> timedelta:
    """Working time of `period` inside both `span` and the closed `cycle`."""
    started_at, completed_at = cycle[0], cycle[1] or cycle[0]
    begin = max(period.entered_at, span[0], started_at)
    end = min(period.exited_at or completed_at, span[1] or completed_at, completed_at)
    return sample.elapsed(begin, end) if end > begin else timedelta(0)


def _in_cycle_stays(events: Sequence[Event], sample: FlowSample) -> dict[str, timedelta]:
    """The sample's in-progress time in each state inside its cycle; empty if it has none."""
    if sample.started_at is None or sample.completed_at is None:
        return {}
    cycle = (sample.started_at, sample.completed_at)
    spans = _work_spans(events)
    stays: dict[str, timedelta] = defaultdict(timedelta)
    for period in state_periods(list(events)):
        for span in spans:
            stays[period.state] += _overlap(period, span, cycle, sample)
    return {state: time for state, time in stays.items() if time}


def _queued_in(events: Sequence[Event], at: datetime) -> str | None:
    """The state the item sat in at `at` while in progress; None when not in progress."""
    working = any(start <= at and (end is None or end > at) for start, end in _work_spans(events))
    entered = [p for p in state_periods(list(events)) if p.entered_at <= at]
    return entered[-1].state if working and entered else None


def _median(durations: list[timedelta]) -> timedelta:
    if not durations:
        return timedelta(0)
    return timedelta(seconds=percentile([d.total_seconds() for d in durations], 50))


@dataclass
class _Tally:
    """Per-state accumulators while folding the scope's items."""

    stays: dict[_Key, list[timedelta]] = field(default_factory=lambda: defaultdict(list))
    queue: Counter[_Key] = field(default_factory=Counter)
    wait: set[_Key] = field(default_factory=set)
    measured: int = 0

    def note_wait(self, key: _Key, rules: MetricRules) -> None:
        if rules.is_wait_state(key[1]):
            self.wait.add(key)

    def states(self) -> list[StateTime]:
        totals = {key: sum(d, timedelta(0)) for key, d in self.stays.items()}
        grand = sum(totals.values(), timedelta(0))
        listed = [
            StateTime(
                state=key[1],
                total=totals.get(key, timedelta(0)),
                share=totals.get(key, timedelta(0)) / grand if grand else 0.0,
                median=_median(self.stays.get(key, [])),
                items=len(self.stays.get(key, [])),
                queue=self.queue[key],
                wait_state=key in self.wait,
                team=key[0],
            )
            for key in {*totals, *self.queue}
        ]
        return sorted(listed, key=lambda s: (-s.total, -s.queue, s.state, s.team or ""))


def _check_per_stream(name: str, values: Sequence[object] | None, streams: int) -> None:
    """A given per-stream list needs one entry per stream; empty means omitted."""
    if values and len(values) != streams:
        raise ValueError(f"{name} has {len(values)} entries for {streams} streams")


def compute_state_times(
    streams: Sequence[Sequence[Event]],
    samples: Sequence[FlowSample],
    *,
    now: datetime,
    window_days: int = STATS_WINDOW_DAYS,
    rules: MetricRules = DEFAULT_RULES,
    stream_rules: Sequence[MetricRules] | None = None,
    stream_teams: Sequence[str | None] | None = None,
) -> StateTimes:
    """Time in each state for samples completed in (now - window_days, now].

    `streams[i]` folds into `samples[i]` under `stream_rules[i]` (its team's
    rules; `rules` when omitted), which name its wait states, and
    `stream_teams[i]` labels its rows (no label when omitted). A state is
    listed when it holds time or a queue. A non-empty per-stream list of the
    wrong length raises ValueError. `rules` (the scope's) set the
    minimum sample (health_min_sample) a bottleneck needs.
    """
    _check_per_stream("stream_rules", stream_rules, len(streams))
    _check_per_stream("stream_teams", stream_teams, len(streams))
    window_start = now - timedelta(days=window_days)
    tally = _Tally()
    for index, (events, sample) in enumerate(zip(streams, samples, strict=True)):
        item_rules = stream_rules[index] if stream_rules else rules
        team = stream_teams[index] if stream_teams else None
        completed = sample.completed_at
        if completed is not None and window_start < completed <= now:
            stays = _in_cycle_stays(events, sample)
            tally.measured += bool(stays)
            for state, duration in stays.items():
                tally.stays[(team, state)].append(duration)
                tally.note_wait((team, state), item_rules)
        queued = _queued_in(events, now)
        if queued is not None:
            tally.queue[(team, queued)] += 1
            tally.note_wait((team, queued), item_rules)
    states = tally.states()
    enough = tally.measured >= rules.health_min_sample
    top = states[0] if states and enough and states[0].total else None
    return StateTimes(
        window_start=window_start,
        window_end=now,
        measured=tally.measured,
        min_sample=rules.health_min_sample,
        states=tuple(states),
        bottleneck=top.state if top else None,
        bottleneck_team=top.team if top else None,
    )
