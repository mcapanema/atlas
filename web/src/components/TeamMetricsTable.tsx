import { Table, Tooltip } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { HTMLAttributes, ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { formatDay } from "../lib/dates";
import type { Delta } from "../lib/deltas";
import { formatSeconds } from "../lib/duration";
import type { CellState, TeamRow } from "../lib/teamRows";
import { HealthBadge } from "./HealthBadge";
import { HelpLabel } from "./HelpLabel";

// AntD's Table doesn't forward aria props to the <table> element itself;
// screen-reader table navigation needs the name there, not on the section.
const TABLE_COMPONENTS = {
  table: (props: HTMLAttributes<HTMLTableElement>) => (
    <table {...props} aria-label="Delivery metrics by team" />
  ),
};

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
  const pct = delta.direction === "flat" ? "0%" : `${Math.round(Math.abs(delta.pct) * 100)}%`;
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
  return <HelpLabel label={label} help={help} />;
}

function buildColumns(periodLabel: string): ColumnsType<TeamRow> {
  return [
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
      title: columnHelp("Throughput", `Work items completed in the last ${periodLabel}.`),
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
        `85% of items completed in the last ${periodLabel} took no longer than this, created → done.`,
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
        `Share of cycle time spent actively working (not blocked), averaged over completed items in the last ${periodLabel}.`,
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
      title: columnHelp(
        "Blocked time",
        `Time the items completed in the last ${periodLabel} spent blocked while in progress (start to done), summed across items.`,
      ),
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
}

/** The executive dashboard's per-team table; a row click opens that team. */
export function TeamMetricsTable({
  rows,
  periodLabel,
  loading,
}: {
  rows: TeamRow[];
  periodLabel: string;
  loading: boolean;
}) {
  const navigate = useNavigate();
  return (
    <section aria-label="Delivery metrics by team">
      <Table
        columns={buildColumns(periodLabel)}
        components={TABLE_COMPONENTS}
        dataSource={rows}
        loading={loading}
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
  );
}
