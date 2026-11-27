"""Which in-scope item was whose parent at an instant (ADR-0033).

Parent links follow history: an item's PARENT_CHANGED events say which
parent it had when. Items synced before those events existed (and items
created through the REST API) fall back to their current parent. Either
way, an item links only to a parent that is in the scope and already
existed at that instant.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.domain.events.entities import Event
from app.domain.events.timeline import parent_at, tracks_parent
from app.domain.work_items.entities import WorkItem


@dataclass(frozen=True)
class ParentLinks:
    """The scope's parent links at one instant."""

    # Items whose parent (at the instant) is in the scope.
    sub_issue_ids: frozenset[UUID] = frozenset()
    # Each in-scope parent's in-scope children (at the instant).
    children: Mapping[UUID, tuple[WorkItem, ...]] = field(default_factory=dict)
    # The items that had a child (in any team) at the instant, by item id
    # (current links) or by source id (PARENT_CHANGED history).
    parent_ids: frozenset[UUID] = frozenset()
    parent_source_ids: frozenset[str] = frozenset()

    def is_parent(self, item: WorkItem) -> bool:
        """Whether the item had a child at the instant."""
        return item.id in self.parent_ids or (
            item.external_id is not None and item.external_id in self.parent_source_ids
        )


def parent_id_at(
    item: WorkItem,
    events: list[Event],
    at: datetime | None,
    by_external_id: Mapping[str, UUID],
) -> UUID | None:
    """The item's parent at `at`: from its PARENT_CHANGED events, else its current parent.

    Now (`at` None) is always the stored parent: insert-only history can go
    stale or be capped, and the live view must match the tracker. A
    recorded parent maps through `by_external_id` (source id -> item id);
    one that isn't there (out of the scope, or never synced) is None.
    """
    if at is None or not tracks_parent(events):
        return item.parent_id
    source_id = parent_at(events, at)
    return by_external_id.get(source_id) if source_id is not None else None


def sub_issue_links(
    family: Iterable[WorkItem],
    events: Mapping[UUID, list[Event]],
    at: datetime | None,
    existed: Callable[[WorkItem], bool],
) -> ParentLinks:
    """The links among `family` (the scope's unfiltered items) at `at`.

    `existed(parent)` says whether the parent existed at `at`: a link to a
    parent created later never counts, whatever the record says.
    """
    members = {item.id: item for item in family}
    by_external_id = {item.external_id: item.id for item in members.values() if item.external_id}
    children: defaultdict[UUID, list[WorkItem]] = defaultdict(list)
    for item in members.values():
        parent_id = parent_id_at(item, events.get(item.id, []), at, by_external_id)
        parent = members.get(parent_id) if parent_id is not None else None
        if parent is not None and parent.id != item.id and existed(parent):
            children[parent.id].append(item)
    return ParentLinks(
        sub_issue_ids=frozenset(child.id for found in children.values() for child in found),
        children={parent_id: tuple(found) for parent_id, found in children.items()},
    )


def parents_at(
    children: Iterable[WorkItem], events: Mapping[UUID, list[Event]], at: datetime | None
) -> tuple[frozenset[UUID], frozenset[str]]:
    """The parents of `children` (any team) at `at`: item ids, and source ids from history.

    A child counts from its creation on; one with PARENT_CHANGED events
    names its parent of the day by source id, one without (or now, `at`
    None, as in parent_id_at) names its current parent. A child naming
    itself is never its own parent.
    """
    ids: set[UUID] = set()
    source_ids: set[str] = set()
    for child in children:
        if at is not None and child.created_at > at:
            continue
        own = events.get(child.id, [])
        if at is not None and tracks_parent(own):
            source_id = parent_at(own, at)
            if source_id is not None and source_id != child.external_id:
                source_ids.add(source_id)
        elif child.parent_id is not None and child.parent_id != child.id:
            ids.add(child.parent_id)
    return frozenset(ids), frozenset(source_ids)
