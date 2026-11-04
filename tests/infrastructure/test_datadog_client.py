import httpx
import pytest

from app.domain.sync.port import DataSourceError
from app.infrastructure.connectors import retry as retry_module
from app.infrastructure.connectors.datadog.client import DatadogAPIError, DatadogClient


@pytest.fixture
def recorded_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(retry_module, "_sleep", fake_sleep)
    return sleeps


def _client(handler: httpx.MockTransport, site: str = "datadoghq.com") -> DatadogClient:
    return DatadogClient("k", "a", site, transport=handler)


def test_datadog_api_error_is_a_data_source_error() -> None:
    assert issubclass(DatadogAPIError, DataSourceError)


async def test_get_sends_keys_to_the_site_api_host() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    client = _client(httpx.MockTransport(handler), "datadoghq.eu")

    assert await client.get("/api/v2/services", {"page": 2}) == {"data": []}
    request = seen[0]
    assert request.url.host == "api.datadoghq.eu"
    assert request.url.path == "/api/v2/services"
    assert request.url.params["page"] == "2"
    assert request.headers["DD-API-KEY"] == "k"
    assert request.headers["DD-APPLICATION-KEY"] == "a"


async def test_post_sends_json_body() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    client = _client(httpx.MockTransport(handler))

    assert await client.post("/api/v2/x", {"q": 1}) == {"ok": True}
    assert seen[0].method == "POST"
    assert seen[0].read() == b'{"q":1}'


async def test_retries_429_honoring_x_ratelimit_reset(recorded_sleeps: list[float]) -> None:
    responses = iter(
        [
            httpx.Response(429, headers={"X-RateLimit-Reset": "4"}),
            httpx.Response(200, json={"a": 1}),
        ]
    )
    client = _client(httpx.MockTransport(lambda _r: next(responses)))

    assert await client.get("/x") == {"a": 1}
    assert recorded_sleeps == [4.0]


async def test_non_2xx_raises_datadog_api_error_with_status_and_errors() -> None:
    client = _client(
        httpx.MockTransport(lambda _r: httpx.Response(403, json={"errors": ["Forbidden"]}))
    )

    with pytest.raises(DatadogAPIError) as exc_info:
        await client.get("/x")

    assert exc_info.value.status == 403
    assert "Forbidden" in str(exc_info.value)


async def test_error_message_keeps_at_most_three_errors() -> None:
    body = {"errors": ["e1", "e2", "e3", "e4"]}
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(400, json=body)))

    with pytest.raises(DatadogAPIError) as exc_info:
        await client.get("/x")

    assert "e3" in str(exc_info.value)
    assert "e4" not in str(exc_info.value)


async def test_non_json_body_raises() -> None:
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(200, text="nope")))

    with pytest.raises(DatadogAPIError, match="Datadog response is not JSON"):
        await client.get("/x")


async def test_non_json_error_body_keeps_the_status() -> None:
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(502, text="bad gateway")))

    with pytest.raises(DatadogAPIError) as exc_info:
        await client.get("/x")

    assert exc_info.value.status == 502


async def test_non_object_body_raises() -> None:
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(200, json=[1])))

    with pytest.raises(DatadogAPIError, match="not an object"):
        await client.get("/x")


async def test_error_without_an_errors_list_omits_the_suffix() -> None:
    client = _client(httpx.MockTransport(lambda _r: httpx.Response(400, json={"message": "x"})))

    with pytest.raises(DatadogAPIError) as exc_info:
        await client.get("/x")

    assert str(exc_info.value) == "Datadog API returned HTTP 400"
