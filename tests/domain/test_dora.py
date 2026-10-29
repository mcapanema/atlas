from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus, PullRequest
from app.domain.metrics.dora import (
    DoraBand,
    DoraMetrics,
    Incident,
    change_failure_band,
    compute_dora,
    deploy_frequency_band,
    lead_time_band,
    restore_band,
)
from app.domain.metrics.stats import percentile

NOW = datetime(2026, 10, 29, tzinfo=UTC)
API = Codebase(
    organization_id=uuid4(), name="API", external_id="1", production_environment="production"
)

S = DeploymentStatus.SUCCESS
F = DeploymentStatus.FAILURE


def _at(day: float) -> datetime:
    return NOW - timedelta(days=day)


def _deploy(
    day: float,
    status: DeploymentStatus = S,
    env: str = "production",
    sha: str = "abc",
) -> Deployment:
    started = _at(day)
    finished = None if status is DeploymentStatus.PENDING else started + timedelta(hours=1)
    return Deployment(
        codebase_id=API.id,
        external_id=str(uuid4()),
        environment=env,
        sha=sha,
        started_at=started,
        status=status,
        finished_at=finished,
    )


def _pr(opened_day: float, merged_day: float, first_commit_day: float | None = None) -> PullRequest:
    return PullRequest(
        codebase_id=API.id,
        external_id=str(uuid4()),
        number=1,
        title="change",
        opened_at=_at(opened_day),
        merged_at=_at(merged_day),
        first_commit_at=None if first_commit_day is None else _at(first_commit_day),
    )


def _dora(
    deployments: list[Deployment] | None = None,
    pull_requests: list[PullRequest] | None = None,
    incidents: list[Incident] | None = None,
    min_sample: int = 1,
) -> DoraMetrics:
    return compute_dora(
        [API],
        deployments or [],
        pull_requests or [],
        incidents or [],
        now=NOW,
        window_days=30,
        min_sample=min_sample,
    )


def test_no_codebases_gives_no_bands() -> None:
    result = compute_dora([], [], [], [Incident(_at(2), _at(1))], now=NOW)

    assert result.codebases == 0
    assert result.deployments == 0
    assert result.deploy_frequency_band is None
    assert result.lead_time_band is None
    assert result.change_failure_band is None
    assert result.restore_band is None
    assert result.change_failure_rate is None


def test_deploy_frequency_counts_successes_per_week() -> None:
    result = _dora([_deploy(day) for day in (1, 5, 9, 13, 17, 21)])

    assert result.codebases == 1
    assert result.deployments == 6
    assert result.deploys_per_week == pytest.approx(6 / (30 / 7))
    assert result.deploy_frequency_band == "high"

    empty = _dora()
    assert empty.deploys_per_week == 0.0
    assert empty.deploy_frequency_band == "low"


def test_only_finished_production_deployments_count() -> None:
    result = _dora(
        [
            _deploy(5, env="staging"),
            _deploy(4, env=" Production "),
            _deploy(3, DeploymentStatus.PENDING),
            _deploy(2, F),
        ]
    )

    assert result.deployments == 1
    assert result.finished_deployments == 2
    assert result.failed_deployments == 1
    assert result.change_failure_rate == 0.5


def test_lead_time_counts_each_change_once_when_shipped() -> None:
    p, d = _deploy(20), _deploy(10)
    a = _pr(opened_day=27, merged_day=25)
    b = _pr(opened_day=17, merged_day=15, first_commit_day=18)
    c = _pr(opened_day=6, merged_day=5)

    result = _dora([p, d], [a, b, c])

    assert p.finished_at is not None
    assert d.finished_at is not None
    lead_a = p.finished_at - a.opened_at
    lead_b = d.finished_at - _at(18)
    expected = percentile([lead_a.total_seconds(), lead_b.total_seconds()], 50)
    assert result.lead_time_changes == 2
    assert result.lead_time_median == timedelta(seconds=expected)


def test_lead_time_uses_opened_at_without_first_commit() -> None:
    deploy = _deploy(2)
    pr = _pr(opened_day=4, merged_day=3)

    result = _dora([deploy], [pr])

    assert deploy.finished_at is not None
    assert result.lead_time_changes == 1
    assert result.lead_time_median == deploy.finished_at - pr.opened_at


def test_incident_blames_latest_prior_success() -> None:
    incident = Incident(_at(3), _at(3) + timedelta(minutes=30))

    result = _dora([_deploy(10), _deploy(4)], incidents=[incident])

    assert result.failed_deployments == 1
    assert result.change_failure_rate == 0.5
    assert result.restores == 1
    assert result.restore_median == timedelta(minutes=30)
    assert result.restore_band == "elite"


def test_a_deployment_blamed_twice_fails_once() -> None:
    incidents = [
        Incident(_at(9), _at(9) + timedelta(hours=1)),
        Incident(_at(8), _at(8) + timedelta(hours=1)),
        Incident(_at(4), _at(4) + timedelta(hours=1)),
    ]

    result = _dora([_deploy(10), _deploy(6, F)], incidents=incidents)

    assert result.failed_deployments == 2
    assert result.finished_deployments == 2
    assert result.change_failure_rate == 1.0


