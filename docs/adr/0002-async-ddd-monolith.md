# 2. Async DDD monolith with SQLAlchemy

Date: 2026-07-08

## Status

Accepted

## Context

Atlas is a Delivery Intelligence Platform — it syncs delivery data from external
engineering systems, derives flow metrics and forecasts from it, and explains them
with an AI advisor (see [docs/VISION.md](../VISION.md) for the full product vision).
Phase 1 establishes the foundation. Two decisions shape every later task:
concurrency model and layering.

The platform is IO-bound by nature — it will call external connector APIs (Linear,
GitHub) and LLM providers. `pytest-asyncio` is already in the required stack.

## Decision

- **Async throughout**: SQLAlchemy 2.0 async engine + `aiosqlite`, async repositories,
  async services, async FastAPI endpoints. Retrofitting sync → async later would touch
  every repository, service, and endpoint, so we pay the cost once, up front.
- **Domain-Driven Design** with strict inward dependencies. The Domain layer is pure
  Python with zero framework imports; Infrastructure adapts SQLAlchemy to Domain
  `Protocol` ports.
- **Single deployable monolith**: FastAPI serves both the API and the compiled SPA.

## Consequences

- Clean testability: Application logic tests against in-memory fakes; the Domain has no
  framework to mock.
- Portability to PostgreSQL is preserved because DB-specific code lives only in
  Infrastructure.
- Async adds some ceremony (async fixtures, `StaticPool` for in-memory test DBs). This
  is accepted as the cost of a concurrency model that fits the platform's IO-bound future.
