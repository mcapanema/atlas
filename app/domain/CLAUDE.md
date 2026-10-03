# app/domain/

Pure Python, stdlib only — no FastAPI, SQLAlchemy, Pydantic, aiosqlite, or
connector code (Linear, GitHub, Slack, …), ever. `tests/test_architecture.py`
fails the suite on any other import — absolute or relative, module-level or
function-local.

## Slice shapes

A new concept copies the exemplar for its kind (the full slice list lives in
`docs/architecture/overview.md`):

**Persisted aggregate** — exemplar `organizations/`: `entities.py` +
`repository.py`.

- `entities.py` — a plain `@dataclass` per entity. Invariants live in
  `__post_init__` and raise `ValueError`. IDs are `uuid4()` `UUID`s;
  timestamps are timezone-aware UTC `datetime`s.
- `repository.py` — an `async` `typing.Protocol` persistence port. Interface
  only: Infrastructure implements it, Application depends on it.
- A derivation over one aggregate's data lives beside the aggregate, not in
  a service (e.g. `events/timeline.py`).

**Pure-function analytics** — exemplar `metrics/`: frozen result dataclasses
plus deterministic functions. No repository, no loading — Application
assembles the inputs. Anything random takes a seeded `random.Random`.

**External-system port** — exemplar `sync/`: a `Protocol` port, the stdlib
types that cross it, and the port's own failure type beside it
(`DataSourceError`). Adapters translate vendor exceptions into it, so
nothing above Infrastructure ever sees an httpx error.

## Shared helpers

`_time.py`'s `utcnow()` is the one timezone-aware "now" for entity
`created_at`/`recorded_at` defaults — don't redefine a local `_utcnow`.

## Tests

`tests/domain/` asserts on entity and pure-function behavior only — no DB,
no HTTP. If a change here is forced by an Infrastructure or Presentation
change, the dependency is pointing the wrong way.
