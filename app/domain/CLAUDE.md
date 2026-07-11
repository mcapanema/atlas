# app/domain/

Pure Python. Zero framework imports — no FastAPI, SQLAlchemy, Pydantic,
aiosqlite, or connector-specific code (Linear, GitHub, Slack, etc.), ever.
This is the one rule in this repo that isn't negotiable.

## Three slice shapes

**Persisted aggregates** (`organizations/`, `teams/`, `projects/`,
`work_items/`, `events/`): `entities.py` + `repository.py`.

- `entities.py` — a plain `@dataclass` per aggregate/entity. Invariants
  live in `__post_init__` and raise `ValueError` on violation (see
  `organizations/entities.py`'s stripped/non-empty `name` check). IDs are
  `uuid4()`-generated `UUID`s, timestamps timezone-aware UTC `datetime`s.
- `repository.py` — a `typing.Protocol` per aggregate describing the
  persistence port (`add`, `list`, `get`, ...), all `async`. Interface
  only — Infrastructure implements it, Application depends on it.
- `events/` additionally holds `timeline.py`, a pure function deriving
  state/blocked periods from an item's events. A derivation that belongs
  to an aggregate's data lives beside the aggregate, not in a service.

**Pure-function analytics** (`metrics/`, `forecasting/`): no repository,
no persistence — frozen dataclasses for results plus deterministic
functions (`derive_flow_sample`, `compute_team_metrics`, the CFD replay,
the Monte Carlo simulation, ...). Anything random takes a seeded
`random.Random` argument. These modules compute; they never load —
Application assembles their inputs.

**Port slices** (`sync/`, `advisor/`): a `Protocol` port for an external
capability plus the stdlib types that cross it — `sync/source.py`'s
platform-neutral `Source*` snapshots with `sync/port.py`'s
`DeliveryDataSource`; `advisor/entities.py`'s `DeliveryAdvice`/`Recommendation` with
`advisor/port.py`'s `DeliveryContext`/`AdvisorPort`. Each port defines its failure type
beside it (`DataSourceError`, `AdvisorError`) — adapters translate vendor
exceptions into these, so nothing above Infrastructure ever sees an httpx
error.

**Shared helpers**: `_time.py` — `utcnow()`, the single timezone-aware
"now" used by entity `created_at`/`recorded_at` defaults. Don't redefine
a local `_utcnow` in a new slice.

## Before committing

Grep your diff for `fastapi`, `sqlalchemy`, `pydantic`, `sqlite`
(case-insensitive) — none should match. `tests/domain/` asserts on entity
and pure-function behavior only (no DB, no HTTP).

## Adding a new concept

Copy the shape that matches the kind: `organizations/` for a persisted
aggregate, `metrics/` for pure computation, `sync/` for an
external-system port. Nothing here should ever need to change when
Infrastructure or Presentation changes — if it does, the dependency is
pointing the wrong way.
