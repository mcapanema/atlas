# Atlas

Atlas is a delivery intelligence platform for engineering managers. It
reads delivery data from Linear and GitHub, measures how work flows,
forecasts risk, and uses AI to explain the results.

Atlas does not replace your project management tool. It adds an analysis
layer on top of it.

## What Atlas answers

- Why is delivery slow?
- Where is the bottleneck?
- Which project is at risk?
- Which team needs attention today?
- What do we improve next, and did the last change help?

## How it works

| Step | What Atlas does |
|---|---|
| Observe | Syncs work items from Linear, and pull requests and deployments from GitHub. |
| Understand | Calculates flow metrics, Delivery Health and DORA metrics from the synced events. |
| Predict | Uses statistics (Monte Carlo), not AI, to forecast completion and risk. |
| Advise | Uses AI to explain the numbers and recommend improvements. |

Atlas calculates every number from synced events. The AI explains the
numbers. It never makes a number.

## Main views

- **Executive**: health, flow, DORA and forecast accuracy for all teams on
  one page.
- **Teams** and **Projects**: metrics, charts, the bottleneck, aging work
  and a completion forecast.
- **Advisor** and **Meetings**: AI advice, and preparation for standups,
  retrospectives and planning.
- **Metric rules**: how Atlas calculates each metric, for the workspace or
  for one team.

## Quick start

Prerequisite: Docker with Compose.

1. Clone the repository and create the configuration file:

   ```bash
   git clone https://github.com/mcapanema/atlas.git
   cd atlas
   cp .env.example .env
   ```

2. Set `ATLAS_LINEAR_API_KEY` in `.env`.
3. Start Atlas with `make docker-up`.
4. Open http://localhost:8000.
5. Go to **Connectors** and click **Sync now**.

The [user guide](docs/GUIDE.md) tells how to run Atlas without Docker,
connect GitHub, turn on the AI, schedule syncs, and connect a chat client.

## Documentation

- [User guide](docs/GUIDE.md): the views, setup, sync, chat access and
  upgrade notes.
- [Vision](docs/VISION.md): the product vision and principles.
- [Architecture](docs/architecture/overview.md) and [ADRs](docs/adr/): how
  the code is organized, and why.
- [Contributing](CONTRIBUTING.md): CI, git hooks and Dependabot.
- [Product brief](PRODUCT.md): the design brief for the UI.
