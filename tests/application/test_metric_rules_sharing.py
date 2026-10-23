from uuid import uuid4

import pytest

from app.application.metric_rules.service import MetricRulesService
from app.application.metric_rules.sharing import SharedRules, SharedTeamRules, match_teams
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
