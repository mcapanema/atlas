import type { UseQueryResult } from "@tanstack/react-query";
import { Alert, Button, Empty, Typography } from "antd";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { DeliveryHealth, MetricsFilters } from "../api/metrics";
import { useAllTeamsOverviews, type ScopeOverview } from "../api/overview";
import { useTeams, type Team } from "../api/teams";
import { HealthBadge } from "../components/HealthBadge";
import { MetricsFilterBar } from "../components/MetricsFilterBar";
import { Sparkline } from "../components/Sparkline";
import { TeamMetricsTable } from "../components/TeamMetricsTable";
import {
  applyFiltersToSearchParams,
  filtersFromSearchParams,
  isDefaultFilters,
  isRanged,
  periodText,
  windowLabel,
} from "../lib/metricsFilters";
import { buildTeamRows, type TeamRow } from "../lib/teamRows";

const BAND_RANK: Record<string, number> = { critical: 0, warning: 1 };

function weakestComponent(health: DeliveryHealth) {
  return [...health.components].sort((a, b) => a.score - b.score)[0];
}

function Headline({ rows }: { rows: TeamRow[] }) {
  const scored = rows.filter((row) => row.health?.band != null && row.health.score != null);
  if (scored.length === 0) return null;
  // Health answered but couldn't produce a score (not enough data yet):
  // name that count instead of silently shrinking the denominator. Pending
  // and failed teams are already covered by skeletons and the failure alert.
  const unscored = rows.filter(
    (row) => row.state === "ready" && (row.health?.score == null || row.health?.band == null),
  ).length;
  const note = unscored > 0 && (
    <span className="page-headline__note">
      {" · "}
      {unscored} not scored yet
    </span>
  );
  const atRisk = scored.filter((row) => row.health!.band !== "healthy");
  if (atRisk.length === 0) {
    return (
      <p className="page-headline">
        {scored.length === 1
          ? `${scored[0].team.name} is healthy`
          : `All ${scored.length} teams healthy`}
        {note}
      </p>
    );
  }
  const worst = [...atRisk].sort((a, b) => a.health!.score! - b.health!.score!)[0];
  const signal = worst.health ? weakestComponent(worst.health) : null;
  return (
    <p className="page-headline">
      <span className={`page-headline__count page-headline__count--${worst.health!.band}`}>
        {scored.length === 1
          ? `${worst.team.name} is at risk`
          : `${atRisk.length} of ${scored.length} teams at risk`}
      </span>
      {signal && (
        <>
          {" — "}
          {scored.length === 1 ? signal.reason : `${worst.team.name}: ${signal.reason}`}
        </>
      )}
      {note}
    </p>
  );
}

function AttentionSection({ rows }: { rows: TeamRow[] }) {
  const atRisk = rows
    .filter((row) => row.health?.band === "critical" || row.health?.band === "warning")
    .sort(
      (a, b) =>
        (BAND_RANK[a.health!.band!] ?? 9) - (BAND_RANK[b.health!.band!] ?? 9) ||
        (a.health!.score ?? 101) - (b.health!.score ?? 101),
    );
  if (atRisk.length === 0) return null;
  return (
    <section aria-label="Teams needing attention" className="attention">
      {atRisk.map((row) => {
        const health = row.health!;
        const reasons = [...health.components].sort((a, b) => a.score - b.score).slice(0, 2);
        return (
          <div key={row.team.id} className={`attention-card attention-card--${health.band}`}>
            <div className="attention-card__head">
              <Link to={`/teams?team=${row.team.id}`}>{row.team.name}</Link>
              <HealthBadge health={health} />
            </div>
            <ul className="attention-card__reasons">
              {reasons.map((component) => (
                <li key={component.name}>
                  <strong>{component.name}</strong> {component.reason}
                </li>
              ))}
            </ul>
            {row.pulse && (
              <div className="attention-card__pulse">
                <Sparkline points={row.pulse.points} />
                <span>lead time P85 {row.pulse.trend} this week</span>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}

function FailedTeamsAlert({
  teams,
  overviews,
}: {
  teams: Team[];
  overviews: UseQueryResult<ScopeOverview>[];
}) {
  const failed = teams.filter((_, index) => overviews[index]?.isError);
  if (failed.length === 0) return null;
  const retryFailed = () => {
    for (const query of overviews) {
      if (query.isError) void query.refetch();
    }
  };
  return (
    <Alert
      type="warning"
      style={{ marginBottom: 16 }}
      message={`Data failed to load for ${failed.map((team) => team.name).join(", ")}`}
      action={
        <Button size="small" onClick={retryFailed}>
          Retry
        </Button>
      }
    />
  );
}

function NoTeams() {
  return (
    <>
      <Typography.Title level={3}>Executive Dashboard</Typography.Title>
      <Empty description="No teams yet — connect Linear to start observing delivery.">
        <Link to="/connectors">
          <Button type="primary">Open Connectors</Button>
        </Link>
      </Empty>
    </>
  );
}

export function ExecutiveDashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const filters = useMemo(() => filtersFromSearchParams(searchParams), [searchParams]);
  const setFilters = (next: MetricsFilters) => {
    const params = new URLSearchParams(searchParams);
    applyFiltersToSearchParams(params, next);
    setSearchParams(params);
  };
  const teams = useTeams();
  const teamList = teams.data ?? [];
  // ponytail: one overview request (one server-side scope load) per team;
  // add a portfolio endpoint or a per-sync scope cache once N loads per
  // page open are slow (~50+ teams).
  const overviews = useAllTeamsOverviews(teamList, filters);

  if (teams.isError) {
    return (
      <Alert
        type="error"
        message="Couldn't load teams"
        action={
          <Button size="small" onClick={() => void teams.refetch()}>
            Retry
          </Button>
        }
      />
    );
  }
  if (teams.data && teams.data.length === 0) return <NoTeams />;

  const rows = buildTeamRows(teamList, overviews, isDefaultFilters(filters));
  const windowSource = rows.find((row) => row.metrics)?.metrics;
  return (
    <>
      <Typography.Title level={3}>Executive Dashboard</Typography.Title>
      <Headline rows={rows} />
      {windowSource && <p className="page-asof">{periodText(filters, windowSource)}</p>}
      <div style={{ marginBottom: 16 }}>
        <MetricsFilterBar filters={filters} onChange={setFilters} />
      </div>
      <FailedTeamsAlert teams={teamList} overviews={overviews} />
      <AttentionSection rows={rows} />
      <TeamMetricsTable
        rows={rows}
        periodLabel={windowLabel(filters, 30)}
        ranged={isRanged(filters)}
        loading={teams.isLoading}
      />
    </>
  );
}
