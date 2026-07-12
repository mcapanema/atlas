import pytest

from app.domain.advisor.entities import AdviceFeedback, Persona, PersonaGuidance


def test_feedback_defaults_and_validity() -> None:
    feedback = AdviceFeedback(
        persona=Persona.AGILE_COACH, rating="up", advice_summary="Flow is healthy."
    )
    assert feedback.comment is None
    assert feedback.created_at.tzinfo is not None
    assert feedback.id != AdviceFeedback(
        persona=Persona.AGILE_COACH, rating="up", advice_summary="x"
    ).id


def test_feedback_rejects_unknown_rating() -> None:
    with pytest.raises(ValueError, match="rating"):
        AdviceFeedback(persona=Persona.AGILE_COACH, rating="meh", advice_summary="x")


def test_feedback_rejects_blank_summary() -> None:
    with pytest.raises(ValueError, match="advice_summary"):
        AdviceFeedback(persona=Persona.AGILE_COACH, rating="down", advice_summary="  ")


def test_guidance_requires_positive_version() -> None:
    with pytest.raises(ValueError, match="version"):
        PersonaGuidance(persona=Persona.AGILE_COACH, version=0, guidance="Be concise.")


def test_guidance_rejects_blank_text() -> None:
    with pytest.raises(ValueError, match="guidance"):
        PersonaGuidance(persona=Persona.AGILE_COACH, version=1, guidance=" ")


def test_guidance_defaults() -> None:
    guidance = PersonaGuidance(
        persona=Persona.DELIVERY_ANALYST, version=1, guidance="Be concise."
    )
    assert guidance.created_at.tzinfo is not None
