# Atlas Architecture Overview

Atlas is a single-deployable monolith with a Domain-Driven Design interior.

## Layers (dependencies point inward)

![Atlas architecture layers. Presentation (app/api, web/) depends on Application (app/application), which depends only on Domain ports. Domain (app/domain) is the core: entities and repository ports, zero framework imports. Infrastructure (app/infrastructure) implements the Domain ports. Dependencies point inward, enforced by tests/test_architecture.py.](../assets/architecture-layers.svg)

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

The slices come in the kinds below.

### Persisted aggregates — the system of record

`Organization → Team → Project → Work Item → Event`, each with
`entities.py` + `repository.py` (a `Protocol` port), a SQLAlchemy adapter
in `app/infrastructure/repositories/`, and a CRUD router. A Team owns
Projects and Work Items; a Project groups Work Items; a Project's teams are
derived from its items (`WorkItemRepository.team_ids_by_project()`, ADR-0020),
with `Project.team_id` only its home team; each Work Item
accumulates immutable Events (state changes, assignments, blocks — including raw label and blocker changes and state types on transitions, ADR-0011). An Organization
also owns People (`app/domain/people/`); a Work Item points at its assignee
Person by `assignee_id`, and the shown name (the manager's display-name
override, else the source name) resolves on load (ADR-0021). `GET
/api/people` and `PATCH /api/people/{id}` serve the People table on the
Organizations page (`/organizations`), where display names are edited.
Events are the source of truth everything analytical derives from. One pure
derivation lives beside its aggregate: `derive_timeline`
(`app/domain/events/timeline.py`) turns an item's events into state periods
and — under its team's rules (`blocked_periods`) — blocked periods for `GET /api/work-items/{id}/timeline` and the Work
Item Explorer (`/work-items`).

An Organization also owns Codebases (`app/domain/codebases/`, ADR-0024): a
repository from a code host, mapped to at most one Team and holding its Pull
Requests and Deployments. Codebases arrive unmapped from a code sync, and an
unmapped codebase is never fetched; `GET /api/codebases?organization_id=`
lists them with their stored counts, and `PUT /api/codebases/{id}` sets the
team and the production environment. The code sync links a pull request to
the work items whose keys it names by REVIEW and MERGED events
(`CodeSyncService`, `app/application/codebases/sync.py`).

### Computed-on-read analytics (ADR-0003, amended by ADR-0008 and ADR-0023)

Metrics and forecasts are recomputed per request from the persisted
events; these slices have no tables and no migrations. AI advice is the
exception: it is generated in the background and stored (ADR-0023).

- **Metrics** (`app/domain/metrics/`): per-item `FlowSample`s
  (`samples.py`) fold into `TeamFlowMetrics` — Lead/Cycle Time
  percentiles, Throughput, WIP, Blocked Time, Flow Efficiency
  (`summary.py`) — plus daily CFD phase counts (`cfd.py`), adaptive
  daily/weekly throughput buckets (`history.py`), and a lead-time histogram
  (`distribution.py`). The metrics slice also computes Queue Time, Touch
  Time, Aging WIP (each item flagged when past the median or the aging percentile, or
  blocked now), and a Delivery Health composite (predictability /
  efficiency / flow / stability / risk, each 0–100 with a reason string and a
  band read against the same cutoffs as the overall score;
  predictability scores how often recent cycles met the team's own service
  level, the aging percentile over the history before the window (ADR-0016), and
  efficiency carries no weight in the built-in rules (a team that lists no
  wait states reads blocked-only efficiency, near 100%; ADR-0018);
  a component backed by fewer than `health_min_sample` items is left out,
  and with none left the scope is unscored).
  Time in state (`state_time.py`) sums each completed item's in-cycle stays
  per workflow state, counts the queue in each state now, and names the
  state with the most total time as the bottleneck (none below
  `health_min_sample` measured items) — the advisor explains it, never
  finds it.
  DORA (`dora.py`, ADR-0025) computes a team's deploy frequency, change
  lead time, change failure rate and time to restore from its codebases'
  production deployments, pull requests and incidents, each banded by the
  DORA report thresholds (deploy frequency has a band with any mapped
  codebase; lead time, change failure rate and restore wait for
  `health_min_sample` values). `DoraService` (`app/application/metrics/dora.py`)
  feeds it a team's codebases and the scope's incident-labelled items.
  The VISION's Flow Velocity and Flow Load are throughput and WIP under
  Flow Framework names — deliberately not duplicated as separate metrics.
