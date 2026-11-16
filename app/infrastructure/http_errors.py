"""Readable text for an httpx failure, shared by the connector and AI adapters."""

import httpx


def describe_http_error(exc: httpx.HTTPError) -> str:
    """`ClassName: message`, or just `ClassName` — httpx timeouts carry no message."""
    name = type(exc).__name__
    return f"{name}: {exc}" if str(exc) else name
