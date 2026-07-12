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
  `get_<concept>_service` (constructs the service with its concrete
  adapters). See the `ponytail:` comment on `get_session` for the
  deliberate transaction-scope boundary — read it before "fixing" it.
- **409-until-configured**: a dependency backed by an external integration
  (`get_delivery_data_source`, `get_advisor_port`) raises `409 Conflict`
  with a human-readable detail while its `ATLAS_*` key is unset
  (ADR-0005). A new integration follows the same pattern — never a 500,
  never a silent fallback.
- **Analytics scope**: metrics/forecasts/recommendations endpoints take
  `ScopeDep` from `scope.py` — exactly one of `team_id`/`project_id`
  (422 otherwise) and the scope must exist (404). A new scoped endpoint
  reuses it; fabricating empty analytics for an unknown id is a bug (it
  once meant paying for an LLM call on a typo'd UUID).
- **Error semantics belong to `create_app()`'s exception handlers**
  (`app/main.py`): `ValueError` → 422 (domain invariants surfacing after
  Pydantic validation — see the ponytail comment there),
  `IntegrityError` → 409, `DataSourceError` / `AdvisorError` → 502.
  Routers don't try/except these — raise the Domain/port error and let
  the handler translate.
- One router per concept (`<concept>.py`,
  `APIRouter(prefix="/api/<concept>", tags=[...])`), registered in
  `app/main.py`'s `create_app()`. Deliberate exceptions: `health.py`
  serves bare `/health`; `advisor.py` mounts at `/api/recommendations`
  (named for what it returns); `connectors.py` nests actions per vendor
  (`POST /api/connectors/linear/sync`).
- `mount_spa()` must be registered last in `create_app()` — the rule and
  its reason are owned by `app/infrastructure/CLAUDE.md`.
- **MCP facade** (`mcp_server.py`): the MCP server's tools call Atlas's own
  REST API in-process (httpx `ASGITransport`) and return compact text —
  never duplicate scope validation, DTO mapping, or error semantics inside
  a tool, and never return raw endpoint JSON (chat context windows are the
  budget). The endpoint mounts at `/mcp/<ATLAS_MCP_TOKEN>` in `create_app()`
  (before `mount_spa`) only when the token is set, and `lifespan` must run
  `app.state.mcp.session_manager.run()` for it to serve.

## Testing

`tests/api/` drives the full stack through an `httpx.AsyncClient` (the
`client` fixture in `tests/conftest.py`, backed by the in-memory test DB)
— this is the layer where you assert on HTTP status codes and JSON shapes,
not internals.
