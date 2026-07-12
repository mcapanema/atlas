"""Persistence ports for the persona-learning aggregates."""

from datetime import datetime
from typing import Protocol

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance


class AdviceFeedbackRepository(Protocol):
    """Port for storing and querying EM feedback on advice."""

    async def add(self, feedback: AdviceFeedback) -> None: ...

    async def list_for_persona(
        self, persona: Persona, *, since: datetime | None = None
    ) -> list[AdviceFeedback]:
        """Feedback for one persona, oldest first; `since` filters created_at > since."""
        ...


class PersonaGuidanceRepository(Protocol):
    """Port for the append-only learned-guidance versions."""

    async def add(self, guidance: PersonaGuidance) -> None: ...

    async def latest(self, persona: Persona) -> PersonaGuidance | None:
        """Highest version for the persona — the active guidance."""
        ...

    async def list_versions(self, persona: Persona) -> list[PersonaGuidance]:
        """All versions, newest (highest version) first."""
        ...

    async def get_version(self, persona: Persona, version: int) -> PersonaGuidance | None: ...
