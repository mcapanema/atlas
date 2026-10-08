import { Table, Tooltip, type TableProps } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState, type HTMLAttributes, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { formatDay } from "../lib/dates";
import type { Delta } from "../lib/deltas";
import { formatSeconds } from "../lib/duration";
import { isAtRisk, weakestComponents } from "../lib/health";
import type { CellState, TeamRow } from "../lib/teamRows";
import { HealthBadge } from "./HealthBadge";
import { HelpLabel } from "./HelpLabel";
import { Sparkline } from "./Sparkline";

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

/**
 * A figure plus its delta. When any row has a delta, every row reserves the
 * slot, so figures end on the same edge down a right-aligned column.
 */
function FigureWithDelta({
  children,
  delta,
  metric,
  slot,
}: {
  children: ReactNode;
  delta: Delta | null;
  metric: string;
  slot: boolean;
}) {
  return (
    <>
      <span className="fig">{children}</span>
      {slot && (
        <span className="delta-slot">
          <DeltaChip delta={delta} metric={metric} />
        </span>
      )}
    </>
  );
}

/** Column header with a focus/hover definition — recognition over recall. */
function columnHelp(label: string, help: string) {
  return <HelpLabel label={label} help={help} />;
}

function buildColumns(
  periodLabel: string,
  ranged: boolean,
  showDeltas: boolean,
): ColumnsType<TeamRow> {
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
      render: (_, row) => cell(row.state, () => <HealthBadge health={row.health} />),
    },
    {
      // Column headers drop the "(30d)" suffix — the window is stated once in
      // the as-of line and restated per-column in each tooltip; at 1288px the
      // suffixes were pushing the last column behind a horizontal scrollbar.
      title: columnHelp("Throughput", `Work items completed in the last ${periodLabel}.`),
      align: "right",
      sorter: (a, b) => (a.metrics?.completed ?? -1) - (b.metrics?.completed ?? -1),
      render: (_, row) =>
        cell(row.state, () =>
          row.metrics ? (
            <FigureWithDelta delta={row.throughputDelta} metric="throughput" slot={showDeltas}>
              {row.metrics.completed}
            </FigureWithDelta>
          ) : (
            "—"
          ),
        ),
    },
    {
      title: columnHelp(
        "WIP",
        ranged
          ? "Work items in progress at the end of the selected range: started, and not yet completed, moved back, or canceled by then."
          : "Work items in progress right now.",
      ),
      align: "right",
      sorter: (a, b) => (a.metrics?.wip ?? -1) - (b.metrics?.wip ?? -1),
      render: (_, row) =>
        cell(row.state, () => <span className="fig">{row.metrics?.wip ?? "—"}</span>),
    },
    {
      title: columnHelp(
        "Lead time P85",
        `85% of items completed in the last ${periodLabel} took no longer than this, created → done.`,
      ),
      align: "right",
      sorter: (a, b) =>
        (a.metrics?.lead_time?.p85_seconds ?? -1) - (b.metrics?.lead_time?.p85_seconds ?? -1),
      render: (_, row) =>
        cell(row.state, () =>
          row.metrics?.lead_time ? (
            <FigureWithDelta delta={row.leadDelta} metric="lead time" slot={showDeltas}>
              {formatSeconds(row.metrics.lead_time.p85_seconds)}
            </FigureWithDelta>
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
      align: "right",
      sorter: (a, b) => (a.metrics?.flow_efficiency ?? -1) - (b.metrics?.flow_efficiency ?? -1),
      render: (_, row) =>
        cell(row.state, () =>
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
      align: "right",
      sorter: (a, b) => (a.metrics?.blocked_seconds ?? -1) - (b.metrics?.blocked_seconds ?? -1),
      render: (_, row) =>
        cell(row.state, () =>
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
      align: "right",
      sorter: (a, b) => (a.accuracy?.p85_hit_rate ?? -1) - (b.accuracy?.p85_hit_rate ?? -1),
      render: (_, row) =>
        cell(row.state, () =>
          row.accuracy && row.accuracy.evaluated > 0 && row.accuracy.p85_hit_rate != null ? (
            <span className="fig">{Math.round(row.accuracy.p85_hit_rate * 100)}%</span>
          ) : (
            "—"
          ),
        ),
    },
  ];
}

type ExpandIconProps = Parameters<
  NonNullable<NonNullable<TableProps<TeamRow>["expandable"]>["expandIcon"]>
>[0];

/**
 * The row toggle, named per team. AntD's default renders a hidden
 * "Expand row" button on every row, even rows that can't expand; this one
 * exists only where there is something to show.
 */
function renderRiskToggle({ expanded, expandable, onExpand, record, prefixCls }: ExpandIconProps) {
  if (!expandable) return null;
  const icon = `${prefixCls}-row-expand-icon`;
  return (
    <button
      type="button"
      className={`${icon} ${icon}-${expanded ? "expanded" : "collapsed"}`}
      aria-expanded={expanded}
      aria-label={`${expanded ? "Hide" : "Show"} risk reasons for ${record.team.name}`}
      onClick={(event) => {
        // The row itself navigates to the team; the toggle must not.
        event.stopPropagation();
        onExpand(record, event);
      }}
    />
  );
}

/** Beneath an at-risk row: its two weakest health components and the 7-day pulse. */
function RiskDetail({ row }: { row: TeamRow }) {
  const health = row.health!;
  return (
    <div className={`risk-detail risk-detail--${health.band}`}>
      <ul className="risk-detail__reasons">
        {weakestComponents(health, 2).map((component) => (
          <li key={component.name}>
            <strong>{component.name}</strong> {component.reason}
          </li>
        ))}
      </ul>
      {row.pulse && (
        <span className="risk-detail__pulse">
          <Sparkline points={row.pulse.points} />
          <span>lead time P85 {row.pulse.trend} this week</span>
        </span>
      )}
    </div>
  );
}

/**
 * At-risk rows open by default so their reasons can't be missed; the EM
 * can fold any away. Tracks what was collapsed rather than what is open,
 * because a row turns at-risk only once its team's query lands — after
 * mount, where AntD's defaultExpandedRowKeys no longer applies.
 */
function useRiskExpansion(rows: TeamRow[]) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const expandedRowKeys = rows
    .filter((row) => isAtRisk(row.health) && !collapsed.has(row.key))
    .map((row) => row.key);
  const onExpand = (expanded: boolean, row: TeamRow) => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (expanded) next.delete(row.key);
      else next.add(row.key);
      return next;
    });
  };
  return { expandedRowKeys, onExpand };
}

/** The executive dashboard's per-team table; a row click opens that team. */
export function TeamMetricsTable({
  rows,
  periodLabel,
  ranged,
  loading,
}: {
  rows: TeamRow[];
  periodLabel: string;
  ranged: boolean;
  loading: boolean;
}) {
  const navigate = useNavigate();
  const expansion = useRiskExpansion(rows);
  const showDeltas = rows.some((row) => row.throughputDelta != null || row.leadDelta != null);
  return (
    <section aria-label="Delivery metrics by team">
      <Table
        columns={buildColumns(periodLabel, ranged, showDeltas)}
        components={TABLE_COMPONENTS}
        dataSource={rows}
        loading={loading}
        pagination={false}
        showSorterTooltip={false}
        scroll={{ x: "max-content" }}
        expandable={{
          ...expansion,
          rowExpandable: (row) => isAtRisk(row.health),
          expandedRowRender: (row) => <RiskDetail row={row} />,
          expandIcon: renderRiskToggle,
        }}
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
