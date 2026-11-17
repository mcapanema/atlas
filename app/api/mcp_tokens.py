from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUserDep, McpTokenServiceDep
from app.api.schemas import McpTokenCreate, McpTokenIssuedRead, McpTokenRead
from app.application.auth.mcp_tokens import UnknownMcpTokenError
from app.domain.auth.entities import McpAccess

router = APIRouter(prefix="/api/mcp-tokens", tags=["mcp-tokens"])


@router.get("", response_model=list[McpTokenRead])
async def list_mcp_tokens(user: CurrentUserDep, service: McpTokenServiceDep) -> list[McpTokenRead]:
    return [McpTokenRead.model_validate(t) for t in await service.list(user)]


@router.post("", response_model=McpTokenIssuedRead, status_code=status.HTTP_201_CREATED)
async def create_mcp_token(
    payload: McpTokenCreate, user: CurrentUserDep, service: McpTokenServiceDep
) -> McpTokenIssuedRead:
    issued = await service.issue(user, payload.name, McpAccess(payload.access))
    return McpTokenIssuedRead(
        **McpTokenRead.model_validate(issued.token).model_dump(), token=issued.secret
    )


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_mcp_token(
    token_id: UUID, user: CurrentUserDep, service: McpTokenServiceDep
) -> Response:
    try:
        await service.revoke(user, token_id)
    except UnknownMcpTokenError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