- **Forecasting** (`app/domain/forecasting/monte_carlo.py`): Monte Carlo
  simulation of the scope's open work by resampling its historical daily
  throughput — seeded `random.Random`, deterministic by construction.
- **Advisor** (`app/domain/advisor/`): `AdvisorPort` takes a
  `DeliveryContext` — the already-computed metrics, distribution,
  forecast, and (team scopes) DORA metrics — and returns explainable
  `DeliveryAdvice` (narrative summary plus prioritized `Recommendation`s
  with root causes and evidence). The AI never calculates (ADR-0006).
  Advice is stored, not computed on read (ADR-0023): `AdviceRun` (table
  `advice_runs`, managed by `AdviceRunService`) is one generation of advice
  or meeting prep, keyed by scope + persona + request params; each
  `POST` starts a run in `AdviceRunner` (`app/api/advice_runner.py`) and
  each `GET` reads the newest. Personas carry learned state:
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
`/api/metrics/health`, `/api/metrics/dora` (team scope only; 422 for a
project), `/api/forecasts`, and `/api/recommendations` (`POST` starts a
stored background run and answers 202 — 409 until `ATLAS_OPENROUTER_API_KEY` is set,
ADR-0005; `GET` reads the latest stored run for the same scope, persona and
window, or `null`, with no key needed). `GET /api/metrics/overview`
is the Executive Dashboard's per-team row: flow metrics, health, forecast
accuracy, snapshot history and, for a team, `dora` from one scope load,
identical to the standalone endpoints for the same query. The frontend consumes them
on the Executive (`/`), Team (`/teams`), and Project (`/projects`)
dashboards — charted with Apache ECharts (ADR-0007) — plus the Advisor
(`/advisor`) page; the retired `/metrics` route redirects to `/teams`.

### Persisted analytics snapshots (ADR-0008)

