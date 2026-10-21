"""Per-work-item flow measures derived from its immutable events.

The bridge between raw events and the flow metrics: every metric consumes
FlowSamples instead of re-reading event streams.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domain.events.entities import Event, EventType, event_order
from app.domain.events.timeline import BlockedPeriod, blocked_periods, derive_timeline
from app.domain.metric_rules.calendar import EVERY_DAY, WorkCalendar
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.stats import percentile
from app.domain.work_items.entities import NOT_STARTED_STATE_TYPES, StateType


@dataclass(frozen=True)
class FlowSample:
    """One work item's flow measures. A None field means 'has not happened'."""

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    blocked_time: timedelta
    stopped_at: datetime | None = None
    canceled: bool = False
    born_done: bool = False
    # A blocked period is still open at the end of the stream.
    blocked_now: bool = False
    # When lead time starts if not at creation: the Triage exit, set only
    # under lead_time_start="triage_exit" (see arrived_at).
    triage_exit_at: datetime | None = None
    # The working days every duration of this sample is measured on.
    calendar: WorkCalendar = EVERY_DAY
    # In-cycle time in a wait state (the rules' wait_state_names) while not
    # blocked: wait_time adds it to blocked_time without counting twice.
    state_wait_time: timedelta = timedelta(0)

    def elapsed(self, start: datetime, end: datetime) -> timedelta:
        """Time from `start` to `end` on this sample's working calendar."""
        return self.calendar.elapsed(start, end)

    @property
    def wait_time(self) -> timedelta:
        """In-cycle time not spent working: blocked, or in a wait state."""
        return self.blocked_time + self.state_wait_time

    @property
    def arrived_at(self) -> datetime:
        """Where lead time and pre-start queue time begin (creation, or Triage exit by rule)."""
        return self.triage_exit_at or self.created_at


def _born_done(ordered: list[Event], started_at: datetime | None) -> bool:
    """Created already completed: a CREATED, then a COMPLETED at its instant, never started.

    Connectors stamp an item logged straight into a done state that way (the
    Linear mapping's `:created-done`). It's a record of work, not flow Atlas
    observed. The first event must be a CREATED: a completion with no recorded
    creation means "creation unknown", not "created done". Later completions
    don't matter: a re-sync backfills the creation-instant one beside sync's
    completedAt-stamped one.
    """
    created = ordered[0]
    return (
        created.type is EventType.CREATED
        and started_at is None
        and any(
            event.type is EventType.COMPLETED and event.occurred_at == created.occurred_at
            for event in ordered
        )
    )


@dataclass
class _Lifecycle:
    """Fold state while replaying one item's events in order."""

    started_at: datetime | None = None
    completed_at: datetime | None = None
    stopped_at: datetime | None = None
    canceled: bool = False
    reopened_after_done: bool = False

    def start(self, at: datetime, *, restart_clock: bool) -> None:
        # A start after a move-back (stopped, not completed) opens a fresh
        # stint when the team's rules say so; a reopen after Done never does.
        moved_back = self.stopped_at is not None and not self.reopened_after_done
        if self.started_at is None or (restart_clock and moved_back):
            self.started_at = at
        self.completed_at, self.stopped_at, self.canceled = None, None, False
        self.reopened_after_done = False

    def complete(self, at: datetime) -> None:
        self.completed_at, self.stopped_at, self.canceled = at, None, False
        self.reopened_after_done = False

    def reopen(self, event: Event, rules: MetricRules) -> None:
        """A Done or Canceled item moved back to a not-started state, by the reopen rules.

        Reopened, it is open again (remaining) but not in progress. A Done
        reopen keeps the clock: a later start resumes the same stint.
        """
        if event.from_state_type is StateType.COMPLETED:
            if self.completed_at is not None and rules.done_then_reopened == "reopened":
                self.completed_at, self.stopped_at = None, event.occurred_at
                self.reopened_after_done = True
        elif self.canceled and rules.canceled_then_reopened == "reopened":
            self.canceled = False

    def close(self, event: Event, rules: MetricRules) -> None:
        """A STOPPED or CANCELED: leaves progress, or (by rule) un-delivers Done."""
        if self.completed_at is not None:
            if event.type is EventType.CANCELED and rules.done_then_canceled == "canceled":
                self.completed_at, self.stopped_at, self.canceled = None, event.occurred_at, True
                self.reopened_after_done = False
            return
        if self.stopped_at is None:
            self.stopped_at = event.occurred_at
        # A stop or cancel after a Done reopen is a plain move-back: a later
        # start restarts the clock as after any cancel.
        self.reopened_after_done = False
        self.canceled = self.canceled or event.type is EventType.CANCELED


def reopens(event: Event) -> bool:
    """A move from a Done or Canceled state back to a not-started one (typed transitions only)."""
    return (
        event.from_state_type in (StateType.COMPLETED, StateType.CANCELED)
        and event.to_state_type in NOT_STARTED_STATE_TYPES
    )


