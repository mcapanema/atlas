from datetime import UTC, datetime

import pytest

from app.domain.advisor.entities import DeliveryAdvice, Recommendation


def _recommendation(**overrides: object) -> Recommendation:
    values: dict[str, object] = {
        "title": "Lower WIP",
        "priority": "high",
        "problem": "WIP is 12 while weekly throughput is 3",
        "root_cause": "Work is started faster than it finishes",
        "action": "Introduce a WIP limit of 6 on In Progress",
        "evidence": ["wip=12", "completed=3"],
    }
    values.update(overrides)
    return Recommendation(**values)  # type: ignore[arg-type]


def test_recommendation_holds_fields() -> None:
    rec = _recommendation()
    assert rec.title == "Lower WIP"
    assert rec.evidence == ["wip=12", "completed=3"]


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
            recommendations=[],
        )


def test_advice_rejects_blank_summary() -> None:
    with pytest.raises(ValueError):
        DeliveryAdvice(
            generated_at=datetime(2026, 7, 10, tzinfo=UTC),
            summary="  ",
            recommendations=[],
        )