def test_incident_before_any_deployment_blames_nothing() -> None:
    incident = Incident(_at(12), _at(12) + timedelta(hours=2))

    result = _dora([_deploy(10)], incidents=[incident])

    assert result.failed_deployments == 0
    assert result.restores == 1


def test_a_run_of_failures_restores_once() -> None:
    result = _dora([_deploy(9, F), _deploy(8, F), _deploy(7, F), _deploy(6)])

    one_hour = timedelta(hours=1)
    assert result.restores == 1
    assert result.restore_median == (_at(6) + one_hour) - (_at(9) + one_hour)


def test_open_incident_has_no_restore() -> None:
    result = _dora([_deploy(10)], incidents=[Incident(_at(2), None)])

    assert result.restores == 0
    assert result.restore_median is None


def test_bands_wait_for_the_minimum_sample() -> None:
    result = _dora([_deploy(10), _deploy(5)], [_pr(opened_day=8, merged_day=7)], min_sample=3)

    assert result.change_failure_band is None
    assert result.lead_time_band is None
    assert result.lead_time_median is not None
    assert result.deploy_frequency_band is not None


@pytest.mark.parametrize(
    ("per_week", "band"),
    [
        (7.0, "elite"),
        (6.99, "high"),
        (1.0, "high"),
        (0.99, "medium"),
        (7 / 30, "medium"),
        (0.23, "low"),
    ],
)
def test_deploy_frequency_band_thresholds(per_week: float, band: DoraBand) -> None:
    assert deploy_frequency_band(per_week) == band


@pytest.mark.parametrize(
    ("median", "band"),
    [
        (timedelta(days=1) - timedelta(seconds=1), "elite"),
        (timedelta(days=1), "high"),
        (timedelta(days=7) - timedelta(seconds=1), "high"),
        (timedelta(days=7), "medium"),
        (timedelta(days=30) - timedelta(seconds=1), "medium"),
        (timedelta(days=30), "low"),
    ],
)
def test_lead_time_band_thresholds(median: timedelta, band: DoraBand) -> None:
    assert lead_time_band(median) == band


@pytest.mark.parametrize(
    ("rate", "band"),
    [
        (0.05, "elite"),
        (0.051, "high"),
        (0.10, "high"),
        (0.101, "medium"),
        (0.15, "medium"),
        (0.151, "low"),
    ],
)
def test_change_failure_band_thresholds(rate: float, band: DoraBand) -> None:
    assert change_failure_band(rate) == band


@pytest.mark.parametrize(
    ("median", "band"),
    [
        (timedelta(hours=1) - timedelta(seconds=1), "elite"),
        (timedelta(hours=1), "high"),
        (timedelta(days=1) - timedelta(seconds=1), "high"),
        (timedelta(days=1), "medium"),
        (timedelta(days=7) - timedelta(seconds=1), "medium"),
        (timedelta(days=7), "low"),
    ],
)
def test_restore_band_thresholds(median: timedelta, band: DoraBand) -> None:
    assert restore_band(median) == band


def _run(
    codebase: Codebase, start_h: float, hours: float, status: DeploymentStatus = S
) -> Deployment:
    started = NOW - timedelta(hours=start_h)
    return Deployment(
        codebase_id=codebase.id,
        external_id=str(uuid4()),
        environment="production",
        sha="abc",
        started_at=started,
        status=status,
        finished_at=started + timedelta(hours=hours),
    )


def test_a_success_finishing_before_the_failure_does_not_restore_it() -> None:
    failure = _run(API, 10, 1, F)
    overlapping = _run(API, 9.9, 0.1)

    result = _dora([failure, overlapping])
    assert result.restores == 0
    assert result.restore_median is None

    later = _run(API, 5, 1)
    result = _dora([failure, overlapping, later])
    assert failure.finished_at is not None
    assert later.finished_at is not None
    assert result.restores == 1
    assert result.restore_median == later.finished_at - failure.finished_at


def test_codebases_do_not_mix_in_lead_time_failures_and_mapping() -> None:
    other = Codebase(
        organization_id=API.organization_id,
        name="Web",
        external_id="2",
        production_environment="production",
    )
    unmapped = Codebase(organization_id=API.organization_id, name="Gone", external_id="3")
    deploy_a = _deploy(10)
    deploy_b = _run(other, 2 * 24, 1)
    pr_b = PullRequest(
        codebase_id=other.id,
        external_id="pr-b",
        number=2,
        title="web change",
        opened_at=_at(15),
        merged_at=_at(14),
    )
    incident = Incident(_at(5), _at(5) + timedelta(hours=1))

    result = compute_dora(
        [API, other],
        [deploy_a, deploy_b, _run(unmapped, 1, 1)],
        [pr_b],
        [incident],
        now=NOW,
        window_days=30,
        min_sample=1,
    )

    # (a) B's pull request merged before A's deployment never ships with it.
    assert result.lead_time_changes == 1
    assert deploy_b.finished_at is not None
    assert result.lead_time_median == deploy_b.finished_at - pr_b.opened_at
    # (b) the incident blames the latest success across both codebases: A's (day 10)
    # is the only one finished before it; B's (day 2) comes later.
    assert result.failed_deployments == 1
    assert result.finished_deployments == 2
    # (c) the deployment of an unknown codebase is dropped.
    assert result.deployments == 2