def _triage_exit(ordered: list[Event]) -> datetime | None:
    """When the item first left Triage, at or before its first start/completion.

    None if it never sat in Triage, or only left after work began (a later
    Triage visit would make lead and queue time negative).
    """
    began = next(
        (e.occurred_at for e in ordered if e.type in (EventType.STARTED, EventType.COMPLETED)),
        None,
    )
    return next(
        (
            event.occurred_at
            for event in ordered
            if (began is None or event.occurred_at <= began)
            and event.from_state_type is StateType.TRIAGE
            and event.to_state_type not in (None, StateType.TRIAGE)
        ),
        None,
    )


def state_type_at(
    events: Sequence[Event], at: datetime | None, current: StateType | None
) -> StateType | None:
    """The item's state type at `at`; `current` (the stored one) for now (`at` None).

    From typed transitions: the last one at or before `at` gives its
    to-type; before the first one, its from-type. With no typed transitions
    (REST-created events) the stored type is the only fact.
    """
    if at is None:
        return current
    typed = [e for e in sorted(events, key=event_order) if e.to_state_type is not None]
    if not typed:
        return current
    before = [e for e in typed if e.occurred_at <= at]
    return before[-1].to_state_type if before else typed[0].from_state_type


def _apply(state: _Lifecycle, event: Event, rules: MetricRules) -> None:
    if event.type is EventType.STARTED:
        state.start(event.occurred_at, restart_clock=rules.restart_clock_after_move_back)
    elif event.type is EventType.COMPLETED:
        state.complete(event.occurred_at)
    elif reopens(event):
        state.reopen(event, rules)
    elif event.type is EventType.CANCELED or (
        event.type is EventType.STOPPED and rules.move_back_ends_wip
    ):
        state.close(event, rules)


def _replay(ordered: list[Event], rules: MetricRules) -> _Lifecycle:
    state = _Lifecycle()
    for event in ordered:
        _apply(state, event, rules)
    if state.completed_at is not None and rules.reopen_completion == "first":
        # The first completion of the current clock: never before its start,
        # so a restarted clock can't produce a negative cycle time.
        state.completed_at = min(
            e.occurred_at
            for e in ordered
            if e.type is EventType.COMPLETED
            and (state.started_at is None or e.occurred_at >= state.started_at)
        )
    return state


def _in_cycle(
    periods: Sequence[BlockedPeriod],
    started_at: datetime | None,
    completed_at: datetime | None,
    calendar: WorkCalendar,
) -> timedelta:
    """Time the periods cover inside the cycle, started_at -> completed_at.

    A label left on after Done isn't blocked work, pre-start blocking or
    waiting is already queue time, and an item never started has no cycle, so none
    (audit 2026-10-13). A still-open period on an uncompleted item is
    unmeasurable and not counted.
    """
    if started_at is None:
        return timedelta(0)
    total = timedelta(0)
    for period in periods:
        ended_at = period.ended_at
        if completed_at is not None:
            ended_at = completed_at if ended_at is None else min(ended_at, completed_at)
        begun = max(period.started_at, started_at)
        if ended_at is not None and ended_at > begun:
            total += calendar.elapsed(begun, ended_at)
    return total


def _merged(*groups: Sequence[BlockedPeriod]) -> list[BlockedPeriod]:
    """The union of `groups`' periods as disjoint periods; an open one runs to the end."""
    merged: list[BlockedPeriod] = []
    for period in sorted((p for group in groups for p in group), key=lambda p: p.started_at):
        last = merged[-1] if merged else None
        if last is None or (last.ended_at is not None and period.started_at > last.ended_at):
            merged.append(period)
        elif last.ended_at is not None and (
            period.ended_at is None or period.ended_at > last.ended_at
        ):
            merged[-1] = BlockedPeriod(started_at=last.started_at, ended_at=period.ended_at)
    return merged


def _wait_state_periods(
    ordered: list[Event], rules: MetricRules, born_in: str | None
) -> list[BlockedPeriod]:
    """Stays in the rules' wait states, as periods; none when the rules list none."""
    if not rules.wait_state_names:
        return []
    return [
        BlockedPeriod(started_at=stay.entered_at, ended_at=stay.exited_at)
        for stay in derive_timeline(ordered, rules, born_in=born_in).state_periods
        if rules.is_wait_state(stay.state)
    ]


