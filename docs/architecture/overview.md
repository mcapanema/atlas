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

`Organization` is the reference implementation. Future concepts (Team, Project, Work Item, Event, Metric) follow the same shape.

## Single-service deployment

FastAPI serves the REST API and, in production, the compiled React app from `web/dist`
(`app/infrastructure/static.py`). In development, Vite serves the frontend and proxies
`/api` + `/health` to FastAPI.

## Persistence

Async SQLAlchemy 2.0 over SQLite (aiosqlite) today; portable to PostgreSQL because all
database-specific code is confined to Infrastructure and types (e.g. `Uuid`) render
per-dialect. Alembic manages schema migrations.
