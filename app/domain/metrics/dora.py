"""DORA metrics for a team: deploy frequency, change lead time, change failure
rate and time to restore, over the trailing window (now - window_days, now].

Only production deployments count: a deployment whose environment equals its
codebase's production_environment after strip().casefold() on both. Only
SUCCESS and FAILURE deployments are finished; PENDING counts nowhere. Each
fact falls in the window by its own time: a deployment by finished_at, a
restore by its restore time.

- Deploy frequency: successful deployments finished in the window, per week.
- Change lead time: each successful deployment D finished in the window ships
  the pull requests of its codebase merged in (P.started_at, D.started_at],
  where P is the codebase's previous successful deployment by started_at
  (no P: the window_days before D.started_at). A change's lead time is
  D.finished_at - (first_commit_at or opened_at); reported as the median.
- Change failure rate: failed / finished deployments in the window. A
  deployment fails when its status is FAILURE, or when an incident blames it.
  An incident blames the latest successful deployment of the team's
  codebases that finished at or before the incident opened. A deployment
  fails once, however many incidents blame it.
- Time to restore: the median over incidents restored in the window
  (restored_at - opened_at) and over each run of failed deployments of a
  codebase, from the run's first failure to the codebase's next success
  (counted when that success finished in the window).

Durations are wall-clock, not the working calendar (ADR-0017): DORA bands are
stated in clock time, and outages do not pause on weekends. A band needs at
least `min_sample` values behind it; deploy frequency has a band whenever the
team has a codebase. With no codebase every band is None.

ponytail: lead time attributes pull requests to a deployment by merge time
between deployments, not by commit ancestry, so a codebase that deploys out
of merge order can misassign a change. Upgrade path: match merge_commit_sha
ancestry when the code host exposes it.
"""

import operator
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from app.domain.codebases.entities import Codebase, Deployment, DeploymentStatus, PullRequest
from app.domain.metrics.stats import percentile
from app.domain.metrics.windows import STATS_WINDOW_DAYS

DoraBand = Literal["elite", "high", "medium", "low"]

# DORA report thresholds: the first band whose limit the value meets wins;
# a value that meets none is "low".
DEPLOY_FREQUENCY_BANDS: tuple[tuple[float, DoraBand], ...] = (
    (7.0, "elite"),
    (1.0, "high"),
    (7 / 30, "medium"),
)
LEAD_TIME_BANDS: tuple[tuple[timedelta, DoraBand], ...] = (
    (timedelta(days=1), "elite"),
    (timedelta(days=7), "high"),
    (timedelta(days=30), "medium"),
)
CHANGE_FAILURE_BANDS: tuple[tuple[float, DoraBand], ...] = (
    (0.05, "elite"),
    (0.10, "high"),
    (0.15, "medium"),
)
RESTORE_BANDS: tuple[tuple[timedelta, DoraBand], ...] = (
    (timedelta(hours=1), "elite"),
    (timedelta(days=1), "high"),
    (timedelta(days=7), "medium"),
)

_FINISHED = (DeploymentStatus.SUCCESS, DeploymentStatus.FAILURE)


@dataclass(frozen=True)
class Incident:
    """A production incident: opened, and restored (None while open)."""

    opened_at: datetime
    restored_at: datetime | None


@dataclass(frozen=True)
class DoraMetrics:
    """The four DORA metrics over (window_start, window_end], each with its band."""

    window_start: datetime
    window_end: datetime
    # Codebases read (the team's mapped codebases).
    codebases: int
    min_sample: int
    # Successful production deployments finished in the window.
    deployments: int
    deploys_per_week: float
    deploy_frequency_band: DoraBand | None
    lead_time_median: timedelta | None
    lead_time_changes: int
    lead_time_band: DoraBand | None
    # None when finished_deployments == 0.
    change_failure_rate: float | None
    failed_deployments: int
    finished_deployments: int
    change_failure_band: DoraBand | None
    restore_median: timedelta | None
    restores: int
    restore_band: DoraBand | None


