import { BugOutlined, StopOutlined } from "@ant-design/icons";
import { Table, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";

import type { AgingItem } from "../api/metrics";
import { formatSeconds } from "../lib/duration";
import { ChartCard } from "./ChartCard";
import { HelpLabel } from "./HelpLabel";
import { SlottedTitle } from "./SlottedTitle";

/** "the last day" / "the last 90 days" — the aging history window, in prose. */
function lastDays(days: number): string {
  return days === 1 ? "the last day" : `the last ${days} days`;
}

/** The Age header's help. At a P50 team percentile the two lines coincide: one flag. */
function ageHelp(
  percentile: number,
  historyDays: number,
  medianSeconds: number,
  thresholdSeconds: number,
): string {
  const median = `Flagged > P50 past the median cycle time (${formatSeconds(medianSeconds)})`;
  const team =
    percentile === 50
      ? ""
      : ` and > P${percentile} past P${percentile} (${formatSeconds(thresholdSeconds)})`;
  return `Time in progress. ${median}${team}, over ${lastDays(historyDays)}.`;
}

/** The card help's flag sentence; one flag when the team percentile is the median. */
function agingFlagsHelp(percentile: number, historyDays: number): string {
  const median = `An item's age is flagged > P50 when it has been in progress longer than half the items completed in ${lastDays(historyDays)} took`;
  const team =
    percentile === 50 ? "" : `, and > P${percentile} when longer than ${percentile}% of them`;
  return `${median}${team} (the team's aging percentile and history, set in Metric rules).`;
}

/** One flag per row: past the team percentile (red) wins over past the median (yellow). */
function AgeFlag({ item, percentile }: { item: AgingItem; percentile: number }) {
  if (item.over_percentile) {
    return (
      <span className="delta delta--bad" role="img" aria-label={`over P${percentile}`}>
        &gt; P{percentile}
      </span>
    );
  }
  if (item.over_median) {
    return (
      <span className="delta delta--warn" role="img" aria-label="over P50">
        &gt; P50
      </span>
    );
  }
  return null;
}

function agingColumns({
  percentile,
  historyDays,
  thresholdSeconds,
  medianSeconds,
  slot,
  flagSlot,
}: {
  percentile: number;
  historyDays: number;
  thresholdSeconds: number | null;
  /** Null exactly when thresholdSeconds is: both come from the same history. */
  medianSeconds: number | null;
  /** Some row is flagged: every row reserves the flag slot, so ages share a right edge. */
  slot: boolean;
  /** Some row is blocked or a bug: every row reserves one icon's width, so states share a left edge. */
  flagSlot: boolean;
}): ColumnsType<AgingItem> {
  return [
    {
      title: "Title",
      dataIndex: "title",
      render: (title, item) => <Link to={`/work-items/${item.work_item_id}`}>{title}</Link>,
    },
    {
      title: "Owner",
      dataIndex: "assignee",
      render: (assignee: string | null) =>
        assignee ?? <Typography.Text type="secondary">Unassigned</Typography.Text>,
    },
    {
      title: "State",
      dataIndex: "state",
      render: (state: string, item) => (
        <span className="aging-state">
          {flagSlot && (
            <span className="aging-flags">
              {item.blocked && (
                <Tooltip title="Blocked" trigger={["hover", "focus"]}>
                  <StopOutlined className="aging-blocked" aria-label="Blocked" tabIndex={0} />
                </Tooltip>
              )}
              {item.type === "bug" && (
                <Tooltip title="Bug" trigger={["hover", "focus"]}>
                  <BugOutlined className="aging-bug" aria-label="Bug" tabIndex={0} />
                </Tooltip>
              )}
            </span>
          )}
          {state}
        </span>
      ),
    },
    {
      title: (
        <SlottedTitle slot={slot}>
          {thresholdSeconds === null || medianSeconds === null ? (
            "Age"
          ) : (
            <HelpLabel
              label="Age"
              help={ageHelp(percentile, historyDays, medianSeconds, thresholdSeconds)}
            />
          )}
        </SlottedTitle>
      ),
      align: "right",
      render: (_, item) => (
        <span className="aging-age">
          <span className="fig">{formatSeconds(item.age_seconds)}</span>
          {slot && (
            <span className="delta-slot">
              <AgeFlag item={item} percentile={percentile} />
            </span>
          )}
        </span>
      ),
    },
  ];
}

export function AgingWipCard({
  items,
  percentile,
  historyDays,
  thresholdSeconds,
  medianSeconds,
}: {
  items: AgingItem[];
  percentile: number;
  historyDays: number;
  thresholdSeconds: number | null;
  medianSeconds: number | null;
}) {
  return (
    <ChartCard
      label="Aging WIP"
      help={`Items currently in progress, oldest first. ${agingFlagsHelp(percentile, historyDays)} A stop icon before the state marks an item whose blocked label, state, relation or event is still open (what counts as blocked is set in Metric rules). A bug icon marks an item that the team's type rules classify as a bug.`}
    >
      <Table
        size="small"
        rowKey="work_item_id"
        pagination={false}
        columns={agingColumns({
          percentile,
          historyDays,
          thresholdSeconds,
          medianSeconds,
          slot: items.some((item) => item.over_percentile || item.over_median),
          flagSlot: items.some((item) => item.blocked || item.type === "bug"),
        })}
        dataSource={items}
      />
    </ChartCard>
  );
}
