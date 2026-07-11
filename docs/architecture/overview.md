# Atlas Architecture Overview

Atlas is a single-deployable monolith with a Domain-Driven Design interior.

## Layers (dependencies point inward)

    Presentation (app/api, web/)
        ↓
    Application (app/application)  — use cases / orchestration
        ↓
    Domain (app/domain)           — entities + repository ports; ZERO framework imports
        ↑
    Infrastructure (app/infrastructure) — SQLAlchemy adapters, DB session, SPA serving

- **Domain** is pure Python. It never imports FastAPI, SQLAlchemy, Pydantic, or any connector.
- **Application** depends only on Domain ports (Protocols), never on Infrastructure.
- **Infrastructure** implements the Domain ports (e.g. `SqlAlchemyOrganizationRepository`).
- **Presentation** (FastAPI routers, React app) depends on Application and returns typed DTOs — ORM entities are never exposed.

## Vertical slices

Each domain concept spans all four layers in the same shape:

- `app/domain/<concept>/` — entities and/or ports (pure Python)
- `app/application/<concept>/service.py` — use cases
- `app/infrastructure/…` — the adapter side (ORM repository, connector, LLM client)
- `app/api/<concept>.py` — router, with DTOs in `app/api/schemas.py`

The slices come in three kinds.

### Persisted aggregates — the system of record

`Organization → Team → Project → Work Item → Event`, each with
`entities.py` + `repository.py` (a `Protocol` port), a SQLAlchemy adapter
in `app/infrastructure/repositories/`, and a CRUD router. A Team owns
Projects and Work Items; a Project groups Work Items; each Work Item
accumulates immutable Events (state changes, assignments, blocks). Events
are the source of truth everything analytical derives from. One pure
derivation lives beside its aggregate: `derive_timeline`
(`app/domain/events/timeline.py`) turns an item's events into
state/blocked periods for `GET /api/work-items/{id}/timeline` and the Work
Item Explorer (`/work-items`).

### Computed-on-read analytics — nothing persisted (ADR-0003)

Metrics, forecasts, and AI advice are recomputed per request from the
persisted events; these slices have no tables and no migrations.

- **Metrics** (`app/domain/metrics/`): per-item `FlowSample`s
  (`samples.py`) fold into `TeamFlowMetrics` — Lead/Cycle Time
  percentiles, Throughput, WIP, Blocked Time, Flow Efficiency
  (`summary.py`) — plus daily CFD phase counts (`cfd.py`), weekly
  throughput buckets (`history.py`), and a lead-time histogram
  (`distribution.py`).
- **Forecasting** (`app/domain/forecasting/monte_carlo.py`): Monte Carlo
  simulation of the scope's open work by resampling its historical daily
  throughput — seeded `random.Random`, deterministic by construction.
- **Advisor** (`app/domain/advisor/`): `AdvisorPort` takes a
  `DeliveryContext` — the already-computed metrics, distribution, and
  forecast — and returns explainable `DeliveryAdvice` (narrative summary
  plus prioritized `Recommendation`s with root causes and evidence). The
  AI never calculates (ADR-0006).

All three share one scope pipeline: `app/api/scope.py` validates the scope
(exactly one of `team_id`/`project_id`, 404 when it doesn't exist), and
`ScopeSampleLoader` (`app/application/scope.py`) assembles work items +
events once per request. Served from `GET /api/metrics`,
`/api/metrics/history`, `/api/metrics/lead-time-distribution`,
`/api/forecasts`, and `GET /api/recommendations` (409 until
`ATLAS_OPENROUTER_API_KEY` is set — ADR-0005). The frontend consumes them
on the Executive (`/`), Team (`/teams`), and Project (`/projects`)
dashboards — charted with Apache ECharts (ADR-0007) — plus the Flow
Metrics (`/metrics`) and Advisor (`/advisor`) pages.

### Ports to external systems

- **Sync** (`app/domain/sync/`): the `DeliveryDataSource` port (`port.py`)
  plus platform-neutral snapshots (`SourceTeam`, `SourceProject`,
  `SourceWorkItem`, `SourceEvent` in `source.py`). `SyncService`
  (`app/application/sync/service.py`) upserts snapshots into the domain
  model idempotently, matching on `external_id` — running sync twice is a
  no-op (ADR-0004).
- **Advisor** (`app/domain/advisor/port.py`): implemented by the
  OpenRouter adapter (ADR-0006).

Each port defines its failure type beside it (`DataSourceError`,
`AdvisorError`); adapters translate vendor errors into them, and
`create_app()`'s exception handlers turn them into 502s.

## Connectors

Connector-specific code lives only in
`app/infrastructure/connectors/<vendor>/`; vendor payloads never leave
that package. The first connector is Linear
(`app/infrastructure/connectors/linear/`): a small GraphQL client (httpx,
personal API key via `ATLAS_LINEAR_API_KEY`), pure payload→`Source*`
mapping functions, and a paginating `LinearDataSource`. Exposed as
`POST /api/connectors/linear/sync` (409 until the key is set — ADR-0005)
and the Connectors page in the frontend.

## AI adapter

The advisor's adapter (`app/infrastructure/ai/advisor.py`) calls
OpenRouter's OpenAI-compatible chat-completions API with plain httpx — no
provider SDK (ADR-0006) — enforcing a strict JSON response schema and
grounding the system prompt in a versioned knowledge file
(`app/infrastructure/ai/knowledge/flow_coaching.md`). Model choice is
configuration (`ATLAS_ADVISOR_MODEL`).

## Single-service deployment

FastAPI serves the REST API and, in production, the compiled React app from `web/dist`
(`app/infrastructure/static.py`). In development, Vite serves the frontend and proxies
`/api` + `/health` to FastAPI.

## Persistence

Async SQLAlchemy 2.0 over SQLite (aiosqlite) today; portable to PostgreSQL because all
database-specific code is confined to Infrastructure and types (e.g. `Uuid`) render
per-dialect. Alembic manages schema migrations.
