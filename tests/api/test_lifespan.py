from collections.abc import Callable
from pathlib import Path
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncEngine

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
