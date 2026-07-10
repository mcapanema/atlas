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

## Vertical slice pattern

Each domain concept owns:
- `app/domain/<concept>/entities.py` + `repository.py` (the port)
- `app/application/<concept>/service.py` (use cases)
- `app/infrastructure/repositories/<concept>.py` (ORM model + adapter)
- `app/api/<concept>.py` + DTOs in `app/api/schemas.py`

`Organization` is the reference implementation. `Team`, `Project`, `Work Item`,
and `Event` are now implemented in the same shape, forming the ownership
hierarchy `Organization → Team → Project → Work Item → Event`: a Team owns
Projects and Work Items, a Project groups Work Items, and each Work Item
accumulates immutable Events (state changes, assignment, etc.) — the system
of record that metrics will later derive from. `Metric` is now real as a *computed* concept: the metrics engine
(`app/domain/metrics/`) derives per-item `FlowSample`s from events
(`derive_flow_sample`) and folds them into `TeamFlowMetrics` — Lead/Cycle
Time percentiles, Throughput, WIP, Blocked Time, Flow Efficiency — via
`compute_team_metrics` (`summary.py`). Nothing is persisted: metrics are
recomputed per request (`MetricsService`), served from
`GET /api/metrics?team_id=…`, and shown on the Flow Metrics page
(`/metrics`). This slice deliberately has no repository — everything is
recomputed on read, no snapshot tables. The Linear connector (below) populates these slices from a real
workspace, and the Work Item Explorer (`/work-items` in the frontend) makes
them visible: per-item event timeline plus state/blocked periods derived by
the pure domain function `derive_timeline`
(`app/domain/events/timeline.py`) and served from
`GET /api/work-items/{id}/timeline`. Phase 3's metrics engine builds on
the same derivation. Phase 4 adds flow *history* alongside the summary:
daily phase counts (Cumulative Flow Diagram data) via event replay in
`app/domain/metrics/cfd.py`, plus weekly throughput buckets — both
computed on read like the summary metrics, nothing persisted, no snapshot
tables yet. `GET /api/metrics` and `GET /api/metrics/history` both scope
by team or project. The frontend's three dashboard pages consume this:
Executive (`/`) shows a portfolio table across teams, while Team (`/teams`)
and Project (`/projects`) chart it via Apache ECharts.

Phase 5 adds *forecasting* on the same computed-on-read pattern:
`app/domain/forecasting/monte_carlo.py` simulates completion of the scope's
open work by resampling its historical daily throughput (seeded
`random.Random` — deterministic by construction), and
`app/domain/metrics/distribution.py` bins lead times into a day-width
histogram. `ForecastService` counts the scope's open items (event-less
backlog included) and runs the simulation; results are served from
`GET /api/forecasts` (percentile finish dates, optional `target_date`
delivery confidence, outcome histogram) and
`GET /api/metrics/lead-time-distribution`, both scoped by team or project
like `/api/metrics`. The Team and Project dashboards render them through
the shared `FlowDashboard`: a lead-time distribution chart plus a
`ForecastCard` with a target-date picker. Still nothing persisted — no
snapshot tables, no new migrations.

Phase 6 adds the *AI Intelligence* layer on the same compute-on-read pattern:
the `advisor` slice defines an `AdvisorPort` (`app/domain/advisor/port.py`)
that takes a `DeliveryContext` — the already-computed `FlowMetrics`,
`LeadTimeDistribution`, and `DeliveryForecast` — and returns explainable
`DeliveryAdvice` (a narrative summary plus prioritized `Recommendation`s,
each carrying a root cause and evidence quoting the input metrics). The AI
never calculates: `AdvisorService` assembles the context by composing
`MetricsService` and `ForecastService`, and the OpenRouter adapter
(`app/infrastructure/ai/advisor.py`) does the reasoning via OpenRouter's
OpenAI-compatible chat-completions API (plain httpx, strict JSON schema —
no provider SDK), grounded in a versioned knowledge file
(`app/infrastructure/ai/knowledge/flow_coaching.md` — the SPEC's Knowledge
Layer). Served from `GET /api/recommendations` (409 until
`ATLAS_OPENROUTER_API_KEY` is set, mirroring the Linear connector) and the
Advisor page (`/advisor`), which generates advice on demand. Nothing
persisted — advice is regenerated per request, no migrations.

## Connectors

External delivery systems are integrated through the `DeliveryDataSource`
port (`app/domain/sync/port.py`), which yields platform-neutral snapshots
(`SourceTeam`, `SourceProject`, `SourceWorkItem`, `SourceEvent` — in
`app/domain/sync/source.py`). Connector-specific code lives only in
`app/infrastructure/connectors/<vendor>/`; vendor payloads never leave that
package.

The first connector is Linear (`app/infrastructure/connectors/linear/`):
a small GraphQL client (httpx, personal API key via `ATLAS_LINEAR_API_KEY`),
pure mapping functions, and a paginating `LinearDataSource`. The
`SyncService` use case (`app/application/sync/service.py`) upserts the
snapshots into the domain model idempotently, matching by `external_id` —
running sync twice is a no-op. Exposed as `POST /api/connectors/linear/sync`
and the Connectors page in the frontend.

## Single-service deployment

FastAPI serves the REST API and, in production, the compiled React app from `web/dist`
(`app/infrastructure/static.py`). In development, Vite serves the frontend and proxies
`/api` + `/health` to FastAPI.

## Persistence

Async SQLAlchemy 2.0 over SQLite (aiosqlite) today; portable to PostgreSQL because all
database-specific code is confined to Infrastructure and types (e.g. `Uuid`) render
per-dialect. Alembic manages schema migrations.
