# Atlas

> **Atlas is a Delivery Intelligence Platform.**

Atlas transforms software delivery events into actionable engineering intelligence.

It continuously observes software delivery, measures flow efficiency, forecasts outcomes, and provides AI-powered guidance to help Engineering Managers make better decisions.

Rather than replacing project management tools, Atlas sits on top of them as an intelligence layer, helping engineering organizations understand how work flows through their systems and how delivery performance impacts business outcomes.

---

# Why Atlas?

Modern engineering teams generate enormous amounts of delivery data.

Issues move across workflows.

Pull requests are merged.

Deployments happen.

Projects slip.

Deadlines move.

But very few tools answer the questions engineering leaders actually care about.

- Why is delivery slowing down?
- Where is the bottleneck?
- Which project is at risk?
- Which team needs attention today?
- What should I improve next?
- Are our process improvements actually working?
- How does engineering performance affect business outcomes?

Atlas exists to answer those questions.

---

# Philosophy

Atlas follows a simple philosophy:

```text
Observe
    ↓
Understand
    ↓
Predict
    ↓
Advise
    ↓
Improve
```

### Observe

Collect delivery events from engineering systems such as Linear and transform them into a unified delivery model.

### Understand

Measure software delivery using Flow Metrics inspired by Lean and Kanban. Events are the source of truth, and all metrics are derived from them.

### Predict

Use statistical models—not AI—to forecast delivery confidence, completion probability, and project risk.

### Advise

Use AI to explain what is happening, identify bottlenecks, recommend improvements, and help Engineering Managers make better decisions.

### Improve

Measure the impact of every improvement and continuously evolve engineering delivery based on evidence rather than intuition.

---

## Core Principles

- **Delivery Intelligence over Project Management** — Atlas complements tools like Linear instead of replacing them.
- **AI explains. Statistics predict.** — Statistical models generate forecasts; AI interprets them and provides guidance.
- **Events are the source of truth** — Delivery events are immutable, and every metric is derived from them.
- **Platform-agnostic domain model** — Internal concepts never depend on vendor-specific tools or APIs.
- **Explainability first** — Every recommendation should be traceable back to the data and reasoning that produced it.
- **Domain-Driven Design** — The domain model is the heart of the platform and remains independent of frameworks.
- **Monolithic deployment, modular architecture** — A single deployable application with clear architectural boundaries.
- **Simplicity over complexity** — Prefer boring, maintainable solutions and introduce complexity only when it creates measurable value.

---

# What's in Atlas

Atlas reads your Linear workspace and turns its history into these views
(sidebar groups in the app):

**Overview**
- **Executive** (`/`) — one row per team: Delivery Health, flow metrics with
  their change against the prior window, and how accurate past forecasts
  turned out. An at-risk row expands to its weakest health components and a
  7-day lead-time sparkline.

**Delivery**
- **Teams** (`/teams`) — a team's Delivery Health: the overall score plus a
  tile, with its reason, for each weighted component (predictability, flow,
  stability, risk; efficiency is off by default — weights live in Metric
  rules); Lead/Cycle Time, Throughput, WIP, Blocked Time and Flow
  Efficiency; flow charts; Aging WIP with each item's owner, a stop icon on blocked items and > P50 / > P85 age flags; and a Monte
  Carlo completion forecast. **Sync team** refreshes just that team from
  Linear.
- **Projects** (`/projects`) — the same analytics scoped to one project.
- **Work Items** (`/work-items`) — every synced item, with its event
  timeline, time in each state, and blocked periods.

**Intelligence** (needs `ATLAS_OPENROUTER_API_KEY`)
- **Advisor** (`/advisor`) — AI explanations and prioritized recommendations
  grounded in the computed metrics; your feedback teaches it over time.
- **Meetings** (`/meetings`) — prep for daily standups, retrospectives and
  planning. A retro covers the team's sprint length by default.

**Setup**
- **Organizations** (`/organizations`) — the workspaces Atlas has synced.
- **Connectors** (`/connectors`) — Linear status, **Sync now**, and the
  **Auto sync** schedule.
- **Metric rules** (`/metric-rules`) — how metrics are computed (what counts as blocked,
  lifecycle, health scales and weights, sprint length…), set for the whole
  workspace or overridden per team. Changing a metric rule recomputes
  history in the background; sprint length only sets the Meetings default.

