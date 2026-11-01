"""First-run setup, sign-in, sign-out and password change (ADR-0027)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.helpers import sign_in
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

NEW_PASSWORD = "a-brand-new-passphrase"


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"atlas_session={token}"}


async def test_session_reports_setup_required_on_an_empty_install(
    anon_client: AsyncClient,
) -> None:
    response = await anon_client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() == {"setup_required": True, "user": None}


async def test_session_reports_the_signed_in_user(client: AsyncClient) -> None:
    body = (await client.get("/api/auth/session")).json()

    assert body["setup_required"] is False
    assert body["user"]["email"] == ADMIN_EMAIL


async def test_setup_signs_in_the_first_admin(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/auth/setup",
        json={"email": "ana@acme.com", "name": "Ana", "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["is_admin"] is True
    assert "password_hash" not in body
    cookie = response.headers["set-cookie"]
    assert "atlas_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=1209600" in cookie
    assert (await anon_client.get("/api/teams")).status_code == 200


async def test_setup_is_closed_once_a_user_exists(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/setup",
        json={"email": "eve@acme.com", "name": "Eve", "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 409


async def test_sign_in_with_mixed_case_email(client: AsyncClient, anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/auth/sign-in", json={"email": " Admin@Atlas.TEST ", "password": ADMIN_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["email"] == ADMIN_EMAIL
    assert (await anon_client.get("/api/teams")).status_code == 200


async def test_wrong_password_is_401_with_one_message(
    client: AsyncClient, anon_client: AsyncClient
) -> None:
    wrong = await anon_client.post(
        "/api/auth/sign-in", json={"email": ADMIN_EMAIL, "password": "not-the-password"}
    )
    unknown = await anon_client.post(
        "/api/auth/sign-in", json={"email": "nobody@atlas.test", "password": ADMIN_PASSWORD}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Wrong email or password"}


async def test_short_password_is_422(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/auth/setup", json={"email": "ana@acme.com", "name": "Ana", "password": "short"}
    )

    assert response.status_code == 422


async def test_a_malformed_email_is_422(anon_client: AsyncClient) -> None:
    response = await anon_client.post(
        "/api/auth/setup",
        json={"email": "not-an-email", "name": "Ana", "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 422


async def test_sign_out_clears_the_cookie_and_the_session(
    client: AsyncClient, anon_client: AsyncClient
) -> None:
    token = client.cookies["atlas_session"]

    response = await client.post("/api/auth/sign-out")

    assert response.status_code == 204
    cleared = response.headers["set-cookie"]
    assert cleared.startswith('atlas_session="";')
    assert "Max-Age=0" in cleared
    assert "Path=/" in cleared
    assert (await anon_client.get("/api/teams", headers=_cookie(token))).status_code == 401


async def test_sign_out_without_a_session_is_204(anon_client: AsyncClient) -> None:
    assert (await anon_client.post("/api/auth/sign-out")).status_code == 204


async def test_change_password(client: AsyncClient, anon_client: AsyncClient) -> None:
    other = await anon_client.post(
        "/api/auth/sign-in", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    other_token = other.cookies["atlas_session"]
    anon_client.cookies.clear()

    wrong = await client.put(
        "/api/auth/password",
        json={"current_password": "not-the-password", "new_password": NEW_PASSWORD},
    )
    changed = await client.put(
        "/api/auth/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert wrong.status_code == 422
    assert wrong.json() == {"detail": "Current password is incorrect"}
    assert changed.status_code == 204
    assert (await anon_client.get("/api/teams", headers=_cookie(other_token))).status_code == 401
    assert (await client.get("/api/teams")).status_code == 200
    signed_in = await anon_client.post(
        "/api/auth/sign-in", json={"email": ADMIN_EMAIL, "password": NEW_PASSWORD}
    )
    assert signed_in.status_code == 200


async def test_change_password_needs_a_session(anon_client: AsyncClient) -> None:
    response = await anon_client.put(
        "/api/auth/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert response.status_code == 401


async def test_a_member_session_works_on_the_api(
    anon_client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _, token = await sign_in(sessionmaker)

    assert (await anon_client.get("/api/teams", headers=_cookie(token))).status_code == 200
