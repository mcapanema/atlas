import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest import mock

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.auto_sync import AutoSyncRunner
from app.api.sync_jobs import SyncJobRequest, SyncJobRunner, get_sync_job_runner
from app.domain.organizations.entities import Organization
from app.domain.sync.source import SourceTeam
from app.infrastructure.database.base import Base
from app.infrastructure.repositories.organizations import SqlAlchemyOrganizationRepository
from app.main import create_app, lifespan
from tests.fakes import FakeDataSource


async def test_lifespan_disposes_the_engine_on_shutdown(
    settings_env: Callable[..., None], tmp_path: Path
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path}/lifespan.db")
    app = create_app()
    with mock.patch.object(AsyncEngine, "dispose", autospec=True) as dispose:
        async with lifespan(app):
            pass
    dispose.assert_awaited_once()


async def test_lifespan_starts_auto_sync_and_stops_it_on_shutdown(
    settings_env: Callable[..., None], tmp_path: Path
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path}/lifespan.db", linear_api_key="")
    app = create_app()
    with mock.patch.object(AutoSyncRunner, "tick", autospec=True, return_value=0):
        async with lifespan(app):
            runner = app.state.auto_sync_runner
            assert isinstance(runner, AutoSyncRunner)
            assert runner.running
        assert not runner.running


async def test_lifespan_cancels_a_running_sync_job(
    settings_env: Callable[..., None], tmp_path: Path
) -> None:
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path}/lifespan.db", linear_api_key="")
    app = create_app()
    entered = asyncio.Event()

    class BlockingSource(FakeDataSource):
        async def fetch_teams(self) -> list[SourceTeam]:
            entered.set()
            await asyncio.Event().wait()
            return []

    with mock.patch.object(AutoSyncRunner, "tick", autospec=True, return_value=0):
        async with lifespan(app):
            engine = app.state.sessionmaker.kw["bind"]
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            org = Organization(name="Acme")
            async with app.state.sessionmaker() as session:
                await SqlAlchemyOrganizationRepository(session).add(org)
                await session.commit()
            jobs = app.state.sync_job_runner
            assert isinstance(jobs, SyncJobRunner)
            job = jobs.start(
                SyncJobRequest(org.id, "organization", "manual"),
                BlockingSource(),
            )
            task = jobs._task
            assert task is not None
            await asyncio.wait_for(entered.wait(), 5)
        assert job.state == "running"  # cancelled: no finish written
        assert task.cancelled()


async def test_lifespan_auto_sync_and_routes_share_one_sync_job_runner(
    settings_env: Callable[..., None], tmp_path: Path
) -> None:
    # One lock for every sync: a route's job runner is the one auto sync defers to.
    settings_env(database_url=f"sqlite+aiosqlite:///{tmp_path}/lifespan.db", linear_api_key="")
    app = create_app()
    with mock.patch.object(AutoSyncRunner, "start", autospec=True):
        async with lifespan(app):
            jobs = get_sync_job_runner(Request({"type": "http", "app": app}))
            async with jobs.lock:
                # Skips without touching the (unmigrated) DB: it sees the lock.
                assert await app.state.auto_sync_runner.tick() == 0
