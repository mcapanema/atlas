from uuid import uuid4

import pytest

from app.application.metric_rules.service import MetricRulesService, ScopeRef
from app.application.metric_rules.sharing import SharedRules, SharedTeamRules, match_teams
from app.domain.metric_rules.entities import RuleOverrides
from app.domain.organizations.entities import Organization
from app.domain.projects.entities import Project
from app.domain.teams.entities import Team
from tests.fakes import (
    InMemoryMetricRuleOverridesRepository,
    InMemoryOrganizationRepository,
    InMemoryProjectRepository,
    InMemoryTeamRepository,
)

ORG = Organization(name="Acme")
ALPHA = Team(organization_id=ORG.id, name="Alpha", external_id="lin-alpha")
BETA = Team(organization_id=ORG.id, name="Beta", external_id="lin-beta")


def _world() -> tuple[MetricRulesService, InMemoryMetricRuleOverridesRepository, Project]:
    elsewhere = Team(organization_id=uuid4(), name="Beta", external_id="lin-beta-elsewhere")
    launch = Project(team_id=BETA.id, name="Beta launch")
    repo = InMemoryMetricRuleOverridesRepository()
    service = MetricRulesService(
        repo,
        InMemoryOrganizationRepository([ORG]),
        InMemoryTeamRepository([ALPHA, BETA, elsewhere]),
        InMemoryProjectRepository([launch]),
    )
    return service, repo, launch


def test_matches_by_external_id_even_after_a_rename() -> None:
    entry = SharedTeamRules(name="Old Alpha", external_id="lin-alpha", overrides={})

    assert match_teams([entry], [ALPHA, BETA]) == ({ALPHA.id: entry}, ())


def test_falls_back_to_name_when_external_id_is_unknown() -> None:
    entry = SharedTeamRules(name="  beta ", external_id="other-workspace", overrides={})

    assert match_teams([entry], [ALPHA, BETA]) == ({BETA.id: entry}, ())


def test_unmatched_and_ambiguous_names_are_skipped() -> None:
    twin = Team(organization_id=ORG.id, name="Beta")
    entries = [SharedTeamRules("Gamma", None, {}), SharedTeamRules("Beta", None, {})]

    assert match_teams(entries, [ALPHA, BETA, twin]) == ({}, ("Gamma", "Beta"))


def test_two_entries_for_one_team_are_rejected() -> None:
    entries = [SharedTeamRules("Alpha", "lin-alpha", {}), SharedTeamRules("Alpha", None, {})]

    with pytest.raises(ValueError, match="Alpha"):
        match_teams(entries, [ALPHA, BETA])


async def test_export_carries_workspace_and_non_empty_team_layers() -> None:
    service, *_ = _world()
    await service.update_organization(ORG.id, {"aging_percentile": 80})
    await service.update_team(BETA.id, {"wait_state_names": ["In Review"]})
    await service.update_team(ALPHA.id, {"aging_percentile": 70})
    await service.update_team(ALPHA.id, {"aging_percentile": None})  # empty row: left out

    shared = await service.export_rules(ORG.id)

    assert shared == SharedRules(
        workspace={"aging_percentile": 80},
        teams=(SharedTeamRules("Beta", "lin-beta", {"wait_state_names": ["In Review"]}),),
    )


async def test_export_of_unknown_organization_is_none() -> None:
    service, *_ = _world()

    assert await service.export_rules(uuid4()) is None


async def test_import_replaces_workspace_and_matched_team_layers() -> None:
    service, repo, launch = _world()
    await service.update_organization(ORG.id, {"aging_percentile": 80, "healthy_min": 75})
    await service.update_team(BETA.id, {"restart_clock_after_move_back": True})

    result = await service.import_rules(
        ORG.id,
        SharedRules(
            workspace={"aging_percentile": 90},
            teams=(
                SharedTeamRules("Beta", "lin-beta", {"wait_state_names": ["QA"]}),
                SharedTeamRules("Gamma", None, {"aging_percentile": 70}),
            ),
        ),
    )

    assert result is not None
    assert result.change.view.overrides == {"aging_percentile": 90}  # healthy_min gone
    beta_row = await repo.get(ORG.id, team_id=BETA.id)
    assert beta_row is not None
    assert beta_row.overrides == {"wait_state_names": ["QA"]}
    assert result.imported_teams == ("Beta",)
    assert result.skipped_teams == ("Gamma",)
    assert ScopeRef(team_id=BETA.id) in result.change.scopes
    assert ScopeRef(project_id=launch.id) in result.change.scopes
    assert result.change.organization_id == ORG.id
    assert result.change.view.recompute.state == "running"


