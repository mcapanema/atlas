"""Bug metrics: is bug inflow keeping pace with delivery (ADR-0030).

Computed on read from the flow samples the team's rules produce, like
dora.py. A bug is an item whose effective type (MetricRules.type_of) is
bug. One window, (now - window_days, now], for the ratios, the chart and the
lead-time table.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.domain.metric_rules.entities import MetricRules
from app.domain.metrics.lead_time import lead_times
from app.domain.metrics.samples import FlowSample
from app.domain.metrics.stats import percentile
from app.domain.metrics.throughput import bucketed_throughput, throughput
from app.domain.metrics.windows import bucketing
from app.domain.work_items.entities import WorkItem, WorkItemPriority, WorkItemType

BugState = Literal["ok", "no_mapping", "no_matches"]


@dataclass(frozen=True)
class BugBucket:
    """Bugs created and completed in one bucket — start exclusive, end inclusive."""

    start: datetime
    end: datetime
    created: int
    completed: int


@dataclass(frozen=True)
class FixStats:
    """Bugs fixed in the window (with their median lead time) and open at its end."""

    fixed: int
    median: timedelta | None
    open: int
    oldest_open: timedelta | None


_NO_FIXES = FixStats(fixed=0, median=None, open=0, oldest_open=None)


@dataclass(frozen=True)
class BugMetrics:
    """The Bugs section. With no_mapping or no_matches, counts are 0 and lists empty.

    A ratio is None only when its denominator is 0; min_sample (the team's
    health_min_sample) lets the reader flag a small sample.
    """

    state: BugState
    bug_labels: tuple[str, ...]
    window_start: datetime
    window_end: datetime
    bucket_days: int
    buckets: tuple[BugBucket, ...]
    created: int
    completed: int
    non_bug_completed: int
    all_completed: int
    per_item: float | None
    share: float | None
    min_sample: int
    all_bugs: FixStats
    priorities: tuple[tuple[WorkItemPriority, FixStats], ...]
    unknown_priority: int
    data_as_of: datetime | None


# ponytail: labels are the item's current labels, so a label added later
# moves a bug back to its creation bucket. Upgrade path: label history
# (LABEL_ADDED / LABEL_REMOVED events).
# ponytail: an item belongs to its current team, so a bug moved in does not
# count as created here and one moved out leaves these numbers, as for every
# flow metric. Upgrade path: team-change history from the Linear issue history.
def compute_bug_metrics(
    items_with_samples: Sequence[tuple[WorkItem, FlowSample]],
    stream_rules: Sequence[MetricRules],
    *,
    team_rules: MetricRules,
    now: datetime,
    window_days: int,
    data_as_of: datetime | None,
) -> BugMetrics:
    """The Bugs section for the window (now - window_days, now].

    `stream_rules[i]` holds the rules of `items_with_samples[i]`; empty means
    `team_rules` for every item. `team_rules` also give the evidence floor,
    the bucketing cut-over and the labels that map to bug.
    """
    if stream_rules and len(stream_rules) != len(items_with_samples):
        raise ValueError(
            f"stream_rules has {len(stream_rules)} entries for {len(items_with_samples)} items"
        )
    rules = stream_rules or [team_rules] * len(items_with_samples)
    bugs: list[tuple[WorkItem, FlowSample]] = []
    others: list[FlowSample] = []
    for (item, sample), item_rules in zip(items_with_samples, rules, strict=True):
        if item_rules.type_of(item) is WorkItemType.BUG:
            bugs.append((item, sample))
        else:
            others.append(sample)
    window_start = now - timedelta(days=window_days)
    count, bucket_days = bucketing(window_days, team_rules.daily_bucket_max_days)
    labels = team_rules.bug_labels()
    if not bugs:
        return _empty(
            "no_matches" if labels else "no_mapping",
            labels,
            window_start=window_start,
            now=now,
            bucket_days=bucket_days,
            min_sample=team_rules.health_min_sample,
            data_as_of=data_as_of,
        )
    bug_samples = [sample for _, sample in bugs]
    created = [s.created_at for s in bug_samples if not _canceled_open(s)]
    buckets = tuple(
        BugBucket(
            start=b.start,
            end=b.end,
            created=sum(1 for at in created if b.start < at <= b.end),
            completed=b.completed,
        )
        for b in bucketed_throughput(
            bug_samples, end=now, count=count, bucket_days=bucket_days, start=window_start
        )
    )
    completed = throughput(bug_samples, start=window_start, end=now)
    non_bug_completed = throughput(others, start=window_start, end=now)
    all_completed = completed + non_bug_completed
    created_count = sum(1 for at in created if window_start < at <= now)
    fixes = _FixRows(bugs, window_start=window_start, now=now)
    return BugMetrics(
        state="ok",
        bug_labels=labels,
        window_start=window_start,
        window_end=now,
        bucket_days=bucket_days,
        buckets=buckets,
        created=created_count,
        completed=completed,
        non_bug_completed=non_bug_completed,
        all_completed=all_completed,
        per_item=_ratio(created_count, non_bug_completed),
        share=_ratio(completed, all_completed),
        min_sample=team_rules.health_min_sample,
        all_bugs=fixes.stats(None),
        priorities=tuple((p, fixes.stats(p)) for p in WorkItemPriority),
        unknown_priority=fixes.unknown,
        data_as_of=data_as_of,
    )


def _canceled_open(sample: FlowSample) -> bool:
    """Canceled before completion: a duplicate or "not a bug", which counts nowhere."""
    return sample.canceled and sample.completed_at is None


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


class _FixRows:
    """Bugs fixed in the window and open at `now`, grouped into the lead-time rows."""

    def __init__(
        self, bugs: list[tuple[WorkItem, FlowSample]], *, window_start: datetime, now: datetime
    ) -> None:
        self._now = now
        self._fixed = [
            (item.priority, sample)
            for item, sample in bugs
            if sample.completed_at is not None and window_start < sample.completed_at <= now
        ]
        self._open = [
            (item.priority, sample)
            for item, sample in bugs
            if sample.completed_at is None and not sample.canceled
        ]
        self.unknown = sum(1 for p, _ in [*self._fixed, *self._open] if p is None)

    def stats(self, priority: WorkItemPriority | None) -> FixStats:
        """One row: every bug when `priority` is None, else that priority's bugs."""
        fixed = [s for p, s in self._fixed if priority is None or p is priority]
        still_open = [s for p, s in self._open if priority is None or p is priority]
        if not fixed and not still_open:
            return _NO_FIXES
        seconds = [d.total_seconds() for d in lead_times(fixed)]
        ages = [s.elapsed(s.arrived_at, self._now) for s in still_open]
        return FixStats(
            fixed=len(fixed),
            median=timedelta(seconds=percentile(seconds, 50)) if seconds else None,
            open=len(still_open),
            oldest_open=max(ages, default=None),
        )


def _empty(
    state: BugState,
    labels: tuple[str, ...],
    *,
    window_start: datetime,
    now: datetime,
    bucket_days: int,
    min_sample: int,
    data_as_of: datetime | None,
) -> BugMetrics:
    return BugMetrics(
        state=state,
        bug_labels=labels,
        window_start=window_start,
        window_end=now,
        bucket_days=bucket_days,
        buckets=(),
        created=0,
        completed=0,
        non_bug_completed=0,
        all_completed=0,
        per_item=None,
        share=None,
        min_sample=min_sample,
        all_bugs=_NO_FIXES,
        priorities=(),
        unknown_priority=0,
        data_as_of=data_as_of,
    )
