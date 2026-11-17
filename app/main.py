import asyncio
import logging
import os
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from dotenv import dotenv_values
from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.types import ASGIApp

from app.api import (
    advisor,
    auth,
    codebases,
    connectors,
    docs,
    events,
    forecasts,
    health,
    mcp_server,
    mcp_tokens,
    meetings,
    metric_rules,
    metrics,
    organizations,
    people,
    personas,
    projects,
    sync_schedules,
    teams,
    users,
    work_items,
)
from app.api.advice_runner import AdviceRunner
from app.api.auto_sync import AutoSyncRunner
from app.api.deps import (
    datadog_source,
    github_code_source,
    linear_data_source,
    require_signed_in,
)
from app.api.exposure import LocalOnlyMiddleware
from app.api.mcp_gate import McpGate
from app.api.recompute import RecomputeRunner
from app.api.sync_jobs import SyncJobRunner
from app.config import get_settings
from app.domain.advisor.port import AdvisorError
from app.domain.auth.entities import McpAccess
from app.domain.auth.throttle import SignInThrottle
from app.domain.sync.port import DataSourceError
from app.infrastructure.database.lease import acquire_sqlite_lease
from app.infrastructure.database.session import build_sessionmaker
from app.infrastructure.secrets import cipher_for
from app.infrastructure.static import mount_spa

logger = logging.getLogger(__name__)


# An MCP token rides in the request path, which uvicorn logs per request.
_MCP_PATH = re.compile(r"/mcp/[^/\s\"?]+")


