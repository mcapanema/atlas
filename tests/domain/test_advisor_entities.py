from datetime import UTC, datetime

import pytest

from app.domain.advisor.entities import (
    DeliveryAdvice,
    MeetingPrep,
    MeetingType,
    Persona,
    Recommendation,
    TalkingPoint,
    meeting_persona,
)


def _recommendation(**overrides: object) -> Recommendation:
    values: dict[str, object] = {
        "title": "Lower WIP",
        "priority": "high",
        "problem": "WIP is 12 while weekly throughput is 3",
        "root_cause": "Work is started faster than it finishes",
        "action": "Introduce a WIP limit of 6 on In Progress",
        "evidence": ("wip=12", "completed=3"),
    }
    values.update(overrides)
    return Recommendation(**values)  # type: ignore[arg-type]


def test_recommendation_holds_fields() -> None:
    rec = _recommendation()
    assert rec.title == "Lower WIP"
    assert rec.evidence == ("wip=12", "completed=3")


def test_recommendation_rejects_blank_title() -> None:
    with pytest.raises(ValueError):
        _recommendation(title="   ")


def test_recommendation_rejects_unknown_priority() -> None:
    with pytest.raises(ValueError):
        _recommendation(priority="urgent")


def test_advice_rejects_naive_generated_at() -> None:
    with pytest.raises(ValueError):
        DeliveryAdvice(
            generated_at=datetime(2026, 7, 10),  # naive — no tzinfo
            summary="ok",
            recommendations=(),
        )


def test_advice_rejects_blank_summary() -> None:
    with pytest.raises(ValueError):
        DeliveryAdvice(
            generated_at=datetime(2026, 7, 10, tzinfo=UTC),
            summary="  ",
            recommendations=(),
        )


def test_persona_wire_values() -> None:
    assert [p.value for p in Persona] == [
        "agile_coach",
        "engineering_advisor",
        "project_advisor",
        "delivery_analyst",
        "daily_standup",
        "retrospective",
        "planning",
    ]


def test_meeting_persona_maps_each_meeting_type() -> None:
    assert meeting_persona(MeetingType.DAILY_STANDUP) is Persona.DAILY_STANDUP
    assert meeting_persona(MeetingType.RETROSPECTIVE) is Persona.RETROSPECTIVE
    assert meeting_persona(MeetingType.PLANNING) is Persona.PLANNING


def test_talking_point_rejects_blank_point() -> None:
    with pytest.raises(ValueError, match="point"):
        TalkingPoint(point="   ", detail="whatever")


def test_talking_point_defaults() -> None:
    tp = TalkingPoint(point="Unstick 'Fix login'", detail="6d against a 4d p85")
    assert tp.evidence == ()
    assert tp.needs_decision is False


def test_meeting_prep_rejects_blank_headline() -> None:
    with pytest.raises(ValueError, match="headline"):
        MeetingPrep(
            meeting=MeetingType.DAILY_STANDUP,
            generated_at=datetime(2026, 7, 12, tzinfo=UTC),
            headline="  ",
            talking_points=(),
        )


def test_meeting_prep_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        MeetingPrep(
            meeting=MeetingType.PLANNING,
            generated_at=datetime(2026, 7, 12),  # noqa: DTZ001 — the point of the test
            headline="Plan is at risk.",
            talking_points=(),
        )
