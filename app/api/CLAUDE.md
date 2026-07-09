# app/api/

Presentation layer — FastAPI routers + DTOs. Depends on Application
(services) and, only for dependency wiring, on the concrete Infrastructure
adapter (`app/api/deps.py` is the composition root — the one place
Presentation is allowed to know a concrete adapter exists).

## Rules

- Never return an ORM model or a Domain entity directly from a route
  handler — always `<Concept>Read.model_validate(...)`. DTOs live in
  `schemas.py`, one `<Concept>Create` (input, validated) /
  `<Concept>Read` (output, `from_attributes=True`) pair per concept.
- `deps.py` holds the FastAPI `Depends` chain: `get_session`
  (commit-on-success / rollback-on-error, request-scoped) →
  `get_<concept>_service` (constructs the service with the concrete
  repository). See the `ponytail:` comment on `get_session` for the
  deliberate scope boundary (no explicit Unit-of-Work yet, only needed once
  a single request must coordinate writes across multiple repositories) —
  read it before "fixing" it.
- One router per concept (`<concept>.py`,
  `APIRouter(prefix="/api/<concept>", tags=[...])`), registered in
  `app/main.py`'s `create_app()`. Router registration order matters:
  `mount_spa()` (in `app/infrastructure/static.py`) must be registered
  last, after every API router, or its catch-all swallows API routes.

## Testing

`tests/api/` drives the full stack through an `httpx.AsyncClient` (the
`client` fixture in `tests/conftest.py`, backed by the in-memory test DB)
— this is the layer where you assert on HTTP status codes and JSON shapes,
not internals.