def derive_flow_sample(
    events: list[Event], rules: MetricRules = DEFAULT_RULES, *, born_in: str | None = None
) -> FlowSample | None:
    """Fold one work item's events into a FlowSample; None if it has no events.

    `rules` are the item's team's lifecycle rules (built-in by default):
    created_at is the first event; started_at the first STARTED (or, with
    restart_clock_after_move_back, the restart after the latest move-back);
    completed_at the last COMPLETED (or the first since the clock started,
    with reopen_completion="first"), voided if a later STARTED reopened the
    item. stopped_at is when an uncompleted item first left progress: its
    first STOPPED since the latest STARTED or COMPLETED (STOPPED is ignored
    when move_back_ends_wip is off), or its CANCELED. canceled marks an item
    closed without delivery, which with done_then_canceled="canceled"
    includes Done -> Canceled; a STARTED after that cancel voids the
    cancellation, and with restart_clock_after_move_back it opens a new stint
    (the cancel un-delivered the item). With move_back_ends_wip off, a STOPPED
    never counts, so the clock restarts only after a CANCELED. born_done marks an
    item created already completed and never started (see _born_done).
    Blocked time sums the rules' blocked periods (labels, workflow states,
    relations, explicit events) clipped to the cycle, started_at to
    completed_at (see _in_cycle); an item never started has none.
    `born_in` is the item's creation state, as blocked_periods takes it.
    state_wait_time is the cycle time spent in the rules' wait states while
    not blocked (the union of both, clipped the same way, minus blocked time).

    With done_then_reopened / canceled_then_reopened = "reopened", a typed
    move from Done / Canceled to a not-started state reopens the item (open,
    not in progress); a later start after a Done reopen keeps the clock.
    arrived_at is the Triage exit under lead_time_start="triage_exit".
    Durations (cycle, lead, queue, touch, blocked, age) are measured on the rules'
    working days, so a non-working day adds no time.
    """
    if not events:
        return None
    ordered = sorted(events, key=event_order)
    state = _replay(ordered, rules)
    started_at, completed_at = state.started_at, state.completed_at

    calendar = rules.work_calendar
    periods = blocked_periods(ordered, rules, born_in=born_in)
    blocked_time = _in_cycle(periods, started_at, completed_at, calendar)
    waits = [*periods, *_wait_state_periods(ordered, rules, born_in)]
    if completed_at is None:
        # Open periods count nothing on an unfinished item (_in_cycle); left
        # in, one would absorb an earlier closed period and undercount it.
        waits = [p for p in waits if p.ended_at is not None]
    waiting = _merged(waits)

    return FlowSample(
        created_at=ordered[0].occurred_at,
        started_at=started_at,
        completed_at=completed_at,
        blocked_time=blocked_time,
        stopped_at=state.stopped_at,
        canceled=state.canceled,
        born_done=_born_done(ordered, started_at),
        blocked_now=any(p.ended_at is None for p in periods),
        triage_exit_at=_triage_exit(ordered) if rules.lead_time_start == "triage_exit" else None,
        calendar=calendar,
        state_wait_time=_in_cycle(waiting, started_at, completed_at, calendar) - blocked_time,
    )


def in_progress(sample: FlowSample, at: datetime) -> bool:
    """Started by `at`, and neither completed nor stopped (moved back/canceled) by it."""
    if sample.started_at is None or sample.started_at > at:
        return False
    return all(ended is None or ended > at for ended in (sample.completed_at, sample.stopped_at))


# Where a scope's tracked history starts, as a percentile of its items'
# creation: a few old issues moved in from another team can't pull it back.
_HISTORY_START_PERCENTILE = 10


def observed_history_days(
    samples: Sequence[FlowSample],
    *,
    end: datetime,
    days: int,
    tracked_since: datetime | None = None,
) -> int:
    """`days`, shortened to the whole days the scope has been tracked.

    Days before tracking began aren't zero-throughput days: nothing was
    tracked yet. Sampling them drags a young scope's forecast toward zero
    throughput, and reads its health trend as growth from nothing.

    With `tracked_since` (the team's rule), tracking starts at the scope's
    first creation or completion on or after it, or at it if none: older
    items were moved in from elsewhere, and a project that began later
    starts at its own items. Without it, the start is estimated: the earlier
    of the first completion and the 10th percentile of item creation. Not
    the oldest item: a moved-in issue keeps its original creation date
    (audit 2026-10-13: one 2025 issue put 41 phantom zero days in FNG's
    90-day forecast). Not the first completion alone: a team or project
    fills up for weeks before anything finishes, and those are real zero
    days. The partial first day counts; never less than one day.

    ponytail: the estimate is a percentile. In a scope under ~20 items one
    old item still pulls the start back, and many moved-in items do in any
    scope; tracked_since is the fix for a team it misreads.
    """
    if tracked_since is not None:
        start = _first_activity_since(samples, tracked_since)
    elif samples:
        start = _estimated_start(samples)
    else:
        return days
    return max(1, min(days, (end - start) // timedelta(days=1) + 1))


def _first_activity_since(samples: Sequence[FlowSample], since: datetime) -> datetime:
    moments = [m for s in samples for m in (s.created_at, s.completed_at) if m is not None]
    return min((m for m in moments if m >= since), default=since)


def _estimated_start(samples: Sequence[FlowSample]) -> datetime:
    created = [sample.created_at.timestamp() for sample in samples]
    start = datetime.fromtimestamp(percentile(created, _HISTORY_START_PERCENTILE), tz=UTC)
    completions = [sample.completed_at for sample in samples if sample.completed_at is not None]
    return min(start, *completions) if completions else start