def deploy_frequency_band(per_week: float) -> DoraBand:
    """Elite at 7 or more a week, high at 1, medium at 7 in 30 days."""
    return next((band for limit, band in DEPLOY_FREQUENCY_BANDS if per_week >= limit), "low")


def lead_time_band(median: timedelta) -> DoraBand:
    """Elite under a day, high under a week, medium under 30 days."""
    return next((band for limit, band in LEAD_TIME_BANDS if median < limit), "low")


def change_failure_band(rate: float) -> DoraBand:
    """Elite at 5% or less, high at 10%, medium at 15%."""
    return next((band for limit, band in CHANGE_FAILURE_BANDS if rate <= limit), "low")


def restore_band(median: timedelta) -> DoraBand:
    """Elite under an hour, high under a day, medium under a week."""
    return next((band for limit, band in RESTORE_BANDS if median < limit), "low")


@dataclass(frozen=True)
class _Window:
    start: datetime
    end: datetime
    days: int

    def holds(self, moment: datetime | None) -> bool:
        return moment is not None and self.start < moment <= self.end


def _env(name: str) -> str:
    return name.strip().casefold()


@dataclass(frozen=True)
class _Run:
    """A finished production deployment, with its finish time narrowed."""

    id: UUID
    status: DeploymentStatus
    started_at: datetime
    finished_at: datetime


def _production(
    codebases: Sequence[Codebase], deployments: Sequence[Deployment]
) -> dict[UUID, list[_Run]]:
    """Finished production deployments per codebase, by started_at."""
    production = {codebase.id: _env(codebase.production_environment) for codebase in codebases}
    by_codebase: dict[UUID, list[_Run]] = defaultdict(list)
    for d in deployments:
        if (
            d.status in _FINISHED
            and d.finished_at is not None
            and production.get(d.codebase_id) == _env(d.environment)
        ):
            by_codebase[d.codebase_id].append(_Run(d.id, d.status, d.started_at, d.finished_at))
    for runs in by_codebase.values():
        runs.sort(key=operator.attrgetter("started_at"))
    return by_codebase


def _deploy_frequency(deployments: Sequence[_Run], window: _Window) -> int:
    return sum(
        d.status is DeploymentStatus.SUCCESS and window.holds(d.finished_at) for d in deployments
    )


def _shipped(
    deploy: _Run, since: datetime, pull_requests: Sequence[PullRequest]
) -> list[timedelta]:
    """Lead times of the pull requests merged in (since, deploy.started_at]."""
    return [
        deploy.finished_at - (pr.first_commit_at or pr.opened_at)
        for pr in pull_requests
        if pr.merged_at is not None and since < pr.merged_at <= deploy.started_at
    ]


def _lead_times(
    by_codebase: dict[UUID, list[_Run]],
    pull_requests: Sequence[PullRequest],
    window: _Window,
) -> list[timedelta]:
    merged: dict[UUID, list[PullRequest]] = defaultdict(list)
    for pr in pull_requests:
        merged[pr.codebase_id].append(pr)
    lead_times: list[timedelta] = []
    for codebase_id, deployments in by_codebase.items():
        previous: _Run | None = None
        for deploy in (d for d in deployments if d.status is DeploymentStatus.SUCCESS):
            since = (
                previous.started_at if previous else deploy.started_at - timedelta(days=window.days)
            )
            if window.holds(deploy.finished_at):
                lead_times.extend(_shipped(deploy, since, merged[codebase_id]))
            previous = deploy
    return lead_times


def _blamed(successes: Sequence[_Run], incident: Incident) -> _Run | None:
    """The latest success that finished at or before the incident opened."""
    prior = [d for d in successes if d.finished_at <= incident.opened_at]
    return max(prior, key=operator.attrgetter("finished_at"), default=None)


