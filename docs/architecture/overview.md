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

The slices come in four kinds.

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

### Computed-on-read analytics (ADR-0003, amended by ADR-0008)

Metrics, forecasts, and AI advice are recomputed per request from the
persisted events; these slices have no tables and no migrations.

- **Metrics** (`app/domain/metrics/`): per-item `FlowSample`s
  (`samples.py`) fold into `TeamFlowMetrics` — Lead/Cycle Time
  percentiles, Throughput, WIP, Blocked Time, Flow Efficiency
  (`summary.py`) — plus daily CFD phase counts (`cfd.py`), adaptive
  daily/weekly throughput buckets (`history.py`), and a lead-time histogram
  (`distribution.py`). The metrics slice also computes Queue Time, Touch
  Time, Aging WIP, and a Delivery Health composite (predictability /
  efficiency / flow / stability / risk, each 0–100 with a reason string).
  The VISION's Flow Velocity and Flow Load are throughput and WIP under
  Flow Framework names — deliberately not duplicated as separate metrics.
- **Forecasting** (`app/domain/forecasting/monte_carlo.py`): Monte Carlo
  simulation of the scope's open work by resampling its historical daily
  throughput — seeded `random.Random`, deterministic by construction.
- **Advisor** (`app/domain/advisor/`): `AdvisorPort` takes a
  `DeliveryContext` — the already-computed metrics, distribution, and
  forecast — and returns explainable `DeliveryAdvice` (narrative summary
  plus prioritized `Recommendation`s with root causes and evidence). The
  AI never calculates (ADR-0006).
  Advice stays computed-on-read, but personas carry learned state:
  `AdviceFeedback` and `PersonaGuidance` (persisted aggregates in the same
  slice, tables `advice_feedback`/`persona_guidance`) record EM ratings and
  the append-only learned-guidance versions. `PersonaService`
  (`app/application/personas/service.py`) manages them;
  `POST /api/personas/{persona}/reflect` asks the LLM to distill pending
  feedback into the next guidance version, which the adapter appends to that
  persona's system prompt on every subsequent advice request (latest version
  wins; restore re-adds an old version's text as a new version).

All three share one scope pipeline: `app/api/scope.py` validates the scope
(exactly one of `team_id`/`project_id`, 404 when it doesn't exist), and
`ScopeSampleLoader` (`app/application/scope.py`) assembles work items +
events once per request. Served from `GET /api/metrics`,
`/api/metrics/history`, `/api/metrics/lead-time-distribution`,
`/api/metrics/health`, `/api/forecasts`, and `GET /api/recommendations` (409 until
`ATLAS_OPENROUTER_API_KEY` is set — ADR-0005). The frontend consumes them
on the Executive (`/`), Team (`/teams`), and Project (`/projects`)
dashboards — charted with Apache ECharts (ADR-0007) — plus the Flow
Metrics (`/metrics`) and Advisor (`/advisor`) pages.

### Persisted analytics snapshots (ADR-0008)

The one write-side projection: `app/domain/snapshots/` holds
`MetricSnapshot` and `ForecastSnapshot` (one immutable row per scope per
UTC day) with repository ports, `SnapshotService`
(`app/application/snapshots/service.py`) captures them for every team and
project inside the sync request, and `evaluate_forecast_accuracy`
(`app/domain/forecasting/accuracy.py`) scores past forecast snapshots
against actual completions. Served from `GET /api/metrics/snapshots`
(lead-time trend on the dashboards) and `GET /api/forecasts/accuracy`
(forecast calibration on the forecast card and Executive Dashboard).

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
and the Connectors page in the frontend. Blocked work is inferred from the
workspace's blocked label: the datasource resolves label ids whose name
contains "block" and the mapper turns label add/remove history into
BLOCKED/UNBLOCKED events, which feed blocked time and flow efficiency.

## AI adapter

The advisor's adapter (`app/infrastructure/ai/advisor.py`) calls
OpenRouter's OpenAI-compatible chat-completions API with plain httpx — no
provider SDK (ADR-0006) — enforcing a strict JSON response schema and
grounding the system prompt in a versioned knowledge file
(`app/infrastructure/ai/knowledge/flow_coaching.md`). Model choice is
configuration (`ATLAS_ADVISOR_MODEL`).

An optional self-critique pass (`ATLAS_ADVISOR_SELF_CRITIQUE`, default off)
runs draft → critique → revise inside a single advice request; the reflect
call that distills feedback into persona guidance uses the same adapter.

## Single-service deployment

FastAPI serves the REST API and, in production, the compiled React app from `web/dist`
(`app/infrastructure/static.py`). In development, Vite serves the frontend and proxies
`/api` + `/health` to FastAPI.

## Persistence

Async SQLAlchemy 2.0 over SQLite (aiosqlite) today; portable to PostgreSQL because all
database-specific code is confined to Infrastructure and types (e.g. `Uuid`) render
per-dialect. Alembic manages schema migrations.

## Chat access (MCP)

`app/api/mcp_server.py` mounts an MCP (Model Context Protocol) server inside
the monolith at `/mcp/<ATLAS_MCP_TOKEN>` — Streamable HTTP, stateless, secret-
URL auth (connector UIs cannot send custom headers). It is a Presentation-
layer facade: every tool calls the REST API in-process and reformats the DTO
as compact text, so analytics logic and error semantics live in exactly one
place. `GET /api/recommendations/context` returns the advisor's digest as
text for the same reason — a chat client brings its own LLM, so advice works
without an OpenRouter key.

Meeting preparation has two deliberate paths: **external** — the MCP prompts
(`daily_standup`, `retrospective`, `planning`) instruct a connected chat AI
(Claude/ChatGPT) to call Atlas's MCP tools; and **internal** — `GET
/api/meetings/prep` builds the same digest (`MeetingContext` = advisor context
+ delivery health + aging WIP, rendered by `render_meeting_context`) and sends
it to the OpenRouter advisor (`AdvisorPort.prepare_meeting`), so Atlas works
stand-alone. Meeting types are backed by learnable personas (`daily_standup`,
`retrospective`, `planning` in the `Persona` enum) that reuse the persona
feedback/reflect/guidance machinery unchanged.
