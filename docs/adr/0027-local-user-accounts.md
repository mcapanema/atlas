# 27. Local user accounts with server-side sessions

Date: 2026-10-31

## Status

Accepted. Closes the user-auth question left open by ADR-0005; keeps
ADR-0012.

## Context

Atlas had no user authentication. ADR-0012 made the UI and REST API
local-only, which protects against tunnels and DNS rebinding but not
against another person on the same machine or network path. Engineering
managers now need a signed-in user, an admin role, and a path to Google
SSO later.

## Decision

- Multiple users, each admin or not. Only admins list, add, reset the
  password of, and remove users. Every user changes their own password and
  signs out.
- While no user exists, the sign-in screen becomes "Create the first
  account". That account is an admin. Later users are added on a
  Setup → Users page.
- Passwords use stdlib `hashlib.scrypt` (`n=2**14, r=8, p=1, dklen=32`,
  16-byte random salt), stored as
  `scrypt$16384$8$1$<salt>$<hash>` (urlsafe base64) and compared with
  `hmac.compare_digest`. The stored parameters are used to verify, so they
  can rise later. Length is 12 to 128 characters; the maximum bounds the
  work per request. No new dependency.
- Email is `strip().lower()`, at most 254 characters, and unique.
- A session is an opaque `secrets.token_urlsafe(32)` token in the
  `atlas_session` cookie (`HttpOnly`, `SameSite=Lax`, `Path=/`, `Max-Age`
  14 days, `Secure` off). The database stores only its SHA-256. The
  lifetime is absolute (14 days), with no sliding renewal.
- Every `/api/*` router except `/api/auth` needs a signed-in user;
  `/api/users` needs an admin.
- The MCP facade keeps working without a user. Its in-process REST calls
  carry `X-Atlas-Internal: <token>`, a per-process random value made in
  `create_app()` and compared with `secrets.compare_digest`.
- `LocalOnlyMiddleware` (ADR-0012) does not change.

## Consequences

- Google SSO adds an identity table keyed `(provider, subject)` to
  `user_id`. A user with `password_hash = NULL` cannot sign in with a
  password, so SSO-only users fit the same `users` row.
- Lifting ADR-0012 first needs `Secure` cookies, allowed hosts, and login
  rate limiting.
- If the only admin forgets the password, nobody can reset it through the
  app, and the fix is a database edit. This is a deliberate ceiling; a CLI
  reset command is the upgrade path.
- A removed user or a user with a reset password loses open sessions on the
  next request.
