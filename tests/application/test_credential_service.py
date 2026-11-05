from datetime import UTC, datetime

import pytest

from app.application.credentials.service import CredentialService, NoStoredCredentialError
from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialCheckError
from tests.fakes import FakeCredentialVerifier, InMemoryCredentialRepository


async def test_save_checks_then_stores() -> None:
    repo, verifier = InMemoryCredentialRepository(), FakeCredentialVerifier()
    credential = Credential(Integration.LINEAR, "lin_api_x")
    await CredentialService(repo, verifier).save(credential)
    assert verifier.verified == [credential]
    assert await repo.get(Integration.LINEAR) == credential


async def test_rejected_credential_is_not_stored() -> None:
    repo = InMemoryCredentialRepository()
    verifier = FakeCredentialVerifier(
        error=CredentialCheckError("Could not verify the Linear credentials: HTTP 400")
    )
    with pytest.raises(CredentialCheckError):
        await CredentialService(repo, verifier).save(Credential(Integration.LINEAR, "bad"))
    assert await repo.get(Integration.LINEAR) is None


async def test_remove_is_idempotent() -> None:
    repo = InMemoryCredentialRepository()
    service = CredentialService(repo, FakeCredentialVerifier())
    await service.save(Credential(Integration.LINEAR, "lin"))
    await service.remove(Integration.LINEAR)
    await service.remove(Integration.LINEAR)
    assert await service.get(Integration.LINEAR) is None


async def test_update_keeps_the_stored_secret() -> None:
    repo, verifier = InMemoryCredentialRepository(), FakeCredentialVerifier()
    service = CredentialService(repo, verifier)
    await service.save(Credential(Integration.GITHUB, "ghp_stored_secret", owner="acme"))

    await service.update(Integration.GITHUB, None, owner="globex")

    stored = await repo.get(Integration.GITHUB)
    assert stored is not None
    assert (stored.secret, stored.owner) == ("ghp_stored_secret", "globex")
    assert verifier.verified[-1] == stored


async def test_update_reverifies_the_kept_key_against_the_new_owner() -> None:
    repo, verifier = InMemoryCredentialRepository(), FakeCredentialVerifier()
    service = CredentialService(repo, verifier)
    await service.save(Credential(Integration.GITHUB, "ghp_stored_secret", owner="acme"))
    verifier.error = CredentialCheckError(
        "Could not verify the GitHub credentials: owner 'globex' "
        "was not found or the token can't see it"
    )

    with pytest.raises(CredentialCheckError):
        await service.update(Integration.GITHUB, None, owner="globex")

    stored = await repo.get(Integration.GITHUB)
    assert stored is not None
    assert stored.owner == "acme"


async def test_update_without_secret_and_nothing_stored_is_rejected() -> None:
    service = CredentialService(InMemoryCredentialRepository(), FakeCredentialVerifier())
    with pytest.raises(
        NoStoredCredentialError, match=r"^No OpenRouter key is stored yet; enter one$"
    ):
        await service.update(Integration.OPENROUTER, None, model="openai/gpt-5")


async def test_update_with_a_new_secret_replaces_it() -> None:
    repo = InMemoryCredentialRepository()
    service = CredentialService(repo, FakeCredentialVerifier())
    await service.save(Credential(Integration.OPENROUTER, "sk-or-old-secret", model="m/a"))

    await service.update(Integration.OPENROUTER, "sk-or-new-secret", model="m/b")

    stored = await repo.get(Integration.OPENROUTER)
    assert stored is not None
    assert (stored.secret, stored.model) == ("sk-or-new-secret", "m/b")


_ENTERED = datetime(2026, 11, 1, 12, tzinfo=UTC)


async def _github_key_entered_at(
    when: datetime,
) -> tuple[CredentialService, InMemoryCredentialRepository]:
    repo = InMemoryCredentialRepository()
    service = CredentialService(repo, FakeCredentialVerifier())
    await service.save(
        Credential(Integration.GITHUB, "ghp_stored_secret", owner="acme", updated_at=when)
    )
    return service, repo


async def test_update_that_keeps_the_key_keeps_its_time() -> None:
    service, repo = await _github_key_entered_at(_ENTERED)

    await service.update(Integration.GITHUB, None, owner="globex")

    stored = await repo.get(Integration.GITHUB)
    assert stored is not None
    assert (stored.owner, stored.updated_at) == ("globex", _ENTERED)


async def test_update_with_a_new_key_moves_its_time() -> None:
    service, repo = await _github_key_entered_at(_ENTERED)

    await service.update(Integration.GITHUB, "ghp_new_secret_0000", owner="acme")

    stored = await repo.get(Integration.GITHUB)
    assert stored is not None
    assert stored.updated_at > _ENTERED
