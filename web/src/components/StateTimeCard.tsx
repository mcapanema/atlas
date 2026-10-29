import { AimOutlined } from "@ant-design/icons";
import { Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { StateTime, StateTimes } from "../api/metrics";
import { formatSeconds } from "../lib/duration";
import { ChartCard } from "./ChartCard";

/** A row's identity: a project spanning teams can list one state per team. */
function rowKey(row: StateTime): string {
  return `${row.team ?? ""}\u0000${row.state}`;
}

/** "<1%" for a share that rounds to zero but isn't: a few days still count. */
function formatShare(share: number): string {
  return share > 0 && share < 0.005 ? "<1%" : `${Math.round(share * 100)}%`;
}

function figure(text: string | number) {
  return <span className="fig">{text}</span>;
}

/** The state, then its flags; the name leads so every row's name starts at one x. */
function StateName({ row, bottleneck }: { row: StateTime; bottleneck: boolean }) {
  return (
    <span className="state-time-name">
      {row.state}
      {bottleneck && (
        <span className="delta delta--bad">
          <AimOutlined aria-hidden /> Bottleneck
        </span>
      )}
      {row.wait_state && <span className="delta">wait</span>}
    </span>
  );
}

function columns(data: StateTimes): ColumnsType<StateTime> {
  const isBottleneck = (row: StateTime) =>
    row.state === data.bottleneck && row.team === data.bottleneck_team;
  const split = data.states.some((row) => row.team !== null);
  return [
    {
      title: "State",
      dataIndex: "state",
      render: (_, row) => <StateName row={row} bottleneck={isBottleneck(row)} />,
    },
    ...(split ? [{ title: "Team", dataIndex: "team" }] : []),
    {
      title: "Share",
      dataIndex: "share",
      align: "right",
      render: (share: number) => figure(formatShare(share)),
    },
    {
      title: "Total",
      dataIndex: "total_seconds",
      align: "right",
      render: (seconds: number) => figure(formatSeconds(seconds)),
    },
    {
      title: "Median",
      dataIndex: "median_seconds",
      align: "right",
      render: (seconds: number) => figure(formatSeconds(seconds)),
    },
    {
      title: "Queue",
      dataIndex: "queue",
      align: "right",
      render: (queue: number) => figure(queue),
    },
  ];
}

/** Why there is no bottleneck: too few items measured, or none held time in a state. */
function noBottleneckText(data: StateTimes): string {
  return data.measured < data.min_sample
    ? `No bottleneck yet: ${data.measured} of ${data.min_sample} completed items measured.`
    : "No bottleneck yet: no in-cycle time measured.";
}

/** Time in each workflow state, with the statistically computed bottleneck marked. */
export function StateTimeCard({ data }: { data: StateTimes }) {
  return (
    <ChartCard
      label="Time in state"
      help="Working time that items completed in the window spent in each state, from start to done. The state with the most total time is the bottleneck. Wait marks the team's wait states; Queue counts items in that state now. In a project that spans teams, each team's states get their own rows."
    >
      {data.bottleneck === null && (
        <Typography.Paragraph type="secondary">{noBottleneckText(data)}</Typography.Paragraph>
      )}
      <Table
        size="small"
        rowKey={rowKey}
        pagination={false}
        columns={columns(data)}
        dataSource={data.states}
      />
    </ChartCard>
  );
}
