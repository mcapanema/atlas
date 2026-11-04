import httpx
import pytest

from app.domain.advisor.port import AdvisorError
from app.domain.credentials.entities import Credential, Integration
from app.domain.credentials.port import CredentialCheckError
from app.domain.sync.port import DataSourceError
from app.infrastructure.ai.key_check import is_rejection
from app.infrastructure.connectors import retry
from app.infrastructure.credential_checks import ProviderCredentialVerifier


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
    monkeypatch.setattr(retry, "_sleep", _no_sleep)
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


async def test_github_credential_with_owner_accepted() -> None:
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
        if request.url.path == "/api/v1/key":
            assert request.url == "https://openrouter.ai/api/v1/key"
            assert request.headers["Authorization"] == "Bearer sk"
            return httpx.Response(200, json={"data": {"label": "k"}})
        assert request.url.host == "openrouter.ai"
        assert request.url.path == "/api/v1/models"
        assert request.url.params["supported_parameters"] == "structured_outputs"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"data": [{"id": "m/x"}]})

    await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(
        Credential(Integration.OPENROUTER, "sk", model="m/x")
    )


def _key_ok(models: httpx.Response) -> httpx.MockTransport:
    """OpenRouter accepting the key, then answering the model list with `models`."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/key":
            return httpx.Response(200, json={"data": {}})
        return models

    return httpx.MockTransport(answer)


async def test_openrouter_unknown_model_rejected() -> None:
    transport = _key_ok(httpx.Response(200, json={"data": [{"id": "m/x"}]}))
    with pytest.raises(
        CredentialCheckError,
        match=(
            r"^Could not verify the OpenRouter credentials: OpenRouter has no model "
            r"'m/x:nitro' that supports structured outputs$"
        ),
    ):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x:nitro")
        )


async def test_openrouter_models_outage_is_an_advisor_error() -> None:
    transport = _key_ok(httpx.Response(503))
    with pytest.raises(AdvisorError, match="OpenRouter returned HTTP 503"):
        await ProviderCredentialVerifier(transport).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )


@pytest.mark.parametrize(
    "models",
    [
        httpx.Response(200, text="<html>captive portal</html>"),
        httpx.Response(200, json={"error": {"code": 200}}),
        httpx.Response(200, json={"data": ["m/x"]}),
    ],
)
async def test_openrouter_off_shape_model_list_is_an_advisor_error(
    models: httpx.Response,
) -> None:
    with pytest.raises(AdvisorError, match="unexpected shape"):
        await ProviderCredentialVerifier(_key_ok(models)).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )


async def test_rejected_key_skips_the_model_check() -> None:
    paths: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(401)

    with pytest.raises(CredentialCheckError, match="HTTP 401"):
        await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(
            Credential(Integration.OPENROUTER, "sk", model="m/x")
        )
    assert paths == ["/api/v1/key"]


_DATADOG = Credential(Integration.DATADOG, "dd-api", application_key="dd-app", site="datadoghq.eu")


async def test_datadog_check_validates_the_api_key_then_the_application_key() -> None:
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.datadoghq.eu"
        assert request.headers["DD-API-KEY"] == "dd-api"
        assert request.headers["DD-APPLICATION-KEY"] == "dd-app"
        seen.append(request.url.path)
        return httpx.Response(200, json={"valid": True, "data": []})

    await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(_DATADOG)

    assert seen == ["/api/v1/validate", "/api/v2/catalog/entity"]


async def test_datadog_wrong_site_is_a_rejection_naming_the_site() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(403, json={"errors": ["Forbidden"]}))
    with pytest.raises(CredentialCheckError) as caught:
        await ProviderCredentialVerifier(transport).verify(_DATADOG)
    assert "datadoghq.eu" in str(caught.value)
    assert "Could not verify the Datadog credentials" in str(caught.value)


async def test_datadog_bad_application_key_is_a_rejection() -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/validate":
            return httpx.Response(200, json={"valid": True})
        return httpx.Response(403, json={"errors": ["Forbidden"]})

    with pytest.raises(CredentialCheckError, match="Could not verify the Datadog credentials"):
        await ProviderCredentialVerifier(httpx.MockTransport(answer)).verify(_DATADOG)


async def test_datadog_outage_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "_sleep", _no_sleep)
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    with pytest.raises(DataSourceError) as caught:
        await ProviderCredentialVerifier(transport).verify(_DATADOG)
    assert not isinstance(caught.value, CredentialCheckError)
