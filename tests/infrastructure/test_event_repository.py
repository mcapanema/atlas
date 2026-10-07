from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events.entities import Event, EventType
from app.domain.teams.entities import Team
from app.domain.work_items.entities import StateType, WorkItem
from app.infrastructure.repositories import batching
from app.infrastructure.repositories.events import SqlAlchemyEventRepository
from app.infrastructure.repositories.teams import SqlAlchemyTeamRepository
from app.infrastructure.repositories.work_items import SqlAlchemyWorkItemRepository


async def _work_item_id(session: AsyncSession) -> UUID:
    """FK enforcement is on (see conftest) — events need a real work item."""
    team = Team(organization_id=uuid4(), name="Platform")
    await SqlAlchemyTeamRepository(session).add(team)
    item = WorkItem(team_id=team.id, title="Item")
    await SqlAlchemyWorkItemRepository(session).add(item)
    return item.id


async def test_add_then_list_orders_by_occurred_at(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    work_item_id = await _work_item_id(session)
    await repo.add(
        Event(
            work_item_id=work_item_id,
            type=EventType.STARTED,
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=work_item_id,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    events = await repo.list_for_work_item(work_item_id)

    assert [e.type for e in events] == [EventType.CREATED, EventType.STARTED]


async def test_list_scopes_by_work_item(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_a, item_b = await _work_item_id(session), await _work_item_id(session)
    await repo.add(
        Event(
            work_item_id=item_a,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_b,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert len(await repo.list_for_work_item(item_a)) == 1


async def test_get_by_external_id(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    event = Event(
        work_item_id=await _work_item_id(session),
        type=EventType.STATE_CHANGED,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        from_state="backlog",
        to_state="in_progress",
        external_id="lin_hist_1",
    )
    await repo.add(event)

    fetched = await repo.get_by_external_id("lin_hist_1")

    assert fetched is not None
    assert fetched.id == event.id
    assert fetched.from_state == "backlog"
    assert fetched.to_state == "in_progress"
    assert await repo.get_by_external_id("nope") is None


async def test_list_for_work_items_filters_and_orders(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_a, item_b, item_c = (
        await _work_item_id(session),
        await _work_item_id(session),
        await _work_item_id(session),
    )
    await repo.add(
        Event(
            work_item_id=item_b,
            type=EventType.STARTED,
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_a,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_c,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    events = await repo.list_for_work_items([item_a, item_b])

    assert [(e.work_item_id, e.type) for e in events] == [
        (item_a, EventType.CREATED),
        (item_b, EventType.STARTED),
    ]


async def test_list_for_work_items_with_no_ids_is_empty(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    await repo.add(
        Event(
            work_item_id=await _work_item_id(session),
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    assert await repo.list_for_work_items([]) == []


async def test_existing_external_ids_returns_only_found(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    await repo.add(
        Event(
            work_item_id=await _work_item_id(session),
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            external_id="lin_e1",
        )
    )

    found = await repo.existing_external_ids(["lin_e1", "missing"])

    assert found == {"lin_e1"}


async def test_list_for_work_items_survives_sqlite_bind_param_limit(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyEventRepository(session)
    # SQLite's bind-parameter ceiling is 32766; an unchunked IN(...) with
    # 33k ids raises OperationalError("too many SQL variables").
    ids = [uuid4() for _ in range(33_000)]

    assert await repo.list_for_work_items(ids) == []


async def test_list_for_work_items_orders_across_chunks(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batching, "BATCH_SIZE", 1)  # force one id per chunk
    repo = SqlAlchemyEventRepository(session)
    item_a, item_b = await _work_item_id(session), await _work_item_id(session)
    await repo.add(
        Event(
            work_item_id=item_a,
            type=EventType.STARTED,
            occurred_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
    )
    await repo.add(
        Event(
            work_item_id=item_b,
            type=EventType.CREATED,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    events = await repo.list_for_work_items([item_a, item_b])

    assert [e.type for e in events] == [EventType.CREATED, EventType.STARTED]


async def test_delete_for_work_items_removes_their_events_in_batches(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batching, "BATCH_SIZE", 1)
    repo = SqlAlchemyEventRepository(session)
    first, second, kept = (
        await _work_item_id(session),
        await _work_item_id(session),
        await _work_item_id(session),
    )
    for work_item_id in (first, second, kept):
        await repo.add(
            Event(
                work_item_id=work_item_id,
                type=EventType.CREATED,
                occurred_at=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )

    await repo.delete_for_work_items([first, second])

    remaining = await repo.list_for_work_items([first, second, kept])
    assert [event.work_item_id for event in remaining] == [kept]


async def test_missing_state_types_then_fill_never_overwrites(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_id = await _work_item_id(session)
    at = datetime(2026, 9, 1, tzinfo=UTC)
    untyped = Event(work_item_id=item_id, type=EventType.STARTED, occurred_at=at, external_id="h1")
    typed = Event(
        work_item_id=item_id,
        type=EventType.STARTED,
        occurred_at=at,
        external_id="h2",
        from_state_type=StateType.BACKLOG,
        to_state_type=StateType.STARTED,
    )
    await repo.add(untyped)
    await repo.add(typed)

    missing = await repo.external_ids_missing_state_types(["h1", "h2", "nope"])
    filled = await repo.fill_state_types(
        {
            "h1": (StateType.UNSTARTED, StateType.STARTED),
            "h2": (StateType.TRIAGE, StateType.COMPLETED),  # already typed: untouched
        }
    )
    stored = {e.external_id: e for e in await repo.list_for_work_item(item_id)}

    assert missing == {"h1"}
    assert filled == 1
    assert (stored["h1"].from_state_type, stored["h1"].to_state_type) == (
        StateType.UNSTARTED,
        StateType.STARTED,
    )
    assert (stored["h2"].from_state_type, stored["h2"].to_state_type) == (
        StateType.BACKLOG,
        StateType.STARTED,
    )
    assert await repo.external_ids_missing_state_types(["h1", "h2"]) == set()


async def test_a_typed_to_with_an_untyped_from_is_filled_from_only(session: AsyncSession) -> None:
    # Duplicate -> Todo, stored while "duplicate" had no StateType: only the
    # from side is empty. A transition with no from state has nothing to fill.
    repo = SqlAlchemyEventRepository(session)
    item_id = await _work_item_id(session)
    at = datetime(2026, 9, 1, tzinfo=UTC)
    await repo.add(
        Event(
            work_item_id=item_id,
            type=EventType.STATE_CHANGED,
            occurred_at=at,
            external_id="h1",
            from_state="Duplicate",
            to_state="Todo",
            to_state_type=StateType.UNSTARTED,
        )
    )
    await repo.add(
        Event(
            work_item_id=item_id,
            type=EventType.STATE_CHANGED,
            occurred_at=at,
            external_id="h2",
            to_state="Todo",
            to_state_type=StateType.UNSTARTED,
        )
    )

    missing = await repo.external_ids_missing_state_types(["h1", "h2"])
    filled = await repo.fill_state_types({"h1": (StateType.CANCELED, StateType.BACKLOG)})
    [stored] = [e for e in await repo.list_for_work_item(item_id) if e.external_id == "h1"]

    assert missing == {"h1"}
    assert filled == 1
    # The empty side is filled; the known to-type is never overwritten.
    assert (stored.from_state_type, stored.to_state_type) == (
        StateType.CANCELED,
        StateType.UNSTARTED,
    )
    assert await repo.external_ids_missing_state_types(["h1", "h2"]) == set()


async def test_event_detail_and_types_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyEventRepository(session)
    item_id = await _work_item_id(session)
    event = Event(
        work_item_id=item_id,
        type=EventType.BLOCKER_ADDED,
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
        detail="DEP-1309",
    )
    await repo.add(event)

    [stored] = await repo.list_for_work_item(item_id)

    assert (stored.type, stored.detail, stored.to_state_type) == (
        EventType.BLOCKER_ADDED,
        "DEP-1309",
        None,
    )


async def test_delete_sourced_for_work_items_keeps_events_recorded_through_the_api(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(batching, "BATCH_SIZE", 1)
    repo = SqlAlchemyEventRepository(session)
    item_id, other_id = await _work_item_id(session), await _work_item_id(session)
    at = datetime(2026, 7, 1, tzinfo=UTC)
    synced = Event(
        work_item_id=item_id, type=EventType.CREATED, occurred_at=at, external_id="li1:created"
    )
    recorded = Event(work_item_id=item_id, type=EventType.BLOCKED, occurred_at=at)
    elsewhere = Event(
        work_item_id=other_id, type=EventType.CREATED, occurred_at=at, external_id="li2:created"
    )
    for event in (synced, recorded, elsewhere):
        await repo.add(event)

    await repo.delete_sourced_for_work_items([item_id])

    remaining = await repo.list_for_work_items([item_id, other_id])
    assert {event.id for event in remaining} == {recorded.id, elsewhere.id}
