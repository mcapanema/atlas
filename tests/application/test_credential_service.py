import pytest

from app.application.credentials.service import CredentialService
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
