from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

# FastAPI's own /docs and /openapi.json are switched off in create_app(): they
# bypass routers, so they could not take the sign-in guard. These routes go
# through the guarded loop like every other /api router.
router = APIRouter(prefix="/api", include_in_schema=False)


@router.get("/openapi.json")
async def openapi_schema(request: Request) -> dict[str, Any]:
    app: FastAPI = request.app
    return app.openapi()


@router.get("/docs")
async def swagger_ui() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="Atlas API")
