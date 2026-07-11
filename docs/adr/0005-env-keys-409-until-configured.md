# 5. Integrations configure via ATLAS_* env keys and answer 409 until configured

Date: 2026-07-11 (backfilled; decided in Phase 2b, 2026-07-09; extended to the advisor in Phase 6, 2026-07-10)

## Status

Accepted

## Context

External integrations (the Linear connector, the OpenRouter advisor) need
credentials. Atlas deploys single-tenant, run by the team that owns the
data — there is no user management, and building one to store two API keys
would be ceremony. But an unconfigured integration must fail
understandably, not as a 500 or a silent no-op.

## Decision

- All runtime configuration, credentials included, lives on the
  pydantic-settings `Settings` model (`app/config.py`), `ATLAS_`-prefixed,
  documented in `.env.example` (the source of truth for which variables
  exist).
- A FastAPI dependency backed by an integration (`get_delivery_data_source`,
  `get_advisor_port` in `app/api/deps.py`) raises `409 Conflict` with a
  human-readable detail while its key is unset. The frontend renders these
  as "Not configured" states rather than errors.

## Consequences

- Deployment configuration is one env file; misconfiguration is
  self-describing at exactly the endpoint that needs the key.
- The 409-until-configured convention is the contract every future
  integration follows.
- User-level authentication remains an open decision — deliberately neither
  blocked nor prejudged by this one.
