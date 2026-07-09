from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def mount_spa(app: FastAPI) -> None:
    """Serve the compiled React app. No-op in dev, where Vite serves the frontend."""
    if not WEB_DIST.exists():
        return

    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str) -> FileResponse:
        # API routes are registered before this catch-all, so a request only
        # reaches here if no API route matched. Guard /api explicitly so unknown
        # API paths return 404 instead of the SPA shell.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        return FileResponse(WEB_DIST / "index.html")
