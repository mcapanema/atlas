import httpx
import pytest

from app.infrastructure.http_errors import describe_http_error


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.ReadTimeout(""), "ReadTimeout"),
        (
            httpx.ConnectError("[Errno -2] Name or service not known"),
            "ConnectError: [Errno -2] Name or service not known",
        ),
    ],
    ids=["empty-message", "with-message"],
)
def test_describe_http_error(exc: httpx.HTTPError, expected: str) -> None:
    assert describe_http_error(exc) == expected
