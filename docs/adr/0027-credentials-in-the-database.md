# 27. Credentials live encrypted in the database

Date: 2026-10-31

## Status

Accepted. Supersedes ADR-0005's credential storage; its
409-until-configured contract stands.

## Context

Linear, GitHub and OpenRouter credentials were `ATLAS_*` env keys. To
change one, a manager edited `.env` and restarted Atlas. A wrong key showed
up only when the first sync or advice request failed.

## Decision

- Credentials for Linear (key), GitHub (token and owner) and OpenRouter
  (key and advisor model) are entered on the Connectors page and stored in
  the database. The `ATLAS_LINEAR_API_KEY`, `ATLAS_GITHUB_TOKEN`,
  `ATLAS_GITHUB_OWNER`, `ATLAS_OPENROUTER_API_KEY` and `ATLAS_ADVISOR_MODEL`
  variables no longer exist, with no fallback and no import of old values.
- Secrets are encrypted with Fernet. The key is created on first use in a
  key file next to the database (`ATLAS_SECRET_KEY_FILE`, default
  `data/atlas.key`, mode 0600).
- Atlas checks a credential against its provider before it stores it. A
  rejected credential answers 422 ("Could not verify the … credentials: …")
  and is not stored. A provider that is down, answers 5xx or answers 429
  gives 502 and nothing is stored. `DataSourceError.status` tells the two
  apart.
- For OpenRouter, the check also looks the advisor model up in OpenRouter's
  public model list, filtered to models with structured outputs. An exact id
  match is required; otherwise the save answers 422.
- A GitHub or OpenRouter `PUT` may omit the secret to change only the owner
  or the model. Atlas keeps the stored secret and checks it again with the
  new setting. With nothing stored, the save answers 422. The Linear key is
  always required.
- The API is write-only: `PUT` and `DELETE`
  `/api/connectors/{linear|github|openrouter}/credentials`. Status
  responses carry a `hint` ("…" plus the last four characters, or "…" for a
  key under 12 characters), never the secret. 422 validation bodies drop the
  submitted `input`.
- `ATLAS_MCP_TOKEN` and the advisor tuning (`ATLAS_ADVISOR_SELF_CRITIQUE`,
  `ATLAS_ADVISOR_MAX_TOKENS`, `ATLAS_ADVISOR_TIMEOUT_SECONDS`) stay env
  variables.

## Consequences

- Back up `data/atlas.key` with `data/atlas.db`. Without the key file the
  stored credentials are unreadable.
- A credential that cannot be decrypted (lost or replaced key file) reads
  as not configured, and Atlas logs a warning that names the integration.
  Saving it again fixes it.
- Users who upgrade enter their keys once on the Connectors page.
- A missing credential still gives `409` on the routes that need it
  (ADR-0005); the detail points at the Connectors page.
