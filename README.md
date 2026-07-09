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

## Prerequisites

- Python 3.13+
- `uv`
- Node.js LTS
- npm

## Clone the repository

```bash
git clone <repository-url>
cd atlas
```

## Install dependencies

```bash
uv sync
cd web && npm install && cd ..
```

## Run the database migrations

```bash
uv run alembic upgrade head
```

## Development mode (two processes)

```bash
# Terminal 1 — backend API on http://localhost:8000
uv run fastapi dev app/main.py

# Terminal 2 — Vite dev server (proxies /api and /health to the backend)
cd web && npm run dev
```

## Production mode (single service)

```bash
cd web && npm run build && cd ..
uv run fastapi run app/main.py   # FastAPI serves the API and the compiled React app
```

---

For more information about the architecture, engineering principles, and domain model, see the documentation in the `docs/` directory.
