import { AimOutlined } from "@ant-design/icons";
import { Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { StateTime, StateTimes } from "../api/metrics";
import { formatSeconds } from "../lib/duration";
import { ChartCard } from "./ChartCard";

function columns(bottleneck: string | null): ColumnsType<StateTime> {
  return [
    {
      title: "State",
      dataIndex: "state",
      render: (state: string, row) => (
        <span className="state-time-name">
          {state === bottleneck && (
            <Tag icon={<AimOutlined />} color="error">
              Bottleneck
            </Tag>
          )}
          {state}
          {row.wait_state && <Typography.Text type="secondary">wait</Typography.Text>}
        </span>
      ),
    },
    {
      title: "Share",
      dataIndex: "share",
      align: "right",
      render: (share: number) => <span className="fig">{Math.round(share * 100)}%</span>,
    },
    {
      title: "Total",
      dataIndex: "total_seconds",
      align: "right",
      render: (seconds: number) => <span className="fig">{formatSeconds(seconds)}</span>,
    },
    {
      title: "Median",
      dataIndex: "median_seconds",
      align: "right",
      render: (seconds: number) => <span className="fig">{formatSeconds(seconds)}</span>,
    },
    {
      title: "Queue",
      dataIndex: "queue",
      align: "right",
      render: (queue: number) => <span className="fig">{queue}</span>,
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
      help="Working time that items completed in the window spent in each state, from start to done. The state with the most total time is the bottleneck. Wait marks the team's wait states; Queue counts items in that state now."
    >
      {data.bottleneck === null && (
        <Typography.Paragraph type="secondary">{noBottleneckText(data)}</Typography.Paragraph>
      )}
      <Table
        size="small"
        rowKey="state"
        pagination={false}
        columns={columns(data.bottleneck)}
        dataSource={data.states}
      />
    </ChartCard>
  );
}
