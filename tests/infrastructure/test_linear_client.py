import json
from collections.abc import Callable

import httpx
import pytest

from app.infrastructure.connectors.linear.client import LinearAPIError, LinearGraphQLClient


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> LinearGraphQLClient:
    return LinearGraphQLClient("lin_api_test", transport=httpx.MockTransport(handler))


async def test_execute_sends_raw_api_key_and_returns_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "lin_api_test"  # no "Bearer" prefix
        body = json.loads(request.content)
        assert body["query"] == "{ viewer { id } }"
        assert body["variables"] == {}
        return httpx.Response(200, json={"data": {"viewer": {"id": "u1"}}})

    data = await _client(handler).execute("{ viewer { id } }")

    assert data == {"viewer": {"id": "u1"}}


async def test_execute_raises_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(LinearAPIError, match="401"):
        await _client(handler).execute("{ viewer { id } }")


async def test_execute_raises_on_graphql_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad query"}], "data": None})

    with pytest.raises(LinearAPIError, match="bad query"):
        await _client(handler).execute("{ nope }")
