# 32. Per-user MCP tokens in the URL path

Date: 2026-11-17

## Status

Accepted. Amends ADR-0012 (the public paths are now `/mcp/<token>/…`) and
replaces the `ATLAS_MCP_TOKEN` setting.

## Context

Chat access (the MCP endpoint) used one shared secret, `ATLAS_MCP_TOKEN`,
set in the environment and mounted as `/mcp/<token>`. Anyone with the URL
had every tool, nobody could tell whose connector made a call, and a leak
meant a restart with a new value for every user. Atlas now has users
(ADR-0028), and the MCP facade is about to get write tools, so access must
belong to a user and have a level.

claude.ai and ChatGPT custom connectors cannot send custom headers, and
OAuth would need an Atlas-hosted authorization server reachable from the
internet, while ADR-0012 keeps the UI and REST API local-only.

## Decision

- Each user creates, lists and revokes their own MCP tokens on the AI
  access page (Setup → AI access; `GET/POST /api/mcp-tokens`,
  `DELETE /api/mcp-tokens/{id}`). A token is `atlas_mcp_` plus
  `secrets.token_urlsafe(32)`. Atlas stores only its SHA-256 hash and the
  last 4 characters as a hint; the secret appears once, in the create
  response.
- The token rides in the URL path, `/mcp/<token>/`, for the same reason
  the old shared secret did: connector UIs cannot send headers, and
  Atlas-hosted OAuth conflicts with ADR-0012. There is no `Authorization`
  header path.
- `McpGate` (`app/api/mcp_gate.py`), mounted at `/mcp/{token}`, looks the
  token up per request and forwards to one of two MCP servers, one per
  access level. An unknown or revoked token gets `404 Not Found`, the same
  as any unknown path. Two servers, not one told the level per request:
  in stateless mode the MCP SDK runs tools in its session manager's own
  task group, so request context set by the gate would not reach them.
- Two access levels. `read` has every read tool plus `run_sync`: a sync
  refreshes data from the source and changes no setting a user entered.
  `read_write` adds the write tools. The UI defaults to `read`.
- Tokens do not expire; a user revokes them, and removing a user deletes
  their tokens (`ON DELETE CASCADE`). Ceiling: a leaked token works until
  someone notices. Upgrade path: an `expires_at` column, checked in
  `McpTokenService.authenticate`, with an expiry picker on the AI access
  page.
- `last_used_at` is written at most once per 5 minutes per token
  (`LAST_USED_RESOLUTION`), so chat traffic does not take SQLite's write
  lock on every call. The page shows "last used" to that resolution. The
  write is best effort: if it fails (for example, `database is locked`),
  Atlas logs a warning and still serves the token. A failed lookup still
  refuses the request.
- `ATLAS_MCP_TOKEN` stops working: its validator and `.env.example` entry
  go. If it is still set (environment or `.env`), Atlas logs one warning at
  startup that names the AI access page, and does not serve it.
- uvicorn's access log masks every `/mcp/<token>` path as `/mcp/***`.

## Consequences

- Each connector has its own token, so a user revokes one leaked or
  unused connector without touching the others.
- The MCP endpoint is always mounted; with no tokens, every request to it
  is a 404.
- An install upgraded with `ATLAS_MCP_TOKEN` set loses chat access until a
  user creates a token; the startup warning says where.
- `LocalOnlyMiddleware` makes every `/mcp/<segment>/…` path public, the
  shape of the mount. `/mcp`, `/mcp/` and `/mcp/<token>` without the
  trailing slash stay local-only, so a tunnel never reaches the SPA
  catch-all there. The gate, not the middleware, decides which token is
  valid.
- Each MCP request costs one indexed lookup by token hash.
