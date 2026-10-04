"""Shared scope loading for the analytics use cases.

Metrics, forecasting, snapshots and the advisor all start from the same
picture: every work item in a scope plus each item's ordered events, folded
with the rules of the item's team. This module is the one place that picture
gets assembled — a semantic drift between two copies of this loop is
exactly where remaining-count bugs hide.
"""

from collections import defaultdict
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.application.metric_rules.resolver import MetricRulesResolver, ResolvedRules
from app.domain.events.entities import Event
from app.domain.events.repository import EventRepository
from app.domain.metric_rules.entities import DEFAULT_RULES, MetricRules
from app.domain.metrics.samples import FlowSample, derive_flow_sample
from app.domain.work_items.entities import WorkItem, WorkItemType
from app.domain.work_items.repository import WorkItemRepository


@dataclass(frozen=True)
class ScopeSamples:
    """One scope load: per-item event streams, derived samples, item count.

    `streams` holds one occurred_at-ordered event list per work item that
    has events, born-done items excluded (per their team's rule). `item_count`
    counts every item in the scope, including eventless backlog but not
    excluded born-done records — it is the forecast's remaining-work
    denominator. `items_with_samples` pairs each evented item with its
    derived sample (aging WIP needs item identity). `stream_rules[i]` are the
    rules stream i was folded with (its item's team's); `rules` are the
    scope's own (its team's, or its project's team's).
    """

    streams: list[list[Event]]
    samples: list[FlowSample]
    item_count: int
    items_with_samples: list[tuple[WorkItem, FlowSample]] = field(default_factory=list)
    stream_rules: list[MetricRules] = field(default_factory=list)
    rules: MetricRules = DEFAULT_RULES


@dataclass(frozen=True)
class ScopeData:
    """A scope's raw picture: its items, their events, and the rules that fold them.

    `samples()` derives the analytics view now, or as of a past instant —
    snapshot capture and the history recompute replay a scope that way.
    """

    items: list[WorkItem]
    events: Mapping[UUID, list[Event]]
    rules: ResolvedRules = field(default_factory=ResolvedRules)

    def samples(self, *, as_of: datetime | None = None) -> ScopeSamples:
        """The scope's samples; with `as_of`, as it stood at that instant."""
        streams: list[list[Event]] = []
        stream_rules: list[MetricRules] = []
        pairs: list[tuple[WorkItem, FlowSample]] = []
        item_count = 0
        for item in self.items:
            stream = self._stream(item, as_of)
            if stream is None:
                continue  # didn't exist yet at `as_of`
            item_count += 1
            item_rules = self.rules.for_team(item.team_id)
            sample = derive_flow_sample(stream, item_rules)
            if sample is None:
                continue
            if sample.born_done and item_rules.exclude_born_done:
                # Logged already done: a record of work, not flow Atlas
                # observed. It leaves every metric, remaining included.
                item_count -= 1
                continue
            streams.append(stream)
            stream_rules.append(item_rules)
            pairs.append((item, sample))
        return ScopeSamples(
            streams=streams,
            samples=[sample for _, sample in pairs],
            item_count=item_count,
            items_with_samples=pairs,
            stream_rules=stream_rules,
            rules=self.rules.scope,
        )

    def _stream(self, item: WorkItem, as_of: datetime | None) -> list[Event] | None:
        """The item's events up to `as_of`; None when the item didn't exist then."""
        stream = self.events.get(item.id, [])
        if as_of is None:
            return stream
        if not stream:
            return [] if item.created_at <= as_of else None
        return [event for event in stream if event.occurred_at <= as_of] or None


class ScopeSampleLoader:
    """Loads a scope's items + events once, with the rules that fold them."""

    def __init__(
        self,
        work_items: WorkItemRepository,
        events: EventRepository,
        rules: MetricRulesResolver | None = None,
    ) -> None:
        self._work_items = work_items
        self._events = events
        self._rules = rules

    async def load_data(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeData:
        items = await self._work_items.list(team_id=team_id, project_id=project_id)
        # ponytail: in-Python filter over the scope's items; push into the
        # repository query if scopes grow past what one list comfortably holds.
        if types is not None:
            items = [item for item in items if item.type in types]
        if exclude_states is not None:
            excluded = {state.casefold() for state in exclude_states}
            items = [item for item in items if item.state.casefold() not in excluded]
        events = await self._events.list_for_work_items([item.id for item in items])
        by_item: defaultdict[UUID, list[Event]] = defaultdict(list)
        for event in events:
            by_item[event.work_item_id].append(event)
        rules = (
            await self._rules.resolve(
                team_id=team_id,
                project_id=project_id,
                item_team_ids={item.team_id for item in items},
            )
            if self._rules is not None
            else ResolvedRules()
        )
        return ScopeData(items=items, events=dict(by_item), rules=rules)

    async def load(
        self,
        *,
        team_id: UUID | None = None,
        project_id: UUID | None = None,
        types: AbstractSet[WorkItemType] | None = None,
        exclude_states: AbstractSet[str] | None = None,
    ) -> ScopeSamples:
        data = await self.load_data(
            team_id=team_id, project_id=project_id, types=types, exclude_states=exclude_states
        )
        return data.samples()
