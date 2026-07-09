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
on startup, and serves Atlas at http://localhost:8000. Data persists across
restarts in the `atlas-data` Docker volume. Stop with `make docker-down`.

## Option 2: Makefile (native)

Prerequisites: Python 3.13+, `uv`, Node.js LTS, npm.

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

```bash
# Install
uv sync
cd web && npm install && cd ..
cp .env.example .env

# Migrate
uv run alembic upgrade head

# Development mode (two processes)
# Terminal 1 — backend API on http://localhost:8000
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — Vite dev server (proxies /api and /health to the backend)
cd web && npm run dev

# Production mode (single service)
cd web && npm run build && cd ..
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

</details>

## Continuous Integration

Every push and pull request runs backend and frontend checks in parallel,
each split into four phases: test suite, type check, lint, and a dependency
security audit (`pip-audit` for the backend, `npm audit` for the frontend).
Run the same checks locally with `make check` (or individually — `make
test`, `make typecheck`, `make lint`, `make security`).

[Dependabot](https://docs.github.com/en/code-security/dependabot) opens
weekly PRs for outdated backend (`uv`), frontend (`npm`), and GitHub Actions
dependencies — see `.github/dependabot.yml`.

---

For more information about the architecture, engineering principles, and domain model, see the documentation in the `docs/` directory.