Every number is computed by Atlas from synced events. The AI explains
numbers; it never produces them.

---

# How do I run it?

## Clone the repository

```bash
git clone <repository-url>
cd atlas
```

## Configuration

Copy `.env.example` to `.env` and adjust as needed — every variable is
documented there (`make install` does this automatically if `.env` doesn't
exist yet). Defaults work out of the box for local development; real
environment variables (Docker Compose, your platform, etc.) always take
precedence over `.env`.

## Option 1: Docker (recommended — zero local setup)

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

## Option 2: Makefile (native)

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

Run `make help` for the full list of shortcuts, including `make test`,
`make lint`, `make typecheck`, and `make check` (the full CI gate, run locally).

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

## Continuous Integration

Every push and pull request runs backend and frontend checks in parallel,
each split into four phases: test suite (with coverage floors, and on pull
requests ≥ 90% coverage of the changed lines), type check,
lint (including formatting, complexity ceilings, and — on the frontend —
dead-code detection), and a dependency security audit (`pip-audit` for the
backend, `npm audit` for the frontend). A ninth check builds the production
Docker image. `make check` runs all nine locally, after syncing
dependencies to the lockfiles the way CI does (Docker must be running), or
run them individually: `make test`, `make typecheck`, `make lint`,
`make security`; `make format` fixes formatting.
`make hooks` installs two git hooks: pre-commit (ruff and prettier checks on
the staged files, plus the whole frontend eslint run whenever a `web/`
TypeScript file is staged) and pre-push, which runs `make check` on the
commit being pushed (`git push --no-verify` skips it). Expect side effects from
pre-push:
`uv sync --locked` removes packages added ad hoc with `uv pip install`;
after a package-file change `npm ci` reinstalls `web/node_modules`, which
breaks a running `make dev` until restarted; and during the hook's run
(about 40s) pre-commit stashes your unstaged edits, so files briefly look
reverted — don't edit them until the push finishes.

[Dependabot](https://docs.github.com/en/code-security/dependabot) opens
weekly PRs for outdated backend (`uv`), frontend (`npm`), GitHub Actions,
and Docker base-image dependencies. Minor/patch bumps are grouped into one
PR per ecosystem, except Docker base images, which come one PR per image —
see `.github/dependabot.yml`.

## Automatic sync

On the Connectors page, the **Auto sync** card schedules each organization's
Linear sync: pick the days, a time window, an interval, and a timezone (e.g.
Mon–Fri, 08:00–18:00, every 2 h, America/Sao_Paulo). While Atlas runs, it
syncs at each slot; a slot missed while it was off syncs once at startup. The
card shows the next run and the last run's result, in the schedule's
timezone. **Sync now** still works any time, and it counts for a scheduled
run due within the next 15 minutes, so that one is skipped (ADR-0014).
To refresh one team without waiting, use **Sync team** on the Team
Dashboard. It fetches only that team's issues and never deletes anything;
items removed in Linear are pruned by the next organization sync.

## After upgrading Atlas

### Rebuild synced events

Synced events are never rewritten by a normal sync, so a release that fixes
how Linear history is mapped only reaches existing data through a rebuild:

```bash
curl -X POST http://localhost:8000/api/connectors/linear/sync \
  -H 'content-type: application/json' -d '{"rebuild": true}'
```

It re-derives every synced issue's events and rewrites snapshot history;
feedback, learned guidance, and metric rules are kept (ADR-0013).

### An older `.env` and the database path

A `.env` created before the database moved to `data/` pins
`ATLAS_DATABASE_URL` to `./atlas.db`. Change it to `./data/atlas.db` (as in
`.env.example`), or local runs and Docker will use different databases.

## Chat access from Claude & ChatGPT (MCP)

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
`run_sync`. Prompts: `daily_standup`, `retrospective`, `planning` — pick one
from the client's prompt menu and it orchestrates the tools for you.
Everything is computed by Atlas; the chat model explains, it never invents
numbers it wasn't given.

---

# Further reading

- [`docs/VISION.md`](docs/VISION.md) — the full product vision.
- [`docs/architecture/overview.md`](docs/architecture/overview.md) — how
  the code is organized, slice by slice.
- [`docs/adr/`](docs/adr/) — the architecture decisions and why they were
  made.
- [`PRODUCT.md`](PRODUCT.md) — the design brief for the UI.
