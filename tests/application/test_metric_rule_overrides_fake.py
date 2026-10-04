from uuid import uuid4

from app.domain.metric_rules.entities import RecomputeStatus, RuleOverrides
from tests.fakes import InMemoryMetricRuleOverridesRepository


async def test_fake_mirrors_the_split_between_save_and_save_recompute() -> None:
    repo = InMemoryMetricRuleOverridesRepository()
    org = uuid4()
    await repo.save_recompute(org, RecomputeStatus(state="running"))
    row = await repo.get(org)
    assert row is not None
    assert row.overrides == {}

    await repo.save(RuleOverrides(organization_id=org, overrides={"healthy_min": 70}, id=row.id))
    after = await repo.get(org)
    assert after is not None
    assert after.overrides == {"healthy_min": 70}
    assert after.recompute.state == "running"

    await repo.save_recompute(org, RecomputeStatus(state="idle"))
    final = await repo.get(org)
    assert final is not None
    assert final.overrides == {"healthy_min": 70}
    assert final.recompute.state == "idle"
