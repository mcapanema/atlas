from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain._time import require_aware, utcnow

_LABELS = {"linear": "Linear", "github": "GitHub", "openrouter": "OpenRouter", "datadog": "Datadog"}
_MIN_HINT_LENGTH = 12
DATADOG_SITES = (
    "datadoghq.com",
    "us3.datadoghq.com",
    "us5.datadoghq.com",
    "datadoghq.eu",
    "ap1.datadoghq.com",
    "ap2.datadoghq.com",
    "ddog-gov.com",
)


class Integration(StrEnum):
    LINEAR = "linear"
    GITHUB = "github"
    OPENROUTER = "openrouter"
    DATADOG = "datadog"

    @property
    def label(self) -> str:
        return _LABELS[self.value]


@dataclass(frozen=True)
class Credential:
    """A connector secret plus the integration-specific setting that travels with it."""

    integration: Integration
    secret: str = field(repr=False)
    owner: str | None = None  # GitHub only
    model: str | None = None  # OpenRouter only
    application_key: str | None = field(default=None, repr=False)  # Datadog only
    site: str | None = None  # Datadog only
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.secret.strip():
            raise ValueError("Credential.secret must not be blank")
        self._require("owner", Integration.GITHUB, self.owner)
        self._require("model", Integration.OPENROUTER, self.model)
        self._require("application_key", Integration.DATADOG, self.application_key)
        self._require("site", Integration.DATADOG, self.site)
        if self.site is not None and self.site not in DATADOG_SITES:
            raise ValueError(f"Credential.site must be one of {', '.join(DATADOG_SITES)}")
        require_aware("Credential", updated_at=self.updated_at)

    def _require(self, name: str, owner: Integration, value: str | None) -> None:
        if self.integration == owner:
            if value is None or not value.strip():
                raise ValueError(f"Credential.{name} is required for {owner.label}")
        elif value is not None:
            raise ValueError(f"Credential.{name} only applies to {owner.label}")

    @property
    def hint(self) -> str:
        return _hint(self.secret)

    @property
    def application_key_hint(self) -> str | None:
        return _hint(self.application_key) if self.application_key is not None else None


def _hint(secret: str) -> str:
    """A short tail of the secret; bare when the secret is too short to show any of it."""
    return "…" + secret[-4:] if len(secret) >= _MIN_HINT_LENGTH else "…"