class _RedactSecret(logging.Filter):
    """Masks every MCP token in log-record arguments — uvicorn's access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                _MCP_PATH.sub("/mcp/***", arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def _mask_in_access_log() -> None:
    access = logging.getLogger("uvicorn.access")
    for stale in [f for f in access.filters if isinstance(f, _RedactSecret)]:
        access.removeFilter(stale)  # create_app() runs once per test app
    access.addFilter(_RedactSecret())


# Credentials entered on the Connectors page replaced these env keys (ADR-0027).
_IGNORED_ENV_KEYS = (
    "ATLAS_LINEAR_API_KEY",
    "ATLAS_GITHUB_TOKEN",
    "ATLAS_GITHUB_OWNER",
    "ATLAS_OPENROUTER_API_KEY",
    "ATLAS_ADVISOR_MODEL",
)


def _warn_about_ignored_env_keys() -> None:
    dotenv = dotenv_values(".env")  # Settings' env_file; a missing file reads as empty
    found = [key for key in _IGNORED_ENV_KEYS if os.environ.get(key) or dotenv.get(key)]
    if found:  # names only — never the values
        logger.warning(
            "Ignored settings: %s. Enter connector keys and the advisor model on the "
            "Connectors page.",
            ", ".join(found),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    _warn_about_ignored_env_keys()
    # Create (or check) the credential key now: a corrupt key file fails
    # startup with its path, not every request that touches a credential.
    cipher_for(settings.secret_key_file)
    # Before the journal-mode switch: a second process on a shared SQLite file
    # must fail here, not flip the mode under the one already running.
    lease = acquire_sqlite_lease(settings.database_url)
    # Each MCP server's session manager must run for its streamable-HTTP app
    # to accept requests. Entered before the background tasks start and
    # closed after they stop: entering and closing await, and an await lets a
    # pending task begin the pool checkout the finally below must not cut off.
    mcp_managers = AsyncExitStack()
    try:
        sessionmaker = build_sessionmaker(
            settings.database_url,
            echo=settings.db_echo,
            journal_mode=settings.sqlite_journal_mode,
        )
        for mcp in app.state.mcp_servers.values():
            await mcp_managers.enter_async_context(mcp.session_manager.run())
    except BaseException:
        await mcp_managers.aclose()
        lease.release()
        raise
    app.state.sessionmaker = sessionmaker
    runner = RecomputeRunner(sessionmaker)
    app.state.recompute_runner = runner
    # Finish any history recompute a restart interrupted, without delaying
    # startup; resume() logs and gives up if the DB isn't migrated yet.
    resume = asyncio.create_task(runner.resume())
    advice_runner = AdviceRunner(sessionmaker)
    app.state.advice_runner = advice_runner
    # Fail the advice runs a restart interrupted; same give-up-and-log rule.
    interrupted = asyncio.create_task(advice_runner.fail_interrupted())
    sync_jobs = SyncJobRunner(sessionmaker, recompute=runner)
    app.state.sync_job_runner = sync_jobs
    auto_sync = AutoSyncRunner(
        sessionmaker,
        linear_data_source,
        jobs=sync_jobs,
        code_source_factory=github_code_source,
        datadog_source_factory=datadog_source,
    )
    app.state.auto_sync_runner = auto_sync
    # Ticks at once: a slot missed while Atlas was off syncs now (ADR-0014).
    auto_sync.start()
    try:
        yield
    finally:
        try:
            # Cancel before the first await: a task cancelled while it checks out
            # a pool connection orphans it, so never let one start just to stop it.
            resume.cancel()
            interrupted.cancel()
            await auto_sync.close()
            await sync_jobs.close()
            await advice_runner.close()
            await asyncio.gather(resume, interrupted, return_exceptions=True)
            await runner.close()
            await mcp_managers.aclose()
            engine = sessionmaker.kw["bind"]
            assert isinstance(engine, AsyncEngine)  # noqa: S101 — narrow Any for mypy; always true
            await engine.dispose()
        finally:
            # Even after a failed shutdown step: a lease left behind would refuse
            # the other side's next start for LEASE_TTL_SECONDS.
            lease.release()


def create_app() -> FastAPI:
    # Stdlib logging only (review H3). basicConfig is a no-op if the root
    # logger already has handlers, so embedders/tests keep their own config.
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # FastAPI's own docs bypass routers, so they can't be guarded; docs.py
    # serves them at /api/docs behind sign-in instead.
    app = FastAPI(
        title="Atlas",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Failed sign-ins must outlive a request (ADR-0028).
    app.state.sign_in_throttle = SignInThrottle()
    # Per-process secret for the MCP facade's in-process calls (ADR-0028).
    app.state.internal_token = secrets.token_urlsafe(32)
    app.include_router(health.router)
    app.include_router(auth.router)
    # Everything else needs a signed-in user; test_auth_guard.py fails on a
    # /api route left out of this loop.
    for router in (
        docs.router,
        organizations.router,
        teams.router,
        people.router,
        projects.router,
        work_items.router,
        events.router,
        metrics.router,
        forecasts.router,
        connectors.router,
        codebases.router,
        advisor.router,
        personas.router,
        meetings.router,
        metric_rules.router,
        sync_schedules.router,
        users.router,
        mcp_tokens.router,
    ):
        app.include_router(router, dependencies=[Depends(require_signed_in)])

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

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # FastAPI's default echoes each rejected value back as "input"; a
        # rejected credential body must never reach a response or a log.
        errors = [{k: v for k, v in error.items() if k != "input"} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})

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

    if get_settings().mcp_token:
        logger.warning(
            "ATLAS_MCP_TOKEN is no longer used; create a token on the AI access page "
            "(Setup → AI access)."
        )
    # UI and API to this machine only; the MCP mount to anyone holding a
    # user's MCP token — the documented tunnel exposes nothing else.
    app.add_middleware(LocalOnlyMiddleware, public_prefix="/mcp")
    _mask_in_access_log()
    # One server per access level; McpGate checks the token in the path and
    # forwards to the matching one (ADR-0032).
    app.state.mcp_servers = {
        access: mcp_server.build_mcp_server(app, access) for access in McpAccess
    }
    # mcp 2.x moved these transport-mode kwargs off the MCPServer
    # constructor onto streamable_http_app() itself.
    streamable_apps: dict[McpAccess, ASGIApp] = {
        access: mcp.streamable_http_app(
            stateless_http=True,
            json_response=True,
            streamable_http_path="/",
            transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        )
        for access, mcp in app.state.mcp_servers.items()
    }
    app.mount("/mcp/{token}", McpGate(app, streamable_apps))

    mount_spa(app)  # catch-all — must be registered after all API routers
    return app


app = create_app()
