# 12. The UI and REST API are local-only; MCP is the remote surface

Date: 2026-10-05

## Status

Accepted. Narrows the open user-auth question in ADR-0005.

## Context

Atlas has no user authentication. Chat access (the MCP endpoint) needs a
public HTTPS URL, which the README gets with a tunnel (cloudflared, ngrok)
pointed at the app's port. A tunnel forwards the whole origin: the SPA,
every `/api/*` route (sync, metric-rule writes, paid LLM calls), and
`/docs` were public to anyone who learned the tunnel hostname — the MCP
path token protected only `/mcp/<token>`. The same lack of a Host check
left a local install open to DNS-rebinding pages.

## Decision

`LocalOnlyMiddleware` (`app/api/exposure.py`) answers `403` to every HTTP
request that is not local — Host a loopback name (`localhost`,
`127.0.0.1`, `::1`, `0.0.0.0`, any port) and no forwarding header (`Forwarded`,
`X-Forwarded-For`, `X-Forwarded-Host`, `X-Real-IP`, `CF-Connecting-IP`) —
except under the MCP mount `/mcp/<ATLAS_MCP_TOKEN>`. Two independent
signals catch tunnels: cloudflared keeps the public Host by default, and
both cloudflared and ngrok add `X-Forwarded-For`. `ATLAS_MCP_TOKEN` must be
at least 24 URL-safe characters and is masked in the access log.
`docker-compose.yml` and `make run` bind to loopback.

## Consequences

- The documented tunnel exposes only the MCP endpoint.
- Opening Atlas from another machine (LAN IP, a reverse proxy) is refused
  by design. Serving it to others needs ADR-0005's auth decision first,
  plus an allowed-hosts setting.
- The Host check guards browsers (DNS rebinding) and tunnels. What keeps
  other machines out is the loopback bind (compose `127.0.0.1:8000:8000`,
  `make run --host 127.0.0.1`): a LAN client that forges `Host: localhost`
  would otherwise pass.
- The MCP tools' in-process REST calls use a loopback Host.