The one write-side projection: `app/domain/snapshots/` holds
`MetricSnapshot` and `ForecastSnapshot` (one row per scope per UTC day,
rewritten in place when the scope's metric rules change — ADR-0010) with
repository ports, `SnapshotService` (`app/application/snapshots/service.py`)
captures them for every team and project inside the sync job, and
`evaluate_forecast_accuracy` (`app/domain/forecasting/accuracy.py`) scores
past forecast snapshots against actual completions. Served from
`GET /api/metrics/snapshots` (lead-time trend on the dashboards) and
`GET /api/forecasts/accuracy` (forecast calibration on the forecast card
and Executive Dashboard).

### Metric rules (ADR-0010)

Every rule that changes how a metric is computed — lifecycle interpretation
(incl. reopens, parent issues, lead-time start), the blocked signal, the
wait states flow efficiency and queue/touch time count as wait (ADR-0018), health
scales, weights and evidence floor, timezone, working days, holidays, chart
bucketing, forecast history and remaining, label → type mapping — is a field
of `MetricRules` (`app/domain/metric_rules/entities.py`). Defaults are the
previous built-in behavior, except the blocked sources (blocked-named
states and listed labels only, ADR-0026), the health floor (ADR-0015) and durations counting Monday-to-Friday working days
(ADR-0017).
`metric_rule_overrides` stores sparse override layers per organization
(the workspace default) and per team; `MetricRulesResolver`
(`app/application/metric_rules/resolver.py`) resolves built-in ⊕ workspace
⊕ team, and `ScopeSampleLoader` (`app/application/scope.py`) folds each item
with its team's rules, so durations count each item's own team's working
days, while the scope's own rules drive health, calendar and windows. A
project scope reads the rules of its items' team when they share one, the
workspace rules when they span several, and its home team's when it has none
(ADR-0020).
`MetricRulesService` serves `GET/PATCH /api/organizations/{id}/metric-rules`
and `/api/teams/{id}/metric-rules`; a change rewrites the affected scopes'
snapshot history through the background `RecomputeRunner` in
`app/api/recompute.py` (it cancels the running task before a save writes,
then restarts with the pending scopes; status on the organization row,
resumed by the lifespan). Edited on the Metric rules page (`/metric-rules`).
An organization's layers travel between installs as a JSON file (ADR-0019):
`GET …/metric-rules/export` and `POST …/metric-rules/import` under
`/api/organizations/{id}`, with the file's dataclasses and team matching
(`external_id`, then name) in `app/application/metric_rules/sharing.py`;
each layer is validated like a PATCH body (`MetricRulesOverridesWrite`).
An import replaces the workspace layer and each matched team's layer, skips
and reports unknown or ambiguous teams, and recomputes history the same way a
PATCH does.
One rule changes no metric: `sprint_length_days` (`MEETING_RULES`), the
retrospective's default window on the Meetings page, `/api/meetings/prep`
and the MCP `retrospective` prompt (teams carry it in `GET /api/teams`).
Changing it rewrites no snapshot history and doesn't mark a team's rules as
custom.

### Ports to external systems

- **Sync** (`app/domain/sync/`): the `DeliveryDataSource` port (`port.py`)
  plus platform-neutral snapshots (`SourceTeam`, `SourceProject`,
  `SourceWorkItem`, `SourceEvent` in `source.py`). `SyncService`
  (`app/application/sync/service.py`) upserts snapshots into the domain
  model idempotently, matching on `external_id` — running sync twice is a
  no-op (ADR-0004) — upserts the people who own items (name and email from
  the source, never the display-name override; people are never pruned,
  ADR-0021) — and deletes items the source no longer returns (ADR-0009).
  A rebuild sync (`"rebuild": true`) replaces the returned items'
  source-derived events from the current mapping and rewrites snapshot
  history (ADR-0013) — the upgrade path after a mapping fix.
  A team sync (`POST /api/connectors/linear/teams/{id}/sync`, the Team
  Dashboard's "Sync team" button) fetches only that team's work items,
  snapshots only that team, its single-team projects and its home projects
  with no items (a project holding other teams' items waits for the
  organization sync), and never prunes — a
  filtered fetch can't tell deleted from moved — so deletions wait for the
  next organization sync.
  Sync routes start a background job and answer `202` with it
  (`SyncJobRunner`, `app/api/sync_jobs.py`, ADR-0022): one sync at a time, a
  request the running job covers gets that job back, any other answers
  `409`, and the last `HISTORY_SIZE` jobs (`app/api/sync_jobs.py`) are kept
  in memory (a restart loses them; `GET /api/connectors/linear/jobs/{id}`
  then answers `404`).
  Each sync stamps `teams.last_synced_at` for the teams it pulled; the flow
  history's `data_as_of` is the later of that stamp and the newest event's
  `recorded_at`.
  Auto sync (ADR-0014): an organization's `SyncSchedule`
  (`app/domain/sync_schedules/`: weekdays, a local time window, an interval,
  an IANA zone; slot math in `slots.py`) is served by
  `GET/PUT /api/organizations/{id}/sync-schedule` and run by the in-process
  `AutoSyncRunner` (`app/api/auto_sync.py`). It ticks every minute, syncs
  each organization with a due slot through the same `SyncJobRunner`, and
  records the outcome on the schedule. When GitHub is configured, a
  successful Linear sync is followed by a code sync, whose failure only logs.
  Edited on the Connectors page.
- **Code host** (`app/domain/sync/port.py`): the `CodeHostSource` port plus
  vendor-neutral `SourceCodebase`, `SourcePullRequest` and
  `SourceDeployment` (`source.py`). `CodeSyncService` upserts codebases by
  `external_id` across organizations (never pruned; the first owner keeps
  one, ADR-0024), then the pull requests and deployments of
  mapped codebases, idempotently (ADR-0004): a codebase's first fetch
  reaches back `BACKFILL`, later fetches start `OVERLAP` before its
  `last_synced_at`, or at its oldest pending deployment started within
  `PENDING_REFRESH`, whichever is earlier (all in `app/application/codebases/sync.py`). `POST /api/connectors/github/sync` runs it as a `code`
  job on the same `SyncJobRunner` (`GET /api/connectors/github/jobs/{id}`);
  it captures no snapshots, because the REVIEW and MERGED events change no
  metric: the flow derivations never anchor on `CODE_EVENT_TYPES`
  (`app/domain/events/entities.py`).
- **Advisor** (`app/domain/advisor/port.py`): implemented by the
  OpenRouter adapter (ADR-0006).

Each port defines its failure type beside it (`DataSourceError` — also
for `CodeHostSource` — and `AdvisorError`); adapters translate vendor errors into them, and
`create_app()`'s exception handlers turn them into 502s.

## Connectors

Connector-specific code lives only in
`app/infrastructure/connectors/<vendor>/`; vendor payloads never leave
that package. The first connector is Linear
(`app/infrastructure/connectors/linear/`): a small GraphQL client (httpx,
personal API key via `ATLAS_LINEAR_API_KEY`), pure payload→`Source*`
mapping functions, and a paginating `LinearDataSource`. Exposed as
`POST /api/connectors/linear/sync` (409 until the key is set — ADR-0005)
and the Connectors page in the frontend. A project's home team is the first
of its Linear teams that Atlas has synced (ADR-0020). The mapper stores raw
facts — label add/remove events (named), blocked-side relation-history
events (named by the blocker's current identifier, and each sync renames
stored ones, so a blocker moved to another team still pairs its add with
its resolve), state types on transitions, and each issue's labels, parent and
current assignee as a `SourcePerson` (Linear user id, name, email; a blank
name reads as unassigned) — an email or handle Linear uses as the name is
turned into "First Last" (ADR-0011); the team's metric rules decide at read
time what counts as blocked (labels, workflow-state names, relations),
which items are parents, and which types and states count.
Issues created directly in a started-type state start at creation, and
issues created directly in a completed-type state (logged after the fact)
complete at creation (`:created-done`), which analytics treat as records, not
flow: `ScopeSampleLoader` leaves these born-done items out of every metric;
leaving a started state for a non-started, non-completed one emits STOPPED
(ends WIP); `canceledAt` emits CANCELED (closed undelivered, excluded from WIP
and forecast remaining, while Done → Canceled stays delivered); an issue
archived while still open emits CANCELED at `archivedAt` (`:archived:`), and
Linear's `duplicate` state type reads as `canceled`. Archived issues are synced
and trashed ones skipped; already-synced issues that are trashed or deleted
upstream are pruned (ADR-0009). All of these use derived external ids,
so a re-sync backfills existing data. Linear coalesces quick transitions
by rewriting an already-synced history entry in place (Todo → In Progress
becomes Todo → Done); events stay insert-only, so when no stored event of an
issue with `completedAt` is a completion, the sync synthesizes one
(`:completed`) and the stored start keeps its real time.

The GitHub connector (`app/infrastructure/connectors/github/`) implements
`CodeHostSource` on GitHub's GraphQL API with the GraphQL client shared
between vendors (`app/infrastructure/connectors/graphql.py`): a token via
`ATLAS_GITHUB_TOKEN` and the organization or user login via
`ATLAS_GITHUB_OWNER`. Its codebases are that owner's repositories; GitHub
errors raise `GitHubAPIError` (a `DataSourceError`). Exposed as `GET
/api/connectors/github` and `POST /api/connectors/github/sync` (409 until
both variables are set — ADR-0005).

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

The database file is `data/atlas.db`, used by local runs and bind-mounted into
the Compose container, so both see the same data. SQLite's file locks don't
cross Docker Desktop's VM, so only one of them may run at a time; the
Makefile's `local-db-free` guard enforces this. The container runs SQLite in
rollback-journal mode (`ATLAS_SQLITE_JOURNAL_MODE=delete`) because WAL's
memory-mapped `-shm` file is unreliable on the bind mount; local runs keep
WAL.

## Chat access (MCP)

`app/api/mcp_server.py` mounts an MCP (Model Context Protocol) server inside
the monolith at `/mcp/<ATLAS_MCP_TOKEN>` — Streamable HTTP, stateless, secret-
URL auth (connector UIs cannot send custom headers). It is a Presentation-
layer facade: every tool calls the REST API in-process and reformats the DTO
as compact text, so analytics logic and error semantics live in exactly one
place. `GET /api/recommendations/context` returns the advisor's digest as
text for the same reason — a chat client brings its own LLM, so advice works
without an OpenRouter key. The MCP mount is the only path served to
non-local requests — `LocalOnlyMiddleware` (`app/api/exposure.py`, ADR-0012)
answers 403 to everything else.

Meeting preparation has two deliberate paths: **external** — the MCP prompts
(`daily_standup`, `retrospective`, `planning`) instruct a connected chat AI
(Claude/ChatGPT) to call Atlas's MCP tools; and **internal** — `POST
/api/meetings/prep` starts a stored run (`GET` reads the latest; ADR-0023) that builds the same digest (`MeetingContext` = advisor context
+ delivery health + aging WIP, rendered by `render_meeting_context`) and sends
it to the OpenRouter advisor (`AdvisorPort.prepare_meeting`), so Atlas works
stand-alone. The `dora` MCP tool and the advisor digest render DORA
through the same `render_dora`. Meeting types are backed by learnable
personas (`daily_standup`, `retrospective`, `planning` in the `Persona`
enum) that reuse the persona feedback/reflect/guidance machinery
unchanged.
