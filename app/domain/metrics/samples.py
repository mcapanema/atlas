"""Per-work-item flow measures derived from its immutable events.

The bridge between raw events and the flow metrics: every metric consumes
FlowSamples instead of re-reading event streams.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.domain.events.entities import Event, EventType, event_order
from app.domain.events.timeline import derive_timeline
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules


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

    def start(self, at: datetime, *, restart_clock: bool) -> None:
        # A start after a move-back (stopped, not completed) opens a fresh
        # stint when the team's rules say so; a reopen after Done never does.
        if self.started_at is None or (restart_clock and self.stopped_at is not None):
            self.started_at = at
        self.completed_at, self.stopped_at, self.canceled = None, None, False

    def complete(self, at: datetime) -> None:
        self.completed_at, self.stopped_at, self.canceled = at, None, False

    def close(self, event: Event, rules: MetricRules) -> None:
        """A STOPPED or CANCELED: leaves progress, or (by rule) un-delivers Done."""
        if self.completed_at is not None:
            if event.type is EventType.CANCELED and rules.done_then_canceled == "canceled":
                self.completed_at, self.stopped_at, self.canceled = None, event.occurred_at, True
            return
        if self.stopped_at is None:
            self.stopped_at = event.occurred_at
        self.canceled = self.canceled or event.type is EventType.CANCELED


def _replay(ordered: list[Event], rules: MetricRules) -> _Lifecycle:
    state = _Lifecycle()
    for event in ordered:
        if event.type is EventType.STARTED:
            state.start(event.occurred_at, restart_clock=rules.restart_clock_after_move_back)
        elif event.type is EventType.COMPLETED:
            state.complete(event.occurred_at)
        elif event.type is EventType.CANCELED or (
            event.type is EventType.STOPPED and rules.move_back_ends_wip
        ):
            state.close(event, rules)
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


def derive_flow_sample(
    events: list[Event], rules: MetricRules = DEFAULT_RULES
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
    Blocked time sums blocked periods clipped to the
    cycle — from started_at (or the first event, if never started) to
    completed_at; a still-open period on an uncompleted item is not counted
    (unmeasurable).

    ponytail: Done -> Todo isn't a reopen here (only a STARTED after
    COMPLETED is), so it stays completed. Telling it apart from Done ->
    Deployed needs state types: sub-project B of the per-team metric rules.
    """
    if not events:
        return None
    ordered = sorted(events, key=event_order)
    state = _replay(ordered, rules)
    started_at, completed_at = state.started_at, state.completed_at

    # Blocked time is measured inside the item's cycle: a label left on after
    # Done isn't blocked work, and pre-start blocking is already queue time.
    cycle_start = started_at if started_at is not None else ordered[0].occurred_at
    blocked_time = timedelta(0)
    for period in derive_timeline(ordered).blocked_periods:
        ended_at = period.ended_at
        if completed_at is not None:
            ended_at = completed_at if ended_at is None else min(ended_at, completed_at)
        begun = max(period.started_at, cycle_start)
        if ended_at is not None and ended_at > begun:
            blocked_time += ended_at - begun

    return FlowSample(
        created_at=ordered[0].occurred_at,
        started_at=started_at,
        completed_at=completed_at,
        blocked_time=blocked_time,
        stopped_at=state.stopped_at,
        canceled=state.canceled,
        born_done=_born_done(ordered, started_at),
    )


def in_progress(sample: FlowSample, at: datetime) -> bool:
    """Started by `at`, and neither completed nor stopped (moved back/canceled) by it."""
    if sample.started_at is None or sample.started_at > at:
        return False
    return all(ended is None or ended > at for ended in (sample.completed_at, sample.stopped_at))
