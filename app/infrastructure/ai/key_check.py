"""Checks an OpenRouter API key and advisor model before they are stored."""

import httpx

from app.domain.advisor.port import AdvisorError
from app.domain.credentials.port import CredentialCheckError

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def is_rejection(status: int | None) -> bool:
    """Whether a vendor answer is about the credentials rather than an outage.

    A GraphQL `errors` payload at 200 counts: the check queries are trivial,
    so an error there is about the credentials.
    """
    return status is not None and status < 500 and status != 429


async def _get(
    url: str,
    transport: httpx.AsyncBaseTransport | None,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> httpx.Response:
    """A 200 response; a rejection raises CredentialCheckError, an outage AdvisorError."""
    try:
        async with httpx.AsyncClient(transport=transport, timeout=10.0) as http:
            response = await http.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        raise AdvisorError(f"OpenRouter request failed: {exc}") from exc
    status = response.status_code
    if status == 200:
        return response
    if is_rejection(status):
        raise CredentialCheckError(
            f"Could not verify the OpenRouter credentials: OpenRouter returned HTTP {status}"
        )
    raise AdvisorError(f"OpenRouter returned HTTP {status}")


async def check_openrouter_key(
    api_key: str, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Raise CredentialCheckError if OpenRouter rejects the key, AdvisorError on an outage."""
    await _get(OPENROUTER_KEY_URL, transport, headers={"Authorization": f"Bearer {api_key}"})


async def check_openrouter_model(
    model: str, transport: httpx.AsyncBaseTransport | None = None
) -> None:
    """Raise CredentialCheckError unless OpenRouter lists `model` with structured outputs.

    The model list is public, so the key is not sent: a key kind that may not
    read it must not make a good key look rejected.
    """
    response = await _get(
        OPENROUTER_MODELS_URL, transport, params={"supported_parameters": "structured_outputs"}
    )
    try:
        models = {entry["id"] for entry in response.json()["data"]}
    except (ValueError, KeyError, TypeError) as exc:
        # An off-shape answer is OpenRouter's fault (502), never a 422 blaming the user.
        raise AdvisorError("OpenRouter returned the model list in an unexpected shape") from exc
    if model not in models:
        raise CredentialCheckError(
            "Could not verify the OpenRouter credentials: OpenRouter has no model "
            f"'{model}' that supports structured outputs"
        )
