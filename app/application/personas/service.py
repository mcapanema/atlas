from datetime import datetime

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance
from app.domain.advisor.repository import AdviceFeedbackRepository, PersonaGuidanceRepository


class PersonaService:
    """Use cases for persona learning: record feedback, manage guidance versions.

    Guidance is append-only — the highest version is active, and restoring an
    old version re-adds its text as a new version. The LLM reflect call itself
    happens in Presentation (same pattern as AdvisorService: never hold the DB
    transaction across a slow LLM request).
    """

    def __init__(
        self, feedback: AdviceFeedbackRepository, guidance: PersonaGuidanceRepository
    ) -> None:
        self._feedback = feedback
        self._guidance = guidance

    async def record_feedback(
        self,
        *,
        persona: Persona,
        rating: str,
        comment: str | None,
        advice_summary: str,
    ) -> AdviceFeedback:
        feedback = AdviceFeedback(
            persona=persona, rating=rating, comment=comment, advice_summary=advice_summary
        )
        await self._feedback.add(feedback)
        return feedback

    async def active_guidance(self, persona: Persona) -> PersonaGuidance | None:
        return await self._guidance.latest(persona)

    async def list_guidance(self, persona: Persona) -> list[PersonaGuidance]:
        return await self._guidance.list_versions(persona)

    async def pending_feedback(self, persona: Persona) -> list[AdviceFeedback]:
        """Feedback not yet distilled: everything after the latest guidance."""
        latest = await self._guidance.latest(persona)
        since = latest.created_at if latest else None
        return await self._feedback.list_for_persona(persona, since=since)

    async def add_guidance(
        self,
        persona: Persona,
        guidance_text: str,
        *,
        created_at: datetime | None = None,
    ) -> PersonaGuidance:
        latest = await self._guidance.latest(persona)
        version = (latest.version if latest else 0) + 1
        guidance = (
            PersonaGuidance(persona=persona, version=version, guidance=guidance_text)
            if created_at is None
            else PersonaGuidance(
                persona=persona, version=version, guidance=guidance_text, created_at=created_at
            )
        )
        await self._guidance.add(guidance)
        return guidance

    async def restore_guidance(
        self, persona: Persona, version: int
    ) -> PersonaGuidance | None:
        source = await self._guidance.get_version(persona, version)
        if source is None:
            return None
        return await self.add_guidance(persona, source.guidance)
