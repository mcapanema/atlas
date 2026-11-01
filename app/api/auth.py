from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import SESSION_COOKIE, AuthServiceDep, CurrentUserDep
from app.api.schemas import (
    AuthStatusRead,
    PasswordChangeRequest,
    SetupRequest,
    SignInRequest,
    UserRead,
)
from app.application.auth.service import (
    InvalidCredentialsError,
    SetupClosedError,
    SignedIn,
)
from app.domain.auth.entities import SESSION_LIFETIME

# Public: every route here works without a session (create_app() adds no guard).
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/",
        httponly=True,
        samesite="lax",
        # ponytail: no Secure flag — Atlas serves plain HTTP to loopback only
        # (ADR-0012). Turn it on with the allowed-hosts change that lifts it.
        secure=False,
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


def _signed_in(response: Response, signed_in: SignedIn) -> UserRead:
    _set_session_cookie(response, signed_in.token)
    return UserRead.model_validate(signed_in.user)


@router.get("/session", response_model=AuthStatusRead)
async def get_session_status(request: Request, auth: AuthServiceDep) -> AuthStatusRead:
    token = request.cookies.get(SESSION_COOKIE)
    user = await auth.user_for_token(token) if token else None
    return AuthStatusRead(
        setup_required=await auth.setup_required(),
        user=UserRead.model_validate(user) if user is not None else None,
    )


@router.post("/setup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def set_up(payload: SetupRequest, response: Response, auth: AuthServiceDep) -> UserRead:
    try:
        signed_in = await auth.create_first_admin(payload.email, payload.name, payload.password)
    except SetupClosedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _signed_in(response, signed_in)


@router.post("/sign-in", response_model=UserRead)
async def sign_in(payload: SignInRequest, response: Response, auth: AuthServiceDep) -> UserRead:
    try:
        signed_in = await auth.sign_in(payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return _signed_in(response, signed_in)


@router.post("/sign-out", status_code=status.HTTP_204_NO_CONTENT)
async def sign_out(request: Request, response: Response, auth: AuthServiceDep) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        await auth.sign_out(token)
    _clear_session_cookie(response)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest, request: Request, user: CurrentUserDep, auth: AuthServiceDep
) -> None:
    # CurrentUserDep already proved the cookie is present and valid.
    token = request.cookies[SESSION_COOKIE]
    try:
        await auth.change_password(user, payload.current_password, payload.new_password, token)
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Current password is incorrect",
        ) from exc
