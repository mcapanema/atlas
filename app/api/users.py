from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import AdminDep, UserServiceDep, require_admin
from app.api.schemas import PasswordResetRequest, UserCreate, UserRead
from app.application.auth.service import EmailTakenError, SelfRemovalError, UnknownUserError

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserRead])
async def list_users(service: UserServiceDep) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in await service.list_users()]


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, service: UserServiceDep) -> UserRead:
    try:
        user = await service.create_user(
            payload.email, payload.name, payload.password, payload.is_admin
        )
    except EmailTakenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserRead.model_validate(user)


@router.put("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    user_id: UUID, payload: PasswordResetRequest, service: UserServiceDep
) -> None:
    try:
        await service.reset_password(user_id, payload.new_password)
    except UnknownUserError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, actor: AdminDep, service: UserServiceDep) -> None:
    try:
        await service.delete_user(actor, user_id)
    except UnknownUserError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SelfRemovalError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
