"""Who may reach what: the UI and REST API are local-only; MCP is the remote surface.

Atlas has no user authentication (ADR-0005). A request is local when its
Host is a loopback name and no proxy forwarded it. Anything else — a tunnel
(cloudflared and ngrok add X-Forwarded-For; cloudflared also keeps the
public Host), a LAN client, a DNS-rebinding page — may reach only the MCP
mount, whose secret path is its credential (ADR-0012).
"""

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# ponytail: a fixed loopback allowlist. Add ATLAS_ALLOWED_HOSTS — together
# with the ADR-0005 user-auth decision — if Atlas is ever served to other
# machines.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_FORWARDING_HEADERS = frozenset(
    {b"forwarded", b"x-forwarded-for", b"x-forwarded-host", b"x-real-ip", b"cf-connecting-ip"}
)


def _hostname(host: str) -> str:
    """The Host header's name without its port; an IPv6 literal loses its brackets."""
    if host.startswith("["):
        return host[1 : host.find("]")]
    return host.partition(":")[0]


def is_local(scope: Scope) -> bool:
    """Sent straight to this machine under a loopback name, not forwarded by a proxy."""
    headers = dict(scope["headers"])
    if _FORWARDING_HEADERS & headers.keys():
        return False
    host = headers.get(b"host", b"").decode("latin-1").lower()
    return _hostname(host) in _LOOPBACK_HOSTS


class LocalOnlyMiddleware:
    """403 for every non-local HTTP request outside the public (MCP) path prefix."""

    def __init__(self, app: ASGIApp, public_prefix: str | None = None) -> None:
        self._app = app
        self._public_prefix = public_prefix

    def _is_public(self, path: str) -> bool:
        prefix = self._public_prefix
        return prefix is not None and (path == prefix or path.startswith(prefix + "/"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan passes through; Atlas serves no websockets.
        if scope["type"] != "http" or is_local(scope) or self._is_public(scope["path"]):
            await self._app(scope, receive, send)
            return
        response = PlainTextResponse(
            "Atlas serves its UI and API to this machine only", status_code=403
        )
        await response(scope, receive, send)
