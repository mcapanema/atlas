import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import (
    advisor,
    connectors,
    events,
    forecasts,
    health,
    mcp_server,
    meetings,
    metric_rules,
    metrics,
    organizations,
    personas,
    projects,
    sync_schedules,
    teams,
    work_items,
)
from app.api.auto_sync import AutoSyncRunner
from app.api.deps import linear_data_source
from app.api.exposure import LocalOnlyMiddleware
from app.api.recompute import RecomputeRunner
from app.config import get_settings
from app.domain.advisor.port import AdvisorError
from app.domain.sync.port import DataSourceError
from app.infrastructure.database.session import build_sessionmaker
from app.infrastructure.static import mount_spa

logger = logging.getLogger(__name__)


class _RedactSecret(logging.Filter):
    """Masks a secret in log-record arguments — the MCP token in uvicorn's access log."""

    def __init__(self, secret: str) -> None:
        super().__init__()
        self._secret = secret

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                arg.replace(self._secret, "***") if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def _mask_in_access_log(secret: str) -> None:
    access = logging.getLogger("uvicorn.access")
    for stale in [f for f in access.filters if isinstance(f, _RedactSecret)]:
        access.removeFilter(stale)  # create_app() runs once per test app
    access.addFilter(_RedactSecret(secret))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    sessionmaker = build_sessionmaker(settings.database_url, echo=settings.db_echo)
    app.state.sessionmaker = sessionmaker
    runner = RecomputeRunner(sessionmaker)
    app.state.recompute_runner = runner
    # Finish any history recompute a restart interrupted, without delaying
    # startup; resume() logs and gives up if the DB isn't migrated yet.
    resume = asyncio.create_task(runner.resume())
    auto_sync = AutoSyncRunner(sessionmaker, linear_data_source)
    app.state.auto_sync_runner = auto_sync
    # Ticks at once: a slot missed while Atlas was off syncs now (ADR-0014).
    auto_sync.start()
    try:
        async with AsyncExitStack() as stack:
            # The MCP session manager only exists when ATLAS_MCP_TOKEN is set
            # (create_app skips the mount otherwise) and must run for the
            # streamable-HTTP endpoint to accept requests.
            mcp = getattr(app.state, "mcp", None)
            if mcp is not None:
                await stack.enter_async_context(mcp.session_manager.run())
            yield
    finally:
        # Cancel before the first await: a task cancelled while it checks out
        # a pool connection orphans it, so never let one start just to stop it.
        resume.cancel()
        await auto_sync.close()
        await asyncio.gather(resume, return_exceptions=True)
        await runner.close()
        engine = sessionmaker.kw["bind"]
        assert isinstance(engine, AsyncEngine)  # noqa: S101 — narrow Any for mypy; always true
        await engine.dispose()


def create_app() -> FastAPI:
    # Stdlib logging only (review H3). basicConfig is a no-op if the root
    # logger already has handlers, so embedders/tests keep their own config.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = FastAPI(title="Atlas", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(organizations.router)
    app.include_router(teams.router)
    app.include_router(projects.router)
    app.include_router(work_items.router)
    app.include_router(events.router)
    app.include_router(metrics.router)
    app.include_router(forecasts.router)
    app.include_router(connectors.router)
    app.include_router(advisor.router)
    app.include_router(personas.router)
    app.include_router(meetings.router)
    app.include_router(metric_rules.router)
    app.include_router(sync_schedules.router)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        # Domain entity __post_init__ invariants (e.g. blank name, tz-naive
        # datetime) raise ValueError after Pydantic's own validation passes —
        # this is the one place all 5 create endpoints route through.
        # ponytail: this also catches ValueError from enum coercion in
        # to_domain() on read paths (GET), which would misreport a real
        # data-integrity bug as a 422 client error. Scope more narrowly to
        # the create-endpoint layer if that read-path case ever fires.
        logger.warning(
            "ValueError handled as 422 on %s %s: %s", request.method, request.url.path, exc
        )
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        # Unique-index / FK violations (duplicate external_id, two concurrent
        # syncs inserting the same entity). The DB is the last line of defense
        # here — report a conflict, not a server bug. Violations that surface
        # at get_session's commit land here too: that teardown runs before
        # the response is sent (SessionDep's scope="function").
        return JSONResponse(
            status_code=409,
            content={"detail": "Conflicting write: resource already exists"},
        )

    @app.exception_handler(DataSourceError)
    async def data_source_error_handler(request: Request, exc: DataSourceError) -> JSONResponse:
        # An upstream delivery system (Linear) failed — our fault to report,
        # not the client's: 502, never 500 or 422.
        logger.error("Data source failure on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(
            status_code=502, content={"detail": f"Upstream data source error: {exc}"}
        )

    @app.exception_handler(AdvisorError)
    async def advisor_error_handler(request: Request, exc: AdvisorError) -> JSONResponse:
        # The LLM adapter failed (API error, off-schema reply) — 502.
        logger.error("Advisor failure on %s %s: %s", request.method, request.url.path, exc)
        return JSONResponse(status_code=502, content={"detail": f"Advisor error: {exc}"})

    settings = get_settings()
    # UI and API to this machine only; the MCP mount (if any) to anyone
    # holding its secret URL — the documented tunnel exposes nothing else.
    app.add_middleware(
        LocalOnlyMiddleware,
        public_prefix=f"/mcp/{settings.mcp_token}" if settings.mcp_token else None,
    )
    if settings.mcp_token:
        # The token rides in the request path, which uvicorn logs per request.
        _mask_in_access_log(settings.mcp_token)
        # Secret-URL auth: connector UIs (claude.ai, ChatGPT) can't send
        # custom headers, so the token rides in the path. No token, no route.
        mcp = mcp_server.build_mcp_server(app)
        app.state.mcp = mcp
        # mcp 2.x moved these transport-mode kwargs off the MCPServer
        # constructor onto streamable_http_app() itself.
        app.mount(
            f"/mcp/{settings.mcp_token}",
            mcp.streamable_http_app(
                stateless_http=True,
                json_response=True,
                streamable_http_path="/",
                transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
            ),
        )

    mount_spa(app)  # catch-all — must be registered after all API routers
    return app


app = create_app()