async def test_import_leaves_unlisted_teams_alone() -> None:
    service, repo, _ = _world()
    await service.update_team(ALPHA.id, {"aging_percentile": 70})

    await service.import_rules(ORG.id, SharedRules(workspace={}))

    alpha_row = await repo.get(ORG.id, team_id=ALPHA.id)
    assert alpha_row is not None
    assert alpha_row.overrides == {"aging_percentile": 70}


async def test_an_empty_team_layer_clears_that_team() -> None:
    service, repo, _ = _world()
    await service.update_team(BETA.id, {"aging_percentile": 70})

    await service.import_rules(ORG.id, SharedRules({}, (SharedTeamRules("Beta", None, {}),)))

    beta_row = await repo.get(ORG.id, team_id=BETA.id)
    assert beta_row is not None
    assert beta_row.overrides == {}


async def test_reimporting_an_export_changes_nothing() -> None:
    service, repo, _ = _world()
    await service.update_organization(ORG.id, {"aging_percentile": 80})
    await service.update_team(BETA.id, {"wait_state_names": ["QA"]})
    await service.finish_recompute(ORG.id, error=None)
    before = await repo.list_for_organization(ORG.id)
    shared = await service.export_rules(ORG.id)
    assert shared is not None

    result = await service.import_rules(ORG.id, shared)

    assert result is not None
    assert result.change.scopes == ()
    assert result.change.view.recompute.state == "idle"
    assert await repo.list_for_organization(ORG.id) == before  # updated_at untouched too


@pytest.mark.parametrize(
    ("shared", "error"),
    [
        (SharedRules({"no_such_rule": 1}), "no_such_rule"),
        (SharedRules({}, (SharedTeamRules("Beta", None, {"no_such_rule": 1}),)), "no_such_rule"),
        (
            SharedRules(
                {"aging_percentile": 90},
                (SharedTeamRules("Beta", None, {"aging_percentile": 150}),),
            ),
            "aging_percentile must be between",
        ),
    ],
)
async def test_import_rejects_unknown_rules_and_invalid_values_writing_nothing(
    shared: SharedRules, error: str
) -> None:
    service, repo, _ = _world()

    with pytest.raises(ValueError, match=error):
        await service.import_rules(ORG.id, shared)

    assert await repo.list_for_organization(ORG.id) == []


async def test_invalid_team_layer_error_names_the_team() -> None:
    service, *_ = _world()

    with pytest.raises(ValueError, match="Beta"):
        await service.import_rules(
            ORG.id, SharedRules({}, (SharedTeamRules("Beta", None, {"aging_percentile": 150}),))
        )


async def test_import_rejects_workspace_conflicting_with_an_unlisted_team() -> None:
    service, repo, _ = _world()
    await service.update_team(ALPHA.id, {"healthy_min": 60})

    with pytest.raises(ValueError, match="Alpha"):
        await service.import_rules(ORG.id, SharedRules({"healthy_min": 90, "warning_min": 80}))

    workspace_row = await repo.get(ORG.id)  # the setup's recompute status created it
    assert workspace_row is not None
    assert workspace_row.overrides == {}


async def test_import_skips_an_unlisted_team_whose_stored_rules_were_already_invalid() -> None:
    service, repo, _ = _world()
    # Legacy/corrupt layer: healthy_min below the default warning_min (40).
    await repo.save(
        RuleOverrides(organization_id=ORG.id, team_id=ALPHA.id, overrides={"healthy_min": 30})
    )

    result = await service.import_rules(ORG.id, SharedRules({"aging_percentile": 70}))

    assert result is not None
    assert result.change.view.overrides == {"aging_percentile": 70}
    assert ScopeRef(team_id=BETA.id) in result.change.scopes


async def test_import_into_unknown_organization_is_none() -> None:
    service, *_ = _world()

    assert await service.import_rules(uuid4(), SharedRules({})) is None
