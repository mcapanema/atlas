# tests/

Mirrors `app/`'s structure 1:1 (`tests/domain/`, `tests/application/`,
`tests/infrastructure/`, `tests/api/`). New code follows TDD: write the
failing test in the matching subdirectory first, watch it fail for the
right reason, then implement.

## Fixtures (`conftest.py`)

- `sessionmaker` — a fresh in-memory SQLite engine (`StaticPool`, single
  connection so schema persists across sessions) with the full schema
  created from `Base.metadata`.
- `session` — one `AsyncSession` from that sessionmaker, function-scoped.
- `client` — an `httpx.AsyncClient` wired to a real `create_app()`
  instance with `app.state.sessionmaker` overridden to the in-memory
  factory. Use this for `tests/api/` tests; don't stand up a separate app
  instance per test file.

## What belongs where

- `tests/domain/` — entity/invariant tests only, no DB, no fixtures beyond
  plain pytest.
- `tests/application/` — services tested against a hand-written in-memory
  fake Protocol implementation, not the real repository.
- `tests/infrastructure/` — adapters tested against the real (in-memory)
  SQLite `session` fixture.
- `tests/api/` — HTTP-level tests via the `client` fixture, asserting on
  status codes and response JSON.

`asyncio_mode = "auto"` is set in `pyproject.toml`, so `async def
test_...` functions need no `@pytest.mark.asyncio` decorator.

## Coverage

`make test` and CI run `uv run pytest --cov` (branch coverage over `app/`,
`fail_under = 94`, configured in `pyproject.toml`). Plain
`uv run pytest <path>` skips coverage entirely — keep using it for TDD
loops; the gate would false-fail on partial runs anyway. If the gate
trips, add tests; only lower `fail_under` with a reviewed justification.
