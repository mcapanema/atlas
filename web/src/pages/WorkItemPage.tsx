import { Alert, Card, Descriptions, Space, Table, Tag, Timeline, Typography } from "antd";
import { useParams } from "react-router-dom";

import { useWorkItemEvents, type WorkItemEvent } from "../api/events";
import {
  type BlockedPeriod,
  type StatePeriod,
  useWorkItem,
  useWorkItemTimeline,
} from "../api/workItems";
import { formatDuration } from "../lib/duration";

function eventLabel(event: WorkItemEvent): string {
  if (event.from_state && event.to_state) {
    return `${event.type}: ${event.from_state} → ${event.to_state}`;
  }
  if (event.to_state) {
    return `${event.type} → ${event.to_state}`;
  }
  return event.type;
}

export function WorkItemPage() {
  const { id = "" } = useParams();
  const workItem = useWorkItem(id);
  const events = useWorkItemEvents(id);
  const timeline = useWorkItemTimeline(id);

  if (workItem.isError) {
    return <Alert type="error" message="Work item not found" />;
  }

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="large">
      <div>
        <Typography.Title level={3}>{workItem.data?.title}</Typography.Title>
        {workItem.data && (
          <Descriptions size="small" column={4}>
            <Descriptions.Item label="Type">
              <Tag>{workItem.data.type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="State">
              <Tag color="blue">{workItem.data.state}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Created">
              {new Date(workItem.data.created_at).toLocaleString()}
            </Descriptions.Item>
            <Descriptions.Item label="External id">
              {workItem.data.external_id ?? "—"}
            </Descriptions.Item>
          </Descriptions>
        )}
      </div>
      <Card title="Event timeline" loading={events.isLoading}>
        {events.data?.length ? (
          <Timeline
            items={events.data.map((event) => ({
              children: `${new Date(event.occurred_at).toLocaleString()} — ${eventLabel(event)}`,
            }))}
          />
        ) : (
          <Typography.Text type="secondary">No events recorded yet.</Typography.Text>
        )}
      </Card>
      <Card title="Time in state" loading={timeline.isLoading}>
        <Table
          rowKey={(period: StatePeriod) => `${period.state}-${period.entered_at}`}
          pagination={false}
          dataSource={timeline.data?.state_periods ?? []}
          columns={[
            { title: "State", dataIndex: "state" },
            {
              title: "Entered",
              dataIndex: "entered_at",
              render: (enteredAt: string) => new Date(enteredAt).toLocaleString(),
            },
            {
              title: "Exited",
              dataIndex: "exited_at",
              render: (exitedAt: string | null) =>
                exitedAt ? new Date(exitedAt).toLocaleString() : "current",
            },
            {
              title: "Duration",
              render: (_: unknown, period: StatePeriod) =>
                formatDuration(period.entered_at, period.exited_at),
            },
          ]}
        />
      </Card>
      <Card title="Blocked periods" loading={timeline.isLoading}>
        {timeline.data?.blocked_periods.length ? (
          <Table
            rowKey={(period: BlockedPeriod) => period.started_at}
            pagination={false}
            dataSource={timeline.data.blocked_periods}
            columns={[
              {
                title: "Blocked at",
                dataIndex: "started_at",
                render: (startedAt: string) => new Date(startedAt).toLocaleString(),
              },
              {
                title: "Unblocked at",
                dataIndex: "ended_at",
                render: (endedAt: string | null) =>
                  endedAt ? new Date(endedAt).toLocaleString() : "still blocked",
              },
              {
                title: "Duration",
                render: (_: unknown, period: BlockedPeriod) =>
                  formatDuration(period.started_at, period.ended_at),
              },
            ]}
          />
        ) : (
          <Typography.Text type="secondary">Never blocked.</Typography.Text>
        )}
      </Card>
    </Space>
  );
}
