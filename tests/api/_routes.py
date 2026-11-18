"""The one place that lists an app's /api routes.

Targets FastAPI 0.156: `include_router()` keeps its routes as nested
`_IncludedRouter` branches, so `app.routes` holds no `APIRoute` for them. Their
`effective_candidates()` yield route contexts with the prefixed `path`, `methods`
and `dependencies` (router-level dependencies included). Semi-private API: if a
FastAPI upgrade breaks it, fix it here, once; the non-vacuity asserts in the
callers fail loudly instead of passing on an empty list.
"""

from collections.abc import Iterable, Iterator
from typing import Any

from fastapi import FastAPI

Pair = tuple[str, str]


def _flat(routes: Iterable[Any]) -> Iterator[Any]:
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from _flat(route.effective_candidates())
        else:
            yield route


def api_route_objects(app: FastAPI) -> list[Any]:
    """Every route object whose path starts with /api/ (path, methods, dependencies)."""
    return [
        r for r in _flat(app.routes) if getattr(r, "methods", None) and r.path.startswith("/api/")
    ]


def api_routes(app: FastAPI) -> set[Pair]:
    return {(m, r.path) for r in api_route_objects(app) for m in r.methods if m != "HEAD"}
