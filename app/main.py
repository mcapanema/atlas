from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import events, health, organizations, projects, teams, work_items
from app.config import get_settings
from app.infrastructure.database.session import build_sessionmaker
from app.infrastructure.static import mount_spa


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.sessionmaker = build_sessionmaker(settings.database_url, echo=settings.db_echo)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Atlas", version="0.1.0", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(organizations.router)
    app.include_router(teams.router)
    app.include_router(projects.router)
    app.include_router(work_items.router)
    app.include_router(events.router)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        # Domain entity __post_init__ invariants (e.g. blank name, tz-naive
        # datetime) raise ValueError after Pydantic's own validation passes —
        # this is the one place all 5 create endpoints route through.
        # ponytail: this also catches ValueError from enum coercion in
        # to_domain() on read paths (GET), which would misreport a real
        # data-integrity bug as a 422 client error. Scope more narrowly to
        # the create-endpoint layer if that read-path case ever fires.
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    mount_spa(app)  # catch-all — must be registered after all API routers
    return app


app = create_app()
