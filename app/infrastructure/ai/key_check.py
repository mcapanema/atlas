"""Checks an OpenRouter API key before it is stored."""

import httpx

from app.domain.advisor.port import AdvisorError
from app.domain.credentials.port import CredentialCheckError

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"


def is_rejection(status: int | None) -> bool:
    """Whether a vendor answer is about the credentials rather than an outage.

    A GraphQL `errors` payload at 200 counts: the check queries are trivial,
    so an error there is about the credentials.
    """
    return status is not None and status < 500 and status != 429


async def check_openrouter_key(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Raise CredentialCheckError if OpenRouter rejects the key, AdvisorError on an outage."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as http:
            response = await http.get(
                OPENROUTER_KEY_URL, headers={"Authorization": f"Bearer {api_key}"}
            )
    except httpx.HTTPError as exc:
        raise AdvisorError(f"OpenRouter request failed: {exc}") from exc
    status = response.status_code
    if status == 200:
        return
    if is_rejection(status):
        raise CredentialCheckError(
            f"Could not verify the OpenRouter credentials: OpenRouter returned HTTP {status}"
        )
    raise AdvisorError(f"OpenRouter returned HTTP {status}")
