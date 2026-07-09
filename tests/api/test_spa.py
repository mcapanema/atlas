from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure import static
from app.main import create_app


async def test_spa_root_served_when_dist_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Atlas</title>")
    monkeypatch.setattr(static, "WEB_DIST", dist)

    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        root = await client.get("/")
        unknown = await client.get("/organizations")  # client-side route → SPA fallback
        missing_api = await client.get("/api/does-not-exist")

    assert root.status_code == 200
    assert "Atlas" in root.text
    assert unknown.status_code == 200  # SPA fallback, not 404
    assert missing_api.status_code == 404  # API namespace is never masked by the SPA
