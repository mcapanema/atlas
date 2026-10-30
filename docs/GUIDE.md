# Atlas user guide

The detail behind the [README](../README.md): each view, how to run Atlas,
how to get data in, chat access, and upgrade notes.

- [Views](#views)
- [Run Atlas](#run-atlas)
- [First sync](#first-sync)
- [Automatic sync](#automatic-sync)
- [Chat access from Claude and ChatGPT (MCP)](#chat-access-from-claude-and-chatgpt-mcp)
- [After upgrading Atlas](#after-upgrading-atlas)

## Views

Atlas reads your Linear workspace, and optionally your GitHub repositories,
and turns their history into these views (sidebar groups in the app):

**Overview**
- **Executive** (`/`) — one row per team: Delivery Health, flow metrics with
  their change against the prior window, DORA deploys per week and change
  failure rate (for teams with a mapped repository), and how accurate past
  forecasts turned out. An at-risk row expands to its weakest health
  components and a 7-day lead-time sparkline.

**Delivery**
- **Teams** (`/teams`) — a team's Delivery Health: the overall score plus a
  tile, with its reason, for each weighted component (predictability, flow,
  stability, risk; efficiency is off by default — weights live in Metric
  rules); Lead/Cycle Time, Throughput, WIP, Blocked Time and Flow
  Efficiency; flow charts; **Time in state**, which marks the state where
  completed work spends the most time (the bottleneck); the four **DORA**
  metrics with their bands, once a repository is mapped to the team; Aging
  WIP with each item's owner, a stop icon on blocked items and > P50 / > P85
  age flags; and a Monte Carlo completion forecast. **Sync team** refreshes
  just that team from Linear.
- **Projects** (`/projects`) — the same analytics scoped to one project,
  without DORA (it is measured per team). A project that spans several
  teams reads the workspace rules (ADR-0020).
- **Work Items** (`/work-items`) — every synced item, with its event
  timeline, time in each state, and blocked periods.

**Intelligence** (needs `ATLAS_OPENROUTER_API_KEY`)
- **Advisor** (`/advisor`) — AI explanations and prioritized recommendations
  grounded in the computed metrics; your feedback teaches it over time.
  Advice is generated in the background and kept: it reloads with the page.
- **Meetings** (`/meetings`) — prep for daily standups, retrospectives and
  planning, kept the same way. A retro covers the team's sprint length by
  default.

**Setup**
- **Organizations** (`/organizations`) — the workspaces Atlas has synced,
  and the people who own work items. Click a person's **Display name** to
  override how their name shows; syncs never overwrite it.
- **Connectors** (`/connectors`) — Linear status, **Sync now**, the GitHub
  card that maps repositories to teams, and the **Auto sync** schedule; see
  [First sync](#first-sync).
- **Metric rules** (`/metric-rules`) — how metrics are computed (what
  counts as blocked, lifecycle, when tracking started, working days and
  holidays, waiting states, incident labels, health scales and weights,
  sprint length…), set for the whole workspace or overridden per team.
  Changing a metric rule recomputes history in the background; sprint
  length only sets the Meetings default.
  By default only workflow states named like 'Blocked' and the labels you
  list count as blocked; Linear 'blocked by' relations and blocked-named
  labels are opt-in (ADR-0026). **Export** and **Import** share the rules as
  a file between workspaces (ADR-0019).

Every number is computed by Atlas from synced events. The AI explains
numbers; it never produces them.

## Run Atlas

### Configuration

Copy `.env.example` to `.env` and adjust as needed — every variable is
documented there (`make install` does this automatically if `.env` doesn't
exist yet). Defaults work out of the box for local development; real
environment variables (Docker Compose, your platform, etc.) always take
precedence over `.env`.

### Option 1: Docker (recommended — zero local setup)

Prerequisite: Docker with Compose.

```bash
make docker-up
```

Builds the frontend and backend into a single image, runs database migrations
on startup, and serves Atlas at http://localhost:8000. Data lives in
`data/atlas.db`, the same file the native setup below uses, so you can switch
between the two and keep your data. Run one at a time: `make dev`, `make run`
and `make migrate` refuse to start while the Docker app is up. Stop with
`make docker-down`.
Atlas is served to this machine only — opening it from another device on the
LAN is refused (ADR-0012).

### Option 2: Makefile (native)

Prerequisites: Python 3.13+, `uv`, Node.js (the major in `web/.nvmrc`), npm.

```bash
make install   # install backend + frontend dependencies
make migrate   # apply database migrations
make dev       # run backend + frontend dev servers together (Ctrl+C stops both)
```

Backend API: http://localhost:8000 · Frontend dev server: http://localhost:5173
(proxies `/api` and `/health` to the backend).

For a single-service production-style run — builds the frontend, applies
migrations, then serves everything from FastAPI on port 8000:

```bash
make run
```

Run `make help` for the full list of shortcuts. For CI, git hooks and
Dependabot, see [CONTRIBUTING.md](../CONTRIBUTING.md).

<details>
<summary>Equivalent commands without <code>make</code></summary>

These skip the Docker check `make` performs: stop the Docker app
(`docker compose down`) before running them, since both use `data/atlas.db`.

```bash
# Install
uv sync
cd web && npm ci && cd ..
test -f .env || cp .env.example .env   # keeps an existing .env

# Migrate
uv run alembic upgrade head

# Development mode (two processes)
# Terminal 1 — backend API on http://localhost:8000
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Vite dev server (proxies /api and /health to the backend)
cd web && npm run dev

# Production mode (single service)
cd web && npm run build && cd ..
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

</details>

## First sync

A fresh Atlas has no data. To fill it:

1. Set `ATLAS_LINEAR_API_KEY` in `.env` (Linear → Settings → Security &
   access → Personal API keys) and restart Atlas.
2. Open **Connectors** and click **Sync now**. The sync runs in the
   background; the Linear card shows its result when it finishes.
3. Optional, for DORA: set `ATLAS_GITHUB_TOKEN` and `ATLAS_GITHUB_OWNER`,
   restart, then map each repository to a team in the GitHub card and click
   **Sync GitHub**. Incidents come from Linear issues with an incident
   label (Metric rules → **Incident labels**).
4. Optional, for Advisor and Meetings: set `ATLAS_OPENROUTER_API_KEY` and
   restart.
5. Set an **Auto sync** schedule (see [Automatic sync](#automatic-sync)).

Until its keys are set, a connector shows "Not configured" (Linear) or "Not
set up" (GitHub), and its sync requests return `409`.

## Automatic sync

On the Connectors page, the **Auto sync** card schedules each organization's
syncs: Linear, then GitHub after each successful Linear sync when GitHub is
configured (a failed GitHub sync only logs). Pick the days, a time window,
an interval, and a timezone (e.g. Mon–Fri, 08:00–18:00, every 2 h,
America/Sao_Paulo). While Atlas runs, it syncs at each slot; a slot missed
while it was off syncs once at startup. The card shows the next run and the
last run's result, in the schedule's timezone. **Sync now** still works any
time, and it counts for a scheduled run due within the next 15 minutes, so
that one is skipped (ADR-0014).

To refresh one team without waiting, use **Sync team** on the Team
Dashboard. It fetches only that team's issues and never deletes anything;
items removed in Linear are pruned by the next organization sync.

## Chat access from Claude and ChatGPT (MCP)

Atlas exposes an MCP server so you can ask about your teams' delivery from a
chat interface: meeting briefs for daily standups, retros, reviews, and
planning, with drill-down tools and a data-refresh action.

### 1. Enable the endpoint

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"   # generate a token
echo 'ATLAS_MCP_TOKEN=<paste-it>' >> .env
make run
```

The MCP endpoint is now at `http://localhost:8000/mcp/<token>/` (trailing
slash matters). Anyone with the full URL can read delivery data — treat it
like a password. Leave `ATLAS_MCP_TOKEN` empty to disable the endpoint
entirely.

### 2. Expose it to cloud clients (claude.ai / ChatGPT)

Cloud chat apps can only reach public HTTPS URLs. Run a tunnel while you want
chat access:

```bash
cloudflared tunnel --url http://localhost:8000   # or: ngrok http 8000
```

Copy the printed HTTPS origin; your connector URL is
`https://<origin>/mcp/<token>/`.

Only the MCP endpoint answers through the tunnel. Atlas serves its UI and
REST API to this machine only: a request that arrives through a proxy (it
carries `X-Forwarded-For` or a similar header) or under any hostname other
than `localhost`/`127.0.0.1`/`[::1]` gets `403` everywhere except
`/mcp/<token>/` (ADR-0012). The token is still that endpoint's only
credential — treat the full URL like a password.

### 3. Connect a client

- **claude.ai / Claude Desktop**: Settings → Connectors → *Add custom
  connector* → paste the URL (no OAuth).
- **Claude Code**: `claude mcp add --transport http atlas
  http://localhost:8000/mcp/<token>/` (no tunnel needed locally).
- **ChatGPT**: enable *Developer mode* (Settings → Apps & Connectors →
  Advanced), then *Create connector* → paste the URL, no authentication.

### 4. Use it

Tools: `list_scopes`, `meeting_brief` (the one-call digest), `aging_wip`,
`list_work_items`, `forecast` (supports what-if `remaining`/`target_date`),
`dora` (a team's four DORA metrics with their bands, once a repository is
mapped to the team), `run_sync`. Prompts: `daily_standup`, `retrospective`,
`planning` — pick one from the client's prompt menu and it orchestrates the
tools for you. Everything is computed by Atlas; the chat model explains, it
never invents numbers it wasn't given.

## After upgrading Atlas

### Rebuild synced events

Synced events are never rewritten by a normal sync, so a release that fixes
how Linear history is mapped only reaches existing data through a rebuild:

```bash
curl -X POST http://localhost:8000/api/connectors/linear/sync \
  -H 'content-type: application/json' -d '{"rebuild": true}'
```

It answers `202` with a background sync job; read its state, phase, counts
and error with the job's `id`:

```bash
curl http://localhost:8000/api/connectors/linear/jobs/<id>
```

It re-derives every synced issue's events and rewrites snapshot history;
feedback, learned guidance, and metric rules are kept (ADR-0013).

### Blocked time after the explicit blocked signal

From this release, Linear 'blocked by' relations and blocked-named labels
no longer count as blocked by default (ADR-0026). After `make migrate`
(Docker and `make run` apply it for you), Atlas recomputes history at
startup, so blocked time, flow efficiency and health can change. To
count them again, turn on **Count Linear 'blocked by' relations** or
**Labels named like 'Blocked'** in Metric rules, for the workspace or one
team.

### Sync once for people

After the upgrade that adds people, run **Sync now** once: owners read
Unassigned until the next sync.

### An older `.env` and the database path

A `.env` created before the database moved to `data/` pins
`ATLAS_DATABASE_URL` to `./atlas.db`. Change it to `./data/atlas.db` (as in
`.env.example`), or local runs and Docker will use different databases.
