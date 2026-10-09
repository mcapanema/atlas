import logging
from uuid import uuid4

import pytest

from app.application.metric_rules.service import MetricRulesService, ScopeRef
from app.domain.metric_rules.entities import DEFAULT_RULES, RuleOverrides
from app.domain.organizations.entities import Organization
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from tests.fakes import (
    InMemoryMetricRuleOverridesRepository,
    InMemoryOrganizationRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
)


def _world() -> tuple[
    MetricRulesService, Organization, Team, Team, Project, InMemoryMetricRuleOverridesRepository
]:
    org = Organization(name="Acme")
    alpha = Team(organization_id=org.id, name="Alpha")
    beta = Team(organization_id=org.id, name="Beta")
    elsewhere = Team(organization_id=uuid4(), name="Elsewhere")
    launch = Project(team_id=beta.id, name="Beta launch")
    repo = InMemoryMetricRuleOverridesRepository()
    service = MetricRulesService(
        repo,
        InMemoryOrganizationRepository([org]),
        InMemoryTeamRepository([alpha, beta, elsewhere]),
        InMemoryProjectRepository([launch]),
    )
    return service, org, alpha, beta, launch, repo


async def test_unknown_scopes_have_no_view() -> None:
    service, *_ = _world()

    assert await service.organization_view(uuid4()) is None
    assert await service.team_view(uuid4()) is None
    assert await service.update_team(uuid4(), {"aging_percentile": 80}) is None
    assert await service.update_organization(uuid4(), {"aging_percentile": 80}) is None


async def test_workspace_default_starts_as_built_in() -> None:
    service, org, *_ = _world()

    view = await service.organization_view(org.id)

    assert view is not None
    assert view.effective == DEFAULT_RULES
    assert view.overrides == {}
    assert view.recompute.state == "idle"


async def test_team_override_reports_layers_and_invalidates_the_teams_history() -> None:
    service, org, _, beta, launch, _ = _world()

    change = await service.update_team(beta.id, {"restart_clock_after_move_back": True})

    assert change is not None
    assert change.view.overrides == {"restart_clock_after_move_back": True}
    assert change.view.inherited == DEFAULT_RULES
    assert change.view.effective.restart_clock_after_move_back is True
    assert set(change.scopes) == {ScopeRef(team_id=beta.id), ScopeRef(project_id=launch.id)}
    assert change.organization_id == org.id
    assert change.view.recompute.state == "running"


async def test_null_resets_a_team_rule_to_inherit() -> None:
    service, _, alpha, *_ = _world()
    await service.update_team(alpha.id, {"aging_percentile": 70})

    change = await service.update_team(alpha.id, {"aging_percentile": None})

    assert change is not None
    assert change.view.overrides == {}
    assert change.view.effective.aging_percentile == 85


async def test_a_no_op_change_invalidates_nothing() -> None:
    service, _, alpha, *_ = _world()

    change = await service.update_team(alpha.id, {"aging_percentile": 85})  # = inherited

    assert change is not None
    assert change.scopes == ()
    assert change.view.recompute.state == "idle"


async def test_workspace_change_skips_teams_that_override_the_rule() -> None:
    service, org, alpha, beta, launch, _ = _world()
    await service.update_team(alpha.id, {"restart_clock_after_move_back": False})

    change = await service.update_organization(org.id, {"restart_clock_after_move_back": True})

    assert change is not None
    assert set(change.scopes) == {ScopeRef(team_id=beta.id), ScopeRef(project_id=launch.id)}
    assert change.view.effective.restart_clock_after_move_back is True


async def test_workspace_change_conflicting_with_a_team_override_is_rejected() -> None:
    service, org, alpha, *_ = _world()
    await service.update_team(alpha.id, {"healthy_min": 60})

    with pytest.raises(ValueError, match="Alpha"):
        await service.update_organization(org.id, {"warning_min": 65})


async def test_unknown_and_invalid_rules_are_rejected() -> None:
    service, _, alpha, *_ = _world()

    with pytest.raises(ValueError, match="Unknown metric rule"):
        await service.update_team(alpha.id, {"bogus": 1})
    with pytest.raises(ValueError, match="aging_percentile"):
        await service.update_team(alpha.id, {"aging_percentile": 5})


async def test_team_summaries_flag_teams_whose_rules_differ_from_the_workspace() -> None:
    service, org, alpha, beta, *_ = _world()
    await service.update_organization(org.id, {"aging_percentile": 70})
    await service.update_team(alpha.id, {"aging_percentile": 75})
    await service.update_team(beta.id, {"aging_percentile": 70})  # same as the workspace

    summaries = await service.team_summaries([alpha, beta])

    assert {team_id: s.custom for team_id, s in summaries.items()} == {
        alpha.id: True,
        beta.id: False,
    }
    assert summaries[alpha.id].effective.aging_percentile == 75
    assert summaries[beta.id].effective.aging_percentile == 70


async def test_a_sprint_length_change_rewrites_no_history_and_is_not_custom() -> None:
    service, org, alpha, beta, *_ = _world()

    team_change = await service.update_team(alpha.id, {"sprint_length_days": 7})
    workspace_change = await service.update_organization(org.id, {"sprint_length_days": 21})
    summaries = await service.team_summaries([alpha, beta])

    assert team_change is not None
    assert workspace_change is not None
    assert team_change.scopes == ()
    assert team_change.view.recompute.state == "idle"
    assert workspace_change.scopes == ()
    assert workspace_change.view.recompute.state == "idle"
    assert summaries[alpha.id].effective.sprint_length_days == 7  # its own override wins
    assert summaries[beta.id].effective.sprint_length_days == 21  # inherits the workspace
    assert not summaries[alpha.id].custom