def _failures(
    deployments: Sequence[_Run], incidents: Sequence[Incident], window: _Window
) -> tuple[int, int]:
    """(failed, finished) deployments in the window; each fails at most once."""
    finished = {d.id for d in deployments if window.holds(d.finished_at)}
    failed: set[UUID] = {
        d.id for d in deployments if d.id in finished and d.status is DeploymentStatus.FAILURE
    }
    successes = [d for d in deployments if d.status is DeploymentStatus.SUCCESS]
    for incident in incidents:
        blamed = _blamed(successes, incident)
        if blamed is not None and blamed.id in finished:
            failed.add(blamed.id)
    return len(failed), len(finished)


def _failure_restores(deployments: Sequence[_Run], window: _Window) -> list[timedelta]:
    """From each run's first failure to the codebase's next success."""
    restores: list[timedelta] = []
    first_failure: _Run | None = None
    for deploy in deployments:
        if deploy.status is DeploymentStatus.FAILURE:
            first_failure = first_failure or deploy
            continue
        if first_failure is not None and window.holds(deploy.finished_at):
            restores.append(deploy.finished_at - first_failure.finished_at)
        first_failure = None
    return restores


def _restores(
    by_codebase: dict[UUID, list[_Run]], incidents: Sequence[Incident], window: _Window
) -> list[timedelta]:
    restores = [
        i.restored_at - i.opened_at
        for i in incidents
        if i.restored_at is not None and window.holds(i.restored_at)
    ]
    for deployments in by_codebase.values():
        restores.extend(_failure_restores(deployments, window))
    return restores


def _median(durations: Sequence[timedelta]) -> timedelta | None:
    if not durations:
        return None
    return timedelta(seconds=percentile([d.total_seconds() for d in durations], 50))


def _banded[T](value: T | None, enough: bool, band: Callable[[T], DoraBand]) -> DoraBand | None:
    """The value's band when enough evidence stands behind it."""
    return band(value) if value is not None and enough else None


def compute_dora(
    codebases: Sequence[Codebase],
    deployments: Sequence[Deployment],
    pull_requests: Sequence[PullRequest],
    incidents: Sequence[Incident],
    *,
    now: datetime,
    window_days: int = STATS_WINDOW_DAYS,
    min_sample: int = 5,
) -> DoraMetrics:
    """DORA metrics for one team's codebases over (now - window_days, now].

    `incidents` are the team's incidents (the caller leaves out canceled
    ones). Lead time, change failure rate and restore get a band only when
    their sample is at least `min_sample`; with no codebase no band at all.
    """
    window = _Window(now - timedelta(days=window_days), now, window_days)
    mapped = bool(codebases)
    by_codebase = _production(codebases, deployments)
    every = [d for runs in by_codebase.values() for d in runs]
    count = _deploy_frequency(every, window)
    per_week = count / (window_days / 7)
    lead_times = _lead_times(by_codebase, pull_requests, window)
    failed, finished = _failures(every, incidents, window)
    rate = failed / finished if finished else None
    restores = _restores(by_codebase, incidents, window)
    return DoraMetrics(
        window_start=window.start,
        window_end=now,
        codebases=len(codebases),
        min_sample=min_sample,
        deployments=count,
        deploys_per_week=per_week,
        deploy_frequency_band=deploy_frequency_band(per_week) if mapped else None,
        lead_time_median=_median(lead_times),
        lead_time_changes=len(lead_times),
        lead_time_band=_banded(
            _median(lead_times), mapped and len(lead_times) >= min_sample, lead_time_band
        ),
        change_failure_rate=rate,
        failed_deployments=failed,
        finished_deployments=finished,
        change_failure_band=_banded(rate, mapped and finished >= min_sample, change_failure_band),
        restore_median=_median(restores),
        restores=len(restores),
        restore_band=_banded(
            _median(restores), mapped and len(restores) >= min_sample, restore_band
        ),
    )
