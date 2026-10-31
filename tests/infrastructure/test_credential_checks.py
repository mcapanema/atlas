import httpx
import pytest

from app.domain.advisor.port import AdvisorError
from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialCheckError
from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors import graphql
from app.infrastructure.credential_checks import ProviderCredentialVerifier, is_rejection


async def _no_sleep(delay: float) -> None:
    return None


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, False),
        (200, True),
        (400, True),
        (401, True),
        (429, False),
        (500, False),
        (503, False),
    ],
)
def test_is_rejection(status: int | None, expected: bool) -> None:
    assert is_rejection(status) is expected


async def test_linear_key_accepted() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": {"organization": {"name": "Acme"}}})
    )
    await ProviderCredentialVerifier(transport).verify(Credential(Integration.LINEAR, "lin"))


async def test_linear_key_rejected() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(400, json={"errors": [{"message": "Authentication required"}]})
    )
    with pytest.raises(CredentialCheckError, match="Could not verify the Linear credentials"):
        await ProviderCredentialVerifier(transport).verify(Credential(Integration.LINEAR, "bad"))


async def test_linear_outage_is_not_a_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(graphql, "_sleep", _no_sleep)
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    with pytest.raises(DataSourceError) as caught:
        await ProviderCredentialVerifier(transport).verify(Credential(Integration.LINEAR, "lin"))
    assert not isinstance(caught.value, CredentialCheckError)


async def test_linear_network_failure_is_not_a_rejection() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.UnsupportedProtocol("boom")  # not retried by GraphQLClient

    with pytest.raises(DataSourceError):
        await ProviderCredentialVerifier(httpx.MockTransport(fail)).verify(
            Credential(Integration.LINEAR, "lin")
        )


async def test_openrouter_outage_is_not_a_rejection() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(500))
    with pytest.raises(AdvisorError):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )


async def test_openrouter_network_failure_is_an_advisor_error() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(AdvisorError):
        await ProviderCredentialVerifier(httpx.MockTransport(fail)).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )


async def test_github_unknown_owner_rejected() -> None:
    transport = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": {"repositoryOwner": None}})
    )
    with pytest.raises(CredentialCheckError, match="owner 'nope' was not found"):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.GITHUB, "ghp", owner="nope")
        )


async def test_github_bad_token_rejected() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401))
    with pytest.raises(CredentialCheckError, match="Could not verify the GitHub credentials"):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.GITHUB, "bad", owner="acme")
        )


async def test_github_token_and_owner_accepted() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer ghp"
        return httpx.Response(200, json={"data": {"repositoryOwner": {"login": "acme"}}})

    await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(
        Credential(Integration.GITHUB, "ghp", owner="acme")
    )


async def test_openrouter_key_rejected() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": {"code": 401}}))
    with pytest.raises(CredentialCheckError, match="OpenRouter returned HTTP 401"):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )


async def test_openrouter_key_accepted() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://openrouter.ai/api/v1/key"
        assert request.headers["Authorization"] == "Bearer sk"
        return httpx.Response(200, json={"data": {"label": "k"}})

    await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(
        Credential(Integration.OPENROUTER, "sk", model="m/x")
    )
