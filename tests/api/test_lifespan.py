from collections.abc import Callable
from pathlib import Path
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.auto_sync import AutoSyncRunner
from app.main import create_app, lifespan


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
