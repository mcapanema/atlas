import { Alert, Button, Empty, Table, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { HTMLAttributes, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  useAllTeamsFlowMetrics,
  useAllTeamsHealth,
  type DeliveryHealth,
  type FlowMetrics,
} from "../api/metrics";
import {
  useAllTeamsForecastAccuracy,
  useAllTeamsSnapshots,
  type ForecastAccuracy,
  type MetricSnapshot,
} from "../api/snapshots";
import { useTeams, type Team } from "../api/teams";
import { HealthBadge } from "../components/HealthBadge";
import { Sparkline } from "../components/Sparkline";
import { formatDay } from "../lib/dates";
import { computeDelta, leadTimePulse, pickBaseline, type Delta, type Pulse } from "../lib/deltas";
import { formatSeconds } from "../lib/duration";

const BAND_RANK: Record<string, number> = { critical: 0, warning: 1 };

// AntD's Table doesn't forward aria props to the <table> element itself;
// screen-reader table navigation needs the name there, not on the section.
const TABLE_COMPONENTS = {
  table: (props: HTMLAttributes<HTMLTableElement>) => (
    <table {...props} aria-label="Delivery metrics by team" />
  ),
};

interface TeamRow {
  key: string;
  team: Team;
  metrics: FlowMetrics | undefined;
  accuracy: ForecastAccuracy | undefined;
  health: DeliveryHealth | undefined;
  metricsState: CellState;
  accuracyState: CellState;
  healthState: CellState;
  throughputDelta: Delta | null;
  leadDelta: Delta | null;
  pulse: Pulse | null;
}

/**
 * Three honest cell states: a skeleton means "still asking", "unavailable"
 * means "asked and failed", and "—" is reserved for "asked, answered, and
 * there is genuinely no data". A failed query being retried reads as
 * loading again, so the Retry button gives visible feedback.
 */
type CellState = "pending" | "failed" | "ready";

function queryState(
  query: { isPending: boolean; isError: boolean; isFetching: boolean } | undefined,
): CellState {
  if (!query || query.isPending) return "pending";
  if (query.isError) return query.isFetching ? "pending" : "failed";
  return "ready";
}

/** Skeleton for a cell whose query is still in flight — never an em dash. */
function CellSkeleton() {
  return <span className="cell-skeleton" aria-label="Loading" />;
}

function CellFailed() {
  return (
    <Tooltip title="This query failed — use Retry in the alert above." trigger={["hover", "focus"]}>
      <span className="cell-failed" tabIndex={0}>
        unavailable
      </span>
    </Tooltip>
  );
}

function cell(state: CellState, ready: () => ReactNode): ReactNode {
  if (state === "pending") return <CellSkeleton />;
  if (state === "failed") return <CellFailed />;
  return ready();
}

function DeltaChip({ delta, metric }: { delta: Delta | null; metric: string }) {
  if (!delta) return null;
  const arrow = delta.direction === "up" ? "↑" : delta.direction === "down" ? "↓" : "→";
  const tone = delta.good == null ? "flat" : delta.good ? "good" : "bad";
  const pct =
    delta.direction === "flat" ? "0%" : `${Math.round(Math.abs(delta.pct) * 100)}%`;
  return (
    <Tooltip title={`vs prior 30d window (baseline ${formatDay(delta.baselineDate)})`}>
      <span
        className={`delta delta--${tone}`}
        tabIndex={0}
        aria-label={`${metric} ${delta.direction === "flat" ? "unchanged" : `${delta.direction} ${pct}`} versus prior 30-day window`}
      >
        {arrow} {pct}
      </span>
    </Tooltip>
  );
}

/** Column header with a focus/hover definition — recognition over recall. */
function columnHelp(label: string, help: string) {
  return (
    // Explicit focus trigger: hover-only definitions don't exist for
    // keyboard users.
    <Tooltip title={help} trigger={["hover", "focus"]}>
      <span className="th-help" tabIndex={0}>
        {label}
      </span>
    </Tooltip>
  );
}

const columns: ColumnsType<TeamRow> = [
  {
    title: "Team",
    sorter: (a, b) => a.team.name.localeCompare(b.team.name),
    render: (_, row) => <Link to={`/teams?team=${row.team.id}`}>{row.team.name}</Link>,
  },
  {
    title: columnHelp(
      "Health",
      "Composite delivery health, 0–100 — higher is better. Click a score to see each component and its reason.",
    ),
    // Worst first by default: risk is the sort key of an executive view.
    defaultSortOrder: "ascend",
    sorter: (a, b) => (a.health?.score ?? 101) - (b.health?.score ?? 101),
    render: (_, row) => cell(row.healthState, () => <HealthBadge health={row.health} />),
  },
  {
    // Column headers drop the "(30d)" suffix — the window is stated once in
    // the as-of line and restated per-column in each tooltip; at 1288px the
    // suffixes were pushing the last column behind a horizontal scrollbar.
    title: columnHelp("Throughput", "Work items completed in the last 30 days."),
    sorter: (a, b) => (a.metrics?.completed ?? -1) - (b.metrics?.completed ?? -1),
    render: (_, row) =>
      cell(row.metricsState, () =>
        row.metrics ? (
          <>
            <span className="fig">{row.metrics.completed}</span>{" "}
            <DeltaChip delta={row.throughputDelta} metric="throughput" />
          </>
        ) : (
          "—"
        ),
      ),
  },
  {
    title: columnHelp("WIP", "Work items in progress right now."),
    sorter: (a, b) => (a.metrics?.wip ?? -1) - (b.metrics?.wip ?? -1),
    render: (_, row) =>
      cell(row.metricsState, () => <span className="fig">{row.metrics?.wip ?? "—"}</span>),
  },
  {
    title: columnHelp(
      "Lead time P85",
      "85% of items completed in the last 30 days took no longer than this, created → done.",
    ),
    sorter: (a, b) =>
      (a.metrics?.lead_time?.p85_seconds ?? -1) - (b.metrics?.lead_time?.p85_seconds ?? -1),
    render: (_, row) =>
      cell(row.metricsState, () =>
        row.metrics?.lead_time ? (
          <>
            <span className="fig">{formatSeconds(row.metrics.lead_time.p85_seconds)}</span>{" "}
            <DeltaChip delta={row.leadDelta} metric="lead time" />
          </>
        ) : (
          "—"
        ),
      ),
  },
  {
    title: columnHelp(
      "Flow efficiency",
      "Share of cycle time spent actively working (not blocked), averaged over completed items in the last 30 days.",
    ),
    sorter: (a, b) => (a.metrics?.flow_efficiency ?? -1) - (b.metrics?.flow_efficiency ?? -1),
    render: (_, row) =>
      cell(row.metricsState, () =>
        row.metrics?.flow_efficiency != null ? (
          <span className="fig">{Math.round(row.metrics.flow_efficiency * 100)}%</span>
        ) : (
          "—"
        ),
      ),
  },
  {
    title: columnHelp("Blocked time", "Total time items spent blocked in the last 30 days."),
    sorter: (a, b) => (a.metrics?.blocked_seconds ?? -1) - (b.metrics?.blocked_seconds ?? -1),
    render: (_, row) =>
      cell(row.metricsState, () =>
        row.metrics ? (
          <span className="fig">{formatSeconds(row.metrics.blocked_seconds)}</span>
        ) : (
          "—"
        ),
      ),
  },
  {
    title: columnHelp(
      "Forecast accuracy (P85)",
      "Of past forecasts with a known real finish, the share that finished by their predicted P85 date. Calibrated forecasts land near 85% — higher means predictions run conservative, lower means optimistic. “—” means no forecasts evaluated yet.",
    ),
    sorter: (a, b) => (a.accuracy?.p85_hit_rate ?? -1) - (b.accuracy?.p85_hit_rate ?? -1),
    render: (_, row) =>
      cell(row.accuracyState, () =>
        row.accuracy && row.accuracy.evaluated > 0 && row.accuracy.p85_hit_rate != null ? (
          <span className="fig">{Math.round(row.accuracy.p85_hit_rate * 100)}%</span>
        ) : (
          "—"
        ),
      ),
  },
];

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
    (row) =>
      row.healthState === "ready" && (row.health?.score == null || row.health?.band == null),
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

export function ExecutiveDashboardPage() {
  const navigate = useNavigate();
  const teams = useTeams();
  const teamList = teams.data ?? [];
  // ponytail: four API calls per team (metrics, accuracy, health, snapshots);
  // add a portfolio endpoint when team count makes 4N round trips slow (~20+).
  const metrics = useAllTeamsFlowMetrics(teamList);
  const accuracy = useAllTeamsForecastAccuracy(teamList);
  const health = useAllTeamsHealth(teamList);
  const snapshots = useAllTeamsSnapshots(teamList);

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
  if (teams.data && teams.data.length === 0) {
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

  const rows: TeamRow[] = teamList.map((team, index) => {
    const teamMetrics = metrics[index]?.data;
    const teamSnapshots: MetricSnapshot[] = snapshots[index]?.data ?? [];
    const asOf = teamMetrics?.window_end;
    const baseline = asOf ? pickBaseline(teamSnapshots, asOf, 30) : null;
    return {
      key: team.id,
      team,
      metrics: teamMetrics,
      accuracy: accuracy[index]?.data,
      health: health[index]?.data,
      metricsState: queryState(metrics[index]),
      accuracyState: queryState(accuracy[index]),
      healthState: queryState(health[index]),
      throughputDelta: baseline
        ? computeDelta(teamMetrics?.completed, baseline.completed, false, baseline.captured_on)
        : null,
      leadDelta: baseline
        ? computeDelta(
            teamMetrics?.lead_time?.p85_seconds,
            baseline.lead_time_p85_seconds,
            true,
            baseline.captured_on,
          )
        : null,
      pulse: asOf ? leadTimePulse(teamSnapshots, asOf) : null,
    };
  });

  const queryGroups = [metrics, accuracy, health, snapshots];
  const failedTeams = teamList.filter((_, index) =>
    queryGroups.some((group) => group[index]?.isError),
  );
  const retryFailed = () => {
    for (const group of queryGroups) {
      for (const query of group) {
        if (query.isError) void query.refetch();
      }
    }
  };
  const windowSource = rows.find((row) => row.metrics)?.metrics;

  return (
    <>
      <Typography.Title level={3}>Executive Dashboard</Typography.Title>
      <Headline rows={rows} />
      {windowSource && (
        <p className="page-asof">
          Last 30 days · {formatDay(windowSource.window_start)} –{" "}
          {formatDay(windowSource.window_end)}
        </p>
      )}
      {failedTeams.length > 0 && (
        <Alert
          type="warning"
          style={{ marginBottom: 16 }}
          message={`Data failed to load for ${failedTeams.map((team) => team.name).join(", ")}`}
          action={
            <Button size="small" onClick={retryFailed}>
              Retry
            </Button>
          }
        />
      )}
      <AttentionSection rows={rows} />
      <section aria-label="Delivery metrics by team">
        <Table
          columns={columns}
          components={TABLE_COMPONENTS}
          dataSource={rows}
          loading={teams.isLoading}
          pagination={false}
          showSorterTooltip={false}
          scroll={{ x: "max-content" }}
          onRow={(row) => ({
            className: "row-link",
            onClick: (event) => {
              // The row is a convenience surface; interactive children win.
              if ((event.target as HTMLElement).closest("a, button, .ant-popover")) return;
              void navigate(`/teams?team=${row.team.id}`);
            },
          })}
        />
      </section>
    </>
  );
}
