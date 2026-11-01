from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.domain._time import require_aware, utcnow

_LABELS = {"linear": "Linear", "github": "GitHub", "openrouter": "OpenRouter"}
_MIN_HINT_LENGTH = 12


class Integration(StrEnum):
    LINEAR = "linear"
    GITHUB = "github"
    OPENROUTER = "openrouter"

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
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.secret.strip():
            raise ValueError("Credential.secret must not be blank")
        self._require("owner", Integration.GITHUB, self.owner)
        self._require("model", Integration.OPENROUTER, self.model)
        require_aware("Credential", updated_at=self.updated_at)

    def _require(self, name: str, owner: Integration, value: str | None) -> None:
        if self.integration == owner:
            if value is None or not value.strip():
                raise ValueError(f"Credential.{name} is required for {owner.label}")
        elif value is not None:
            raise ValueError(f"Credential.{name} only applies to {owner.label}")

    @property
    def hint(self) -> str:
        """A short tail of the secret; bare when the secret is too short to show any of it."""
        return "…" + self.secret[-4:] if len(self.secret) >= _MIN_HINT_LENGTH else "…"
