# Atlas

Delivery Intelligence Platform for Engineering Managers — observes delivery
data (issues, deployments), understands what's actually happening, predicts
risk, and advises on improvements. Product framing: `README.md`; full
vision: `docs/VISION.md`; technical record: `docs/architecture/overview.md`
+ `docs/adr/`.

## Architecture

Single-deployable monolith, strict Domain-Driven Design, dependencies point
inward:

```
Presentation (app/api, web/)
    ↓
Application (app/application)       — use cases / orchestration
    ↓
Domain (app/domain)                 — entities + ports; stdlib only
    ↑
Infrastructure (app/infrastructure) — SQLAlchemy adapters, connectors, SPA serving
```

Layer import rules are enforced by `tests/test_architecture.py`. Each domain
concept is a vertical slice across all four layers; the three slice kinds
(persisted aggregates, computed-on-read analytics, ports to external
systems) are described in `docs/architecture/overview.md`.

## Tech stack

- **Backend**: Python 3.13+, `uv`, FastAPI, SQLAlchemy 2.0 (async; SQLite
  via aiosqlite, portable to PostgreSQL), Alembic, Pydantic v2, pytest.
- **Frontend**: React 19, TypeScript, Vite, Ant Design, TanStack Query,
  React Router, Vitest.
- **Single deployable**: in production FastAPI serves both the REST API and
  the compiled React app. No separate frontend server outside development.

## Commands

Prefer the Makefile (`make help` for the full list) over raw commands.

| Command | What it does |
|---|---|
| `make install` | install backend + frontend dependencies |
| `make hooks` | install git pre-commit hooks (ruff check/format, eslint, prettier on staged changes) |
| `make format` | auto-format backend (ruff) and frontend (prettier) |
| `make dev` | run backend + frontend dev servers together (Ctrl+C stops both) |
| `make test` / `make lint` / `make typecheck` / `make security` | run one phase, both sides |
| `make check` | full local CI gate — mirrors `.github/workflows/ci.yml` |
| `make migrate` | apply Alembic migrations |
| `make run` | build frontend + serve single-service production mode |
| `make docker-up` | run the whole stack in Docker (`docker-compose.yml`) |

On pull requests CI also gates diff coverage: ≥ 90% of changed lines, per
side. CI and Dependabot are summarized in `README.md`.

## Non-negotiable constraints

- Domain layer: zero framework imports, stdlib only.
- Never return an ORM model from an API route — always a Pydantic DTO.
- `uv run mypy` (strict), `uv run ruff check .`, and `uv run ruff format --check .` must pass.
- Complexity ceilings are gates, not suggestions: ruff `C901` (max 10),
  `PLR0911/0912/0913/0915`; ESLint `complexity`/`max-*` in `web/`. Over a
  ceiling? Split the function. A suppression needs a line-level `noqa` /
  `eslint-disable-next-line` with an em-dash reason.
- New backend code follows TDD: failing test first, then implementation.
- Persistence stays portable to PostgreSQL — no SQLite-specific types/SQL
  outside `app/infrastructure/`.
- Don't introduce Kafka, Kubernetes, ClickHouse, Spark, Elasticsearch,
  Redis, or a data warehouse — boring, single-deployable monolith by design
  (`docs/adr/0002-async-ddd-monolith.md`).
- A `ponytail:` comment marks a deliberate simplification and names its
  ceiling and upgrade path — treat it as intent, and read it before
  "fixing" the simplicity.

## Where things live

| Path | Purpose |
|---|---|
| `app/domain/` | entities + repository ports, pure Python |
| `app/application/` | use cases / services |
| `app/infrastructure/` | SQLAlchemy adapters, connectors, AI adapter, SPA serving |
| `app/api/` | FastAPI routers + DTOs, composition root (`deps.py`) |
| `app/config.py` | all runtime config (`ATLAS_`-prefixed `Settings`) |
| `web/` | React frontend (design brief: `PRODUCT.md`) |
| `migrations/` | Alembic migrations |
| `tests/` | mirrors `app/`, one subtree per layer |
| `docs/architecture/`, `docs/adr/` | architecture overview + ADRs |

Each code directory above has its own CLAUDE.md, which Claude Code loads
automatically when you work with files there. This file holds only what
applies everywhere.

## Keeping CLAUDE.md files current

These files are part of the codebase — fix drift in the same PR that causes
or notices it.

- Place each rule at the lowest level that still triggers when it's
  needed: cross-cutting → this file; one directory's convention → that
  directory's CLAUDE.md; a gotcha about one file → a comment in that file.
- Document the pattern plus one exemplar, never a list of concepts or
  services — a new vertical slice updates `docs/architecture/overview.md`,
  not the layer CLAUDE.md files.
- Point at the source of truth for values (thresholds, ceilings, versions)
  instead of copying numbers into prose.
- State what *is*; no "today/later" or phase-relative wording — git history
  holds the past.
- A new top-level directory with its own conventions gets a CLAUDE.md and a
  row in the table above.