async def test_a_metric_rule_override_next_to_a_sprint_length_still_queues_and_is_custom() -> None:
    service, _org, alpha, _beta, *_ = _world()

    change = await service.update_team(alpha.id, {"aging_percentile": 75, "sprint_length_days": 7})
    summaries = await service.team_summaries([alpha])

    assert change is not None
    assert change.scopes  # the metric rule still rewrites history
    assert summaries[alpha.id].custom
    assert summaries[alpha.id].effective.sprint_length_days == 7
    assert summaries[alpha.id].effective.aging_percentile == 75


async def test_recompute_status_lifecycle() -> None:
    service, org, *_ = _world()

    await service.start_recompute(org.id)
    assert await service.running_organizations() == [org.id]

    await service.finish_recompute(org.id, error="boom")
    failed = await service.organization_view(org.id)
    assert failed is not None
    assert (failed.recompute.state, failed.recompute.error) == ("failed", "boom")
    assert failed.recompute.finished_at is not None
    assert await service.running_organizations() == []

    await service.start_recompute(org.id)
    await service.finish_recompute(org.id, error=None)
    idle = await service.organization_view(org.id)
    assert idle is not None
    assert idle.recompute.state == "idle"


async def test_organization_scopes_cover_every_team_and_project() -> None:
    service, org, alpha, beta, launch, _ = _world()

    assert set(await service.organization_scopes(org.id)) == {
        ScopeRef(team_id=alpha.id),
        ScopeRef(team_id=beta.id),
        ScopeRef(project_id=launch.id),
    }


async def test_workspace_update_persists_running_status_with_the_new_overrides() -> None:
    service, org, *_, repo = _world()

    await service.update_organization(org.id, {"aging_percentile": 70})

    row = await repo.get(org.id)
    assert row is not None
    assert row.overrides == {"aging_percentile": 70}
    assert row.recompute.state == "running"


async def test_finish_recompute_keeps_overrides_written_after_the_status_was_started() -> None:
    service, org, *_ = _world()
    await service.start_recompute(org.id)
    await service.update_organization(org.id, {"aging_percentile": 70})

    await service.finish_recompute(org.id, error=None)

    view = await service.organization_view(org.id)
    assert view is not None
    assert view.overrides == {"aging_percentile": 70}
    assert view.recompute.state == "idle"


async def test_workspace_reset_of_a_key_invalidates_only_teams_inheriting_it() -> None:
    service, org, alpha, beta, launch, _ = _world()
    await service.update_organization(org.id, {"aging_percentile": 70})
    await service.update_team(alpha.id, {"aging_percentile": 75})

    change = await service.update_organization(org.id, {"aging_percentile": None})

    assert change is not None
    assert set(change.scopes) == {ScopeRef(team_id=beta.id), ScopeRef(project_id=launch.id)}
    assert change.view.effective.aging_percentile == 85


async def test_workspace_change_to_the_same_value_changes_nothing() -> None:
    service, org, *_, repo = _world()
    await service.update_organization(org.id, {"aging_percentile": 70})
    await service.finish_recompute(org.id, error=None)
    stored = await repo.get(org.id)

    change = await service.update_organization(org.id, {"aging_percentile": 70})

    assert change is not None
    assert change.scopes == ()
    assert change.view.recompute.state == "idle"
    assert await service.running_organizations() == []
    assert stored is not None
    after = await repo.get(org.id)
    assert after is not None
    assert after.overrides == stored.overrides
    assert after.recompute == stored.recompute
    assert after.updated_at == stored.updated_at


async def test_a_team_change_to_the_same_value_keeps_updated_at() -> None:
    service, _, alpha, *_, repo = _world()
    org_id = alpha.organization_id
    await service.update_team(alpha.id, {"aging_percentile": 70})
    stored = await repo.get(org_id, team_id=alpha.id)

    await service.update_team(alpha.id, {"aging_percentile": 70})

    after = await repo.get(org_id, team_id=alpha.id)
    assert stored is not None
    assert after is not None
    assert after.updated_at == stored.updated_at


async def test_workspace_change_skips_a_team_whose_stored_rules_were_already_invalid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, org, alpha, beta, launch, repo = _world()
    # Legacy/corrupt layer: healthy_min below the default warning_min (40).
    await repo.save(
        RuleOverrides(organization_id=org.id, team_id=alpha.id, overrides={"healthy_min": 30})
    )

    with caplog.at_level(logging.WARNING):
        change = await service.update_organization(org.id, {"aging_percentile": 70})

    assert change is not None
    assert set(change.scopes) == {
        ScopeRef(team_id=alpha.id),
        ScopeRef(team_id=beta.id),
        ScopeRef(project_id=launch.id),
    }
    assert any("Alpha" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)


async def test_workspace_change_still_rejects_a_team_it_would_newly_invalidate() -> None:
    service, org, alpha, beta, *_, repo = _world()
    await repo.save(
        RuleOverrides(organization_id=org.id, team_id=beta.id, overrides={"healthy_min": 30})
    )
    await service.update_team(alpha.id, {"healthy_min": 60})

    with pytest.raises(ValueError, match="Alpha"):
        await service.update_organization(org.id, {"warning_min": 65})
