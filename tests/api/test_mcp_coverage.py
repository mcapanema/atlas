"""Every /api route is an explicit MCP decision: a tool calls it, or NOT_FOR_MCP names it."""

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api.mcp_coverage import NOT_FOR_MCP
from app.domain.auth.entities import McpAccess
from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "app" / "api"
GUIDE = ROOT / "docs" / "GUIDE.md"
Pair = tuple[str, str]


def _flat_routes(routes: Iterable[Any]) -> Iterator[Any]:
    # FastAPI 0.156 keeps include_router() results as nested `_IncludedRouter`
    # branches; their `effective_candidates()` carry the prefixed path and methods.
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from _flat_routes(route.effective_candidates())
        else:
            yield route


def api_routes(app: FastAPI) -> set[Pair]:
    return {
        (method, route.path)
        for route in _flat_routes(app.routes)
        if getattr(route, "methods", None) and route.path.startswith("/api/")
        for method in route.methods
        if method != "HEAD"
    }


def _call_api_nodes() -> list[tuple[str, ast.Call]]:
    found: list[tuple[str, ast.Call]] = []
    for path in sorted(API_DIR.glob("mcp_*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name == "call_api":
                found.append((f"{path.name}:{node.lineno}", node))
    return found


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def mcp_calls() -> set[Pair]:
    calls: set[Pair] = set()
    for _, node in _call_api_nodes():
        if len(node.args) < 3:
            continue
        method, route = _literal(node.args[1]), _literal(node.args[2])
        if method is not None and route is not None:
            calls.add((method, route))
    return calls


def undecided(app: FastAPI) -> set[Pair]:
    return api_routes(app) - mcp_calls() - NOT_FOR_MCP.keys()


def test_every_api_route_is_an_mcp_decision() -> None:
    missing = undecided(create_app())
    assert not missing, (
        "New /api routes need an MCP decision. Call each from a tool in app/api/mcp_*.py, "
        "or add it to NOT_FOR_MCP in app/api/mcp_coverage.py with a reason:\n"
        + "\n".join(f"  {m} {p}" for m, p in sorted(missing))
    )


def test_mcp_tools_pass_literal_routes() -> None:
    bad = [
        where
        for where, node in _call_api_nodes()
        if len(node.args) < 3 or _literal(node.args[1]) is None or _literal(node.args[2]) is None
    ]
    assert not bad, "call_api needs a literal method and route template at: " + ", ".join(bad)


def test_every_mcp_call_names_a_real_route() -> None:
    assert mcp_calls() - api_routes(create_app()) == set()


def test_no_route_is_both_used_and_excluded() -> None:
    assert mcp_calls() & NOT_FOR_MCP.keys() == set()


def test_every_exclusion_is_a_real_route_with_a_reason() -> None:
    assert NOT_FOR_MCP.keys() <= api_routes(create_app())
    assert all(reason.strip() for reason in NOT_FOR_MCP.values())


def test_the_gate_reports_an_unexposed_route() -> None:
    app = create_app()

    @app.get("/api/zz-probe")
    async def probe() -> None: ...

    assert undecided(app) == {("GET", "/api/zz-probe")}


async def test_every_mcp_tool_is_in_the_guide() -> None:
    server = create_app().state.mcp_servers[McpAccess.READ_WRITE]
    guide = GUIDE.read_text()
    missing = [t.name for t in await server.list_tools() if f"`{t.name}`" not in guide]
    assert not missing, f"Add to docs/GUIDE.md section 'Use it': {missing}"
