"""Who may reach what: the UI and REST API are local-only; MCP is the remote surface.

Atlas has no user authentication (ADR-0005). A request is local when its
Host is a loopback name and no proxy forwarded it. Anything else — a tunnel
(cloudflared and ngrok add X-Forwarded-For; cloudflared also keeps the
public Host), a LAN client, a DNS-rebinding page — may reach only the MCP
mount, whose secret path is its credential (ADR-0012).
"""

import re

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketClose

# ponytail: a fixed loopback allowlist. Add ATLAS_ALLOWED_HOSTS — together
# with the ADR-0005 user-auth decision — if Atlas is ever served to other
# machines.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # noqa: S104 — a Host name to accept, not a bind address
_FORWARDING_HEADERS = frozenset(
    {b"forwarded", b"x-forwarded-for", b"x-forwarded-host", b"x-real-ip", b"cf-connecting-ip"}
)


# name[:port] or [ipv6][:port] — nothing else is a Host Atlas recognises.
_HOST = re.compile(r"(?:\[(?P<v6>[^\]]*:[^\]]*)\]|(?P<name>[^:\[\]]+))(?::\d{1,5})?")


def _hostname(host: str) -> str | None:
    """The Host header's name without its port; None when it isn't a well-formed Host."""
    match = _HOST.fullmatch(host)
    return (match["v6"] or match["name"]) if match else None


def is_local(scope: Scope) -> bool:
    """Sent straight to this machine under a loopback name, not forwarded by a proxy.

    Fails closed: no Host, a malformed one, or more than one is not local.
    """
    headers: list[tuple[bytes, bytes]] = scope["headers"]
    if any(name in _FORWARDING_HEADERS for name, _ in headers):
        return False
    hosts = [value.decode("latin-1").lower() for name, value in headers if name == b"host"]
    return len(hosts) == 1 and _hostname(hosts[0]) in _LOOPBACK_HOSTS


class LocalOnlyMiddleware:
    """403 (HTTP) / close 1008 (websocket) for non-local requests outside the MCP prefix."""

    def __init__(self, app: ASGIApp, public_prefix: str | None = None) -> None:
        self._app = app
        self._public_prefix = public_prefix

    def _is_public(self, path: str) -> bool:
        prefix = self._public_prefix
        return prefix is not None and (path == prefix or path.startswith(prefix + "/"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        guarded = scope["type"] in ("http", "websocket")  # lifespan passes through
        if not guarded or is_local(scope) or self._is_public(scope["path"]):
            await self._app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await WebSocketClose(code=1008)(scope, receive, send)  # policy violation, pre-accept
            return
        response = PlainTextResponse(
            "Atlas serves its UI and API to this machine only", status_code=403
        )
        await response(scope, receive, send)
