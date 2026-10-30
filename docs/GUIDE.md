# Atlas user guide

This guide gives the detail behind the [README](../README.md): the views,
how to run Atlas, how to get data in, chat access, and upgrade notes.

- [Views](#views)
- [Run Atlas](#run-atlas)
- [First sync](#first-sync)
- [Automatic sync](#automatic-sync)
- [Chat access from Claude and ChatGPT (MCP)](#chat-access-from-claude-and-chatgpt-mcp)
- [After upgrading Atlas](#after-upgrading-atlas)

## Views

Atlas reads your Linear workspace and, if you connect it, your GitHub
repositories. It shows their history in the views below. The groups are
the same as in the sidebar of the app.

Atlas calculates every number from synced events. The AI explains the
numbers. It never makes a number.

### Overview

- **Executive** (`/`): one row for each team. A row shows Delivery Health,
  the flow metrics and their change from the prior window, and the accuracy
  of past forecasts. If a repository is mapped to the team, the row also
  shows DORA deploys per week and change failure rate. If a team is at
  risk, expand its row to see its weakest health components and a 7-day
  sparkline of lead time.

### Delivery

- **Teams** (`/teams`): the dashboard for one team. It shows:
  - Delivery Health: the overall score, and one tile with a reason for each
    weighted component (predictability, flow, stability, risk). Efficiency
    is off by default. You set the weights in Metric rules.
  - Lead Time, Cycle Time, Throughput, WIP, Blocked Time and Flow
    Efficiency, and the flow charts.
  - **Time in state**: the time that completed work spent in each state.
    The state with the most time is the bottleneck.
  - The four **DORA** metrics and their bands, if a repository is mapped to
    the team.
  - Aging WIP: each item's owner, a stop icon on blocked items, and age
    flags (> P50 / > P85).
  - A Monte Carlo forecast of completion.

  **Sync team** gets new data from Linear for this team only.
- **Projects** (`/projects`): the same analytics for one project, but
  without DORA, because Atlas measures DORA for each team. A project can
  span several teams. Such a project uses the workspace rules (ADR-0020).
- **Work Items** (`/work-items`): all synced items. Each item shows its
  event timeline, its time in each state, and its blocked periods.

### Intelligence

These views need `ATLAS_OPENROUTER_API_KEY`.

- **Advisor** (`/advisor`): AI explanations and recommendations in order of
  priority. They come from the calculated metrics. Your feedback teaches
  the Advisor over time. Atlas makes the advice in the background and keeps
  it, so the advice is there when you open the page again.
- **Meetings** (`/meetings`): preparation for daily standups,
  retrospectives and planning. Atlas keeps it in the same way. By default,
  a retrospective covers the sprint length of the team.

### Setup

- **Organizations** (`/organizations`): the workspaces that Atlas synced,
  and the people who own work items. To change how a name shows, click the
  person's **Display name**. A sync never changes a display name.
- **Connectors** (`/connectors`): the Linear status, **Sync now**, the
  GitHub card where you map repositories to teams, and the **Auto sync**
  schedule. See [First sync](#first-sync).
- **Metric rules** (`/metric-rules`): the rules that Atlas uses to
  calculate metrics. Examples are: what counts as blocked, the lifecycle,
  when tracking started, working days and holidays, waiting states,
  incident labels, health scales and weights, and sprint length. You set
  the rules for the whole workspace, and you can change them for one team.
  - When you change a rule, Atlas calculates the history again in the
    background. Sprint length only sets the default for Meetings.
  - By default, only two things count as blocked: workflow states with a
    name like 'Blocked', and the labels that you list. Linear 'blocked by'
    relations and labels with a name like 'Blocked' are optional
    (ADR-0026).
  - Use **Export** and **Import** to share the rules as a file between
    workspaces (ADR-0019).

## Run Atlas

### Configuration

All settings are in `.env`. To create it, copy `.env.example` to `.env`.
`.env.example` describes each variable. If `.env` does not exist,
`make install` creates it. The default values work for local development.
Real environment variables (for example from Docker Compose) always
override `.env`.

### Option 1: Docker (recommended)

Prerequisite: Docker with Compose.

```bash
make docker-up
```

This command builds the frontend and backend into one image, applies the
database migrations when it starts, and serves Atlas at
http://localhost:8000. To stop Atlas, run `make docker-down`.

- The data is in `data/atlas.db`. The native setup uses the same file, so
  you can change between the two and keep your data.
- Run only one setup at a time. While the Docker app runs, `make dev`,
  `make run` and `make migrate` do not start.
- Atlas is available only on this machine. It refuses requests from other
  devices on the network (ADR-0012).

### Option 2: Makefile (native)

Prerequisites: Python 3.13+, `uv`, Node.js (the major version in
`web/.nvmrc`), npm.

```bash
make install   # install backend + frontend dependencies
make migrate   # apply database migrations
make dev       # run backend + frontend dev servers together (Ctrl+C stops both)
```

The backend API is at http://localhost:8000. The frontend development
server is at http://localhost:5173. It sends `/api` and `/health` to the
backend.

To run one service, as in production, use `make run`. It builds the
frontend, applies the migrations, and serves everything from FastAPI on
port 8000.

```bash
make run
```

To see all shortcuts, run `make help`. For CI, git hooks and Dependabot,
see [CONTRIBUTING.md](../CONTRIBUTING.md).

<details>
<summary>Equivalent commands without <code>make</code></summary>

These commands do not do the Docker check that `make` does. Before you run
them, stop the Docker app (`docker compose down`), because both use
`data/atlas.db`.

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

A new Atlas has no data. To get data:

1. Set `ATLAS_LINEAR_API_KEY` in `.env`. To get a key, go to Linear →
   Settings → Security & access → Personal API keys.
2. Restart Atlas.
3. Open **Connectors** and click **Sync now**. The sync runs in the
   background. When it finishes, the Linear card shows the result.
4. Optional, for DORA:
   1. Set `ATLAS_GITHUB_TOKEN` and `ATLAS_GITHUB_OWNER` in `.env`, then
      restart Atlas.
   2. In the GitHub card, map each repository to a team.
   3. Click **Sync GitHub**.

   Incidents are Linear issues with an incident label. You set these labels
   in Metric rules → **Incident labels**.
5. Optional, for Advisor and Meetings: set `ATLAS_OPENROUTER_API_KEY` in
   `.env`, then restart Atlas.
6. Set an **Auto sync** schedule. See [Automatic sync](#automatic-sync).

If a key is not set, its connector shows "Not configured" (Linear) or "Not
set up" (GitHub), and its sync requests return `409`.

## Automatic sync

The **Auto sync** card on the Connectors page sets a sync schedule for each
organization. Each sync gets Linear data first. If GitHub is configured and
the Linear sync is successful, it then gets GitHub data. If the GitHub sync
fails, Atlas only writes it to the log.

- To set the schedule, select the days, a time window, an interval and a
  time zone. Example: Mon–Fri, 08:00–18:00, every 2 h, America/Sao_Paulo.
- While Atlas runs, it syncs at each slot. If Atlas was off at a slot, it
  syncs one time when it starts.
- The card shows the next run and the result of the last run, in the time
  zone of the schedule.
- You can use **Sync now** at any time. If a scheduled run is due in the
  next 15 minutes, **Sync now** replaces it, and Atlas skips that run
  (ADR-0014).

To get new data for one team immediately, use **Sync team** on the Team
Dashboard. It gets only the issues of that team and does not delete data.
The next sync of the organization removes the items that were deleted in
Linear.

## Chat access from Claude and ChatGPT (MCP)

Atlas has an MCP server. Use it to ask a chat client about the delivery of
your teams. It gives meeting briefs for daily standups, retrospectives,
reviews and planning. It also has tools for more detail and a tool that
gets new data.

### 1. Turn on the endpoint

```bash
python -c "import secrets; print(secrets.token_urlsafe(24))"   # generate a token
echo 'ATLAS_MCP_TOKEN=<paste-it>' >> .env
make run
```

The MCP endpoint is at `http://localhost:8000/mcp/<token>/`. The slash at
the end is necessary. To turn off the endpoint, leave `ATLAS_MCP_TOKEN`
empty.

**Do not share the full URL. Anyone with the URL can read your delivery
data.**

### 2. Make it available to cloud clients (claude.ai, ChatGPT)

Cloud chat apps can only use public HTTPS URLs. When you want chat access,
run a tunnel:

```bash
cloudflared tunnel --url http://localhost:8000   # or: ngrok http 8000
```

Copy the HTTPS origin that the tunnel shows. Your connector URL is
`https://<origin>/mcp/<token>/`.

Through the tunnel, only the MCP endpoint answers. Atlas serves its UI and
REST API only to this machine (ADR-0012). It returns `403` for all paths
except `/mcp/<token>/` when a request:

- comes through a proxy (it has `X-Forwarded-For` or a similar header), or
- uses a hostname other than `localhost`, `127.0.0.1` or `[::1]`.

The token is the only credential for the endpoint.

### 3. Connect a client

- **claude.ai / Claude Desktop**: go to Settings → Connectors → *Add custom
  connector*, and paste the URL. No OAuth is necessary.
- **Claude Code**: run `claude mcp add --transport http atlas
  http://localhost:8000/mcp/<token>/`. On this machine, you do not need a
  tunnel.
- **ChatGPT**: turn on *Developer mode* (Settings → Apps & Connectors →
  Advanced). Then click *Create connector* and paste the URL. No
  authentication is necessary.

### 4. Use it

Tools:

- `list_scopes`
- `meeting_brief`: one call that gives a full summary.
- `aging_wip`
- `list_work_items`
- `forecast`: supports what-if values for `remaining` and `target_date`.
- `dora`: the four DORA metrics of a team and their bands, if a repository
  is mapped to the team.
- `run_sync`

Prompts: `daily_standup`, `retrospective`, `planning`. Select a prompt in
the prompt menu of the client, and it uses the tools for you.

Atlas calculates every number. The chat model explains the numbers. It
does not make numbers that Atlas did not give.

## After upgrading Atlas

### Rebuild synced events

A normal sync does not change events that it already synced. Some releases
fix how Atlas reads Linear history. To apply such a fix to existing data,
start a rebuild:

```bash
curl -X POST http://localhost:8000/api/connectors/linear/sync \
  -H 'content-type: application/json' -d '{"rebuild": true}'
```

The response is `202` with a background sync job. To read the state,
phase, counts and error of the job, use its `id`:

```bash
curl http://localhost:8000/api/connectors/linear/jobs/<id>
```

The rebuild makes the events of each synced issue again, and writes the
snapshot history again. It keeps feedback, learned guidance and metric
rules (ADR-0013).

### Blocked time after the explicit blocked signal

In this release, Linear 'blocked by' relations and labels with a name like
'Blocked' do not count as blocked by default (ADR-0026).

1. Run `make migrate`. Docker and `make run` do this for you.
2. Start Atlas. It calculates the history again, so blocked time, flow
   efficiency and health can change.
3. If you want to count these sources again, go to Metric rules. Turn on
   **Count Linear 'blocked by' relations** or **Labels named like
   'Blocked'**, for the workspace or for one team.

### Sync once for people

After the upgrade that adds people, click **Sync now** one time. Until the
next sync, owners show as Unassigned.

### An older `.env` and the database path

If you created `.env` before the database moved to `data/`, it sets
`ATLAS_DATABASE_URL` to `./atlas.db`. Change it to `./data/atlas.db`, as in
`.env.example`. If you do not change it, local runs and Docker use
different databases.
