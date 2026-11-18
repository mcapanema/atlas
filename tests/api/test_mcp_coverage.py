"""Every /api route is an explicit MCP decision: a tool calls it, or NOT_FOR_MCP names it."""

import ast
from pathlib import Path

from fastapi import FastAPI

from app.api.mcp_coverage import NOT_FOR_MCP
from app.domain.auth.entities import McpAccess
from app.main import create_app
from tests.api._routes import Pair, api_routes

ROOT = Path(__file__).resolve().parents[2]
API_DIR = ROOT / "app" / "api"
GUIDE = ROOT / "docs" / "GUIDE.md"


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


def test_the_scans_are_not_vacuous() -> None:
    routes = api_routes(create_app())
    assert len(routes) > 20
    assert ("GET", "/api/teams") in routes
    assert ("GET", "/api/organizations") in mcp_calls()


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


async def test_write_tools_are_only_on_the_read_write_server() -> None:
    # A tool registered outside add_config_write_tools is visible to read tokens.
    servers = create_app().state.mcp_servers
    read = {t.name: t for t in await servers[McpAccess.READ].list_tools()}
    both = {t.name: t for t in await servers[McpAccess.READ_WRITE].list_tools()}

    # run_sync syncs data, not settings: it is on both servers by design (ADR-0032).
    writes = {n for n, t in read.items() if not (t.annotations and t.annotations.read_only_hint)}
    assert writes == {"run_sync"}
    assert set(read) < set(both)
    for name in set(both) - set(read):
        annotations = both[name].annotations
        assert annotations is not None, name
        assert annotations.read_only_hint is False, name
