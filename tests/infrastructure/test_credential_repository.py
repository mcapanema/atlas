from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.credentials.entities import Credential, Integration
from app.infrastructure.repositories.credentials import SqlAlchemyCredentialRepository
from app.infrastructure.secrets import cipher_for


async def test_round_trip_and_replace(session: AsyncSession, tmp_path: Path) -> None:
    repo = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "k"))
    await repo.save(Credential(Integration.GITHUB, "ghp_old", owner="acme"))
    await repo.save(Credential(Integration.GITHUB, "ghp_new", owner="globex"))
    stored = await repo.get(Integration.GITHUB)
    assert stored is not None
    assert (stored.secret, stored.owner) == ("ghp_new", "globex")


async def test_secret_is_encrypted_at_rest(session: AsyncSession, tmp_path: Path) -> None:
    repo = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "k"))
    await repo.save(Credential(Integration.LINEAR, "lin_api_plain"))
    raw = (await session.execute(text("SELECT secret_ciphertext FROM credentials"))).scalar_one()
    assert "lin_api_plain" not in raw


async def test_unreadable_secret_reads_as_unset(
    session: AsyncSession, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "a"))
    await writer.save(Credential(Integration.LINEAR, "lin_api_plain"))
    other = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "b"))
    assert await other.get(Integration.LINEAR) is None
    assert "linear" in caplog.text.lower()
    assert "lin_api_plain" not in caplog.text


async def test_delete_removes_the_credential(session: AsyncSession, tmp_path: Path) -> None:
    repo = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "k"))
    await repo.save(Credential(Integration.LINEAR, "lin_api_plain"))
    await repo.delete(Integration.LINEAR)
    assert await repo.get(Integration.LINEAR) is None


async def test_delete_absent_is_a_no_op(session: AsyncSession, tmp_path: Path) -> None:
    repo = SqlAlchemyCredentialRepository(session, cipher_for(tmp_path / "k"))
    await repo.delete(Integration.OPENROUTER)
    assert await repo.get(Integration.OPENROUTER) is None
