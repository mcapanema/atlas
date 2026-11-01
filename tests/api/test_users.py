"""Administrators manage users; members cannot (ADR-0027)."""

from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.api.helpers import sign_in
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

NEW_PASSWORD = "a-brand-new-passphrase"


def _cookie(token: str) -> dict[str, str]:
    return {"Cookie": f"atlas_session={token}"}


async def test_member_gets_403_on_users(
    anon_client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    _, token = await sign_in(sessionmaker, is_admin=False)

    response = await anon_client.get("/api/users", headers=_cookie(token))

    assert response.status_code == 403
    assert response.json() == {"detail": "Only administrators manage users"}


async def test_anonymous_gets_401_on_users(anon_client: AsyncClient) -> None:
    assert (await anon_client.get("/api/users")).status_code == 401


async def test_admin_lists_creates_and_removes_users(client: AsyncClient) -> None:
    created = await client.post(
        "/api/users",
        json={"email": "Bob@Acme.com", "name": "Bob", "password": ADMIN_PASSWORD},
    )
    assert created.status_code == 201
    bob = created.json()
    assert (bob["email"], bob["name"], bob["is_admin"]) == ("bob@acme.com", "Bob", False)
    assert "password_hash" not in bob

    listed = await client.get("/api/users")
    assert listed.status_code == 200
    assert sorted(u["email"] for u in listed.json()) == [ADMIN_EMAIL, "bob@acme.com"]

    assert (await client.delete(f"/api/users/{bob['id']}")).status_code == 204
    assert [u["email"] for u in (await client.get("/api/users")).json()] == [ADMIN_EMAIL]


async def test_admin_creates_another_admin(client: AsyncClient) -> None:
    created = await client.post(
        "/api/users",
        json={"email": "cy@acme.com", "name": "Cy", "password": ADMIN_PASSWORD, "is_admin": True},
    )

    assert created.status_code == 201
    assert created.json()["is_admin"] is True


async def test_duplicate_email_is_409(
    client: AsyncClient, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(sessionmaker)  # member@atlas.test

    response = await client.post(
        "/api/users",
        json={"email": "MEMBER@atlas.test", "name": "Dup", "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 409


async def test_removed_user_loses_access(
    client: AsyncClient,
    anon_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    member, token = await sign_in(sessionmaker)

    assert (await client.delete(f"/api/users/{member.id}")).status_code == 204
    assert (await anon_client.get("/api/teams", headers=_cookie(token))).status_code == 401


async def test_admin_reset_lifts_the_sign_in_lock(
    client: AsyncClient,
    anon_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    member, _ = await sign_in(sessionmaker)
    for _ in range(5):
        await anon_client.post(
            "/api/auth/sign-in", json={"email": member.email, "password": "not-the-password"}
        )

    await client.put(f"/api/users/{member.id}/password", json={"new_password": NEW_PASSWORD})
    signed_in = await anon_client.post(
        "/api/auth/sign-in", json={"email": member.email, "password": NEW_PASSWORD}
    )

    assert signed_in.status_code == 200


async def test_reset_password_revokes_sessions(
    client: AsyncClient,
    anon_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    member, token = await sign_in(sessionmaker)

    response = await client.put(
        f"/api/users/{member.id}/password", json={"new_password": NEW_PASSWORD}
    )

    assert response.status_code == 204
    assert (await anon_client.get("/api/teams", headers=_cookie(token))).status_code == 401
    signed_in = await anon_client.post(
        "/api/auth/sign-in", json={"email": member.email, "password": NEW_PASSWORD}
    )
    assert signed_in.status_code == 200


async def test_admin_cannot_remove_themselves(client: AsyncClient) -> None:
    users = (await client.get("/api/users")).json()
    (me,) = [u for u in users if u["email"] == ADMIN_EMAIL]

    response = await client.delete(f"/api/users/{me['id']}")

    assert response.status_code == 409


async def test_unknown_user_is_404(client: AsyncClient) -> None:
    missing = uuid4()

    deleted = await client.delete(f"/api/users/{missing}")
    reset = await client.put(f"/api/users/{missing}/password", json={"new_password": NEW_PASSWORD})

    assert deleted.status_code == reset.status_code == 404
