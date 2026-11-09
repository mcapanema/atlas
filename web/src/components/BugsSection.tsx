import { Alert, Col, Row, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import {
  useBugMetrics,
  type BugMetrics,
  type FixStats,
  type MetricsFilters,
  type PriorityFix,
} from "../api/metrics";
import { buildBugFlowOption } from "../lib/charts";
import { formatDateTime } from "../lib/dates";
import { formatSeconds } from "../lib/duration";
import { windowLabel } from "../lib/metricsFilters";
import { STATS_WINDOW_DAYS } from "../lib/windows";
import { useThemeMode } from "../theme/context";
import { ChartCard } from "./ChartCard";
import { EChart } from "./EChart";
import { HelpLabel } from "./HelpLabel";
import { SampleNote } from "./SampleNote";
import { StatCard } from "./StatCard";

const PRIORITY_LABEL: Record<PriorityFix["priority"], string> = {
  urgent: "Urgent",
  high: "High",
  medium: "Medium",
  low: "Low",
  none: "No priority",
};

const FLOW_HELP =
  "Bugs created (by creation date) and bugs completed in each bucket of the window. Windows of 21 days or fewer bucket per day; longer windows bucket per week, and the oldest bucket is shorter when the window isn't a whole number of weeks. One bug can count in both series.";

const FIX_HELP =
  "Lead time of the bugs completed in the window, from arrival to done, in working days on the team calendar (set in Metric rules). Rows group bugs by their current priority in Linear; All bugs also counts bugs whose priority is unknown.";

const COLUMN_HELP = {
  priority: "The bug's current priority in Linear. No priority means none is set there.",
  median:
    "Median lead time of the bugs fixed in the window, in working days. Half of them took less.",
  fixed: "Bugs completed in the window.",
  open: "Bugs not completed or canceled at the end of the period (today when no period is set). For a past period, the aging table still shows today.",
  oldestOpen:
    "Age of the oldest open bug since it arrived, in working days on the team calendar, so it reads lower than its calendar age in Linear. Measured at the end of the period (today when no period is set).",
};

function cardHelp(dataAsOf: string | null): string {
  const asOf = dataAsOf ? ` Data as of ${formatDateTime(dataAsOf)}.` : "";
  return (
    "Bugs are items the team's type rules (Metric rules) classify as bugs. A bug counts as created on its creation date, even when its label was added later, and a bug canceled before completion counts nowhere. One bug can count in both chart series. " +
    "The numbers are a lower bound when bugs miss their label." +
    asOf
  );
}

/** A note under a figure whose sample is above zero but below the evidence floor. */
function FloorNote({ sample, min, noun }: { sample: number; min: number; noun: string }) {
  if (sample <= 0 || sample >= min) return null;
  return (
    <span className="dora-detail">
      <SampleNote sample={sample} min={min} noun={noun} />
    </span>
  );
}

function BugRatios({ data }: { data: BugMetrics }) {
  const min = data.min_sample;
  return (
    <div className="stat-grid">
      <StatCard
        title="New bugs per non-bug item completed"
        value={data.per_item === null ? "—" : data.per_item.toFixed(2)}
        help="New bugs ÷ items completed that are not bugs. Bugs are left out of the denominator, so a bug sprint does not lower it."
      >
        <span className="dora-detail">
          {data.created} bugs / {data.non_bug_completed} non-bug items
        </span>
        <FloorNote sample={data.non_bug_completed} min={min} noun="non-bug items" />
      </StatCard>
      <StatCard
        title="Bug share"
        value={data.share === null ? "—" : `${Math.round(data.share * 100)}%`}
        help="Bugs completed ÷ all items completed in the window: the share of completed work that was bug fixes."
      >
        <span className="dora-detail">
          {data.completed} of {data.all_completed}
        </span>
        <FloorNote sample={data.all_completed} min={min} noun="completed items" />
      </StatCard>
      <StatCard
        title="Bugs created"
        value={data.created}
        help="Bugs created in the window, by creation date: the inflow. A bug canceled before it was done counts nowhere."
      />
      <StatCard
        title="Bugs fixed"
        value={data.completed}
        help="Bugs completed in the window: the outflow. The same count as the Fixed column of All bugs."
      />
    </div>
  );
}

function BugFlowChart({ data }: { data: BugMetrics }) {
  const { mode } = useThemeMode();
  const option = useMemo(
    () => buildBugFlowOption(data.buckets, data.bucket_days, mode),
    [data, mode],
  );
  // One bucket is not a trend, as for the Throughput chart.
  if (data.buckets.length <= 1) return null;
  return (
    <>
      <Typography.Text strong>
        <HelpLabel label="Created vs. completed" help={FLOW_HELP} />
      </Typography.Text>
      <EChart option={option} />
    </>
  );
}

interface FixRow extends FixStats {
  key: string;
  label: string;
}

function fixColumns(min: number): ColumnsType<FixRow> {
  const figure = (seconds: number | null) => (
    <span className="fig">{seconds === null ? "—" : formatSeconds(seconds)}</span>
  );
  return [
    { title: <HelpLabel label="Priority" help={COLUMN_HELP.priority} />, dataIndex: "label" },
    {
      title: <HelpLabel label="Median" help={COLUMN_HELP.median} />,
      align: "right",
      render: (_, row) => (
        <>
          {figure(row.median_seconds)}
          <FloorNote sample={row.fixed} min={min} noun="fixed bugs" />
        </>
      ),
    },
    {
      title: <HelpLabel label="Fixed" help={COLUMN_HELP.fixed} />,
      dataIndex: "fixed",
      align: "right",
      render: (n: number) => <span className="fig">{n}</span>,
    },
    {
      title: <HelpLabel label="Open" help={COLUMN_HELP.open} />,
      dataIndex: "open",
      align: "right",
      render: (n: number) => <span className="fig">{n}</span>,
    },
    {
      title: <HelpLabel label="Oldest open" help={COLUMN_HELP.oldestOpen} />,
      dataIndex: "oldest_open_seconds",
      align: "right",
      render: (seconds: number | null) => figure(seconds),
    },
  ];
}

function BugFixTable({ data }: { data: BugMetrics }) {
  const rows: FixRow[] = [
    { key: "all", label: "All bugs", ...data.all_bugs },
    ...data.priorities.map(({ priority, ...stats }) => ({
      key: priority,
      label: PRIORITY_LABEL[priority],
      ...stats,
    })),
  ];
  return (
    <>
      <Typography.Text strong>
        <HelpLabel label="Bug lead time by priority" help={FIX_HELP} />
      </Typography.Text>
      <Table
        size="small"
        rowKey="key"
        pagination={false}
        columns={fixColumns(data.min_sample)}
        dataSource={rows}
      />
      {data.unknown_priority > 0 && (
        <Typography.Text type="secondary">
          Priority unknown for {data.unknown_priority} bugs (not synced yet, or not sent by the
          source).
        </Typography.Text>
      )}
    </>
  );
}

/** no_mapping / no_matches: what to fix, and where. */
function SetupAlert({ data, teamId }: { data: BugMetrics; teamId: string }) {
  const message =
    data.state === "no_mapping"
      ? "No label counts as a bug for this team."
      : `No bug found up to the end of this period for the label(s) ${data.bug_labels.join(", ")}. If the team marks bugs with another label, map it in Metric rules.`;
  return (
    <Alert
      type="info"
      showIcon
      title={message}
      description={<Link to={`/metric-rules?team=${teamId}`}>Map a bug label in Metric rules</Link>}
    />
  );
}

function BugsBody({ data, filtered }: { data: BugMetrics; filtered: boolean }) {
  return (
    <div className="bugs-section">
      <BugRatios data={data} />
      <Row gutter={[24, 16]}>
        <Col xs={24} lg={12} className="bugs-section__col">
          <BugFlowChart data={data} />
          {data.bug_labels.length > 0 && (
            <Typography.Text type="secondary">
              Counts as bug: {data.bug_labels.join(", ")}
            </Typography.Text>
          )}
          {filtered && (
            <Typography.Text type="secondary">
              The type filter does not apply to this section.
            </Typography.Text>
          )}
        </Col>
        <Col xs={24} lg={12} className="bugs-section__col">
          <BugFixTable data={data} />
        </Col>
      </Row>
    </div>
  );
}

/** The Bugs section of the Team page (ADR-0030); nothing for a project, while loading, or on error. */
export function BugsSection({
  teamId,
  filters,
}: {
  teamId: string | undefined;
  filters: MetricsFilters;
}) {
  const bugs = useBugMetrics(teamId, filters);
  if (!teamId || !bugs.data) return null;
  const data = bugs.data;
  return (
    <ChartCard
      label={`Bugs (${windowLabel(filters, STATS_WINDOW_DAYS)})`}
      help={cardHelp(data.data_as_of)}
    >
      {data.state === "ok" ? (
        <BugsBody data={data} filtered={(filters.types?.length ?? 0) > 0} />
      ) : (
        <SetupAlert data={data} teamId={teamId} />
      )}
    </ChartCard>
  );
}
