import type { UseQueryResult } from "@tanstack/react-query";
import { Alert, Button, Empty, Flex, Typography } from "antd";
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { MetricsFilters } from "../api/metrics";
import { useAllTeamsOverviews, type ScopeOverview } from "../api/overview";
import { useTeams, type Team } from "../api/teams";
import { MetricsFilterBar } from "../components/MetricsFilterBar";
import { TeamMetricsTable } from "../components/TeamMetricsTable";
import { isAtRisk, weakestComponents } from "../lib/health";
import {
  applyFiltersToSearchParams,
  filtersFromSearchParams,
  isDefaultFilters,
  isRanged,
  periodText,
  windowLabel,
} from "../lib/metricsFilters";
import { buildTeamRows, type TeamRow } from "../lib/teamRows";
import { STATS_WINDOW_DAYS } from "../lib/windows";

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
  const atRisk = scored.filter((row) => isAtRisk(row.health));
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
  const signal = weakestComponents(worst.health!, 1).at(0);
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
      title={`Data failed to load for ${failed.map((team) => team.name).join(", ")}`}
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
        title="Couldn't load teams"
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
      <Flex wrap gap="small" align="center" style={{ marginBottom: 16 }}>
        <MetricsFilterBar filters={filters} onChange={setFilters} />
      </Flex>
      <FailedTeamsAlert teams={teamList} overviews={overviews} />
      <TeamMetricsTable
        rows={rows}
        periodLabel={windowLabel(filters, STATS_WINDOW_DAYS)}
        ranged={isRanged(filters)}
        loading={teams.isLoading}
      />
    </>
  );
}
