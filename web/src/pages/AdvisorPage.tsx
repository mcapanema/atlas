import { Alert, Button, Card, List, Select, Space, Tag, Typography } from "antd";
import { useSearchParams } from "react-router-dom";

import { useAdvice, useAdvisorStatus } from "../api/advisor";
import { useTeams } from "../api/teams";

const priorityColor: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "blue",
};

export function AdvisorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const teams = useTeams();
  const status = useAdvisorStatus();
  const advice = useAdvice({ teamId });

  if (teams.isError) {
    return <Alert type="error" message="Failed to load teams" />;
  }
  const configured = status.data?.configured ?? false;
  return (
    <>
      <Typography.Title level={3}>Advisor</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        {status.isSuccess && !configured && (
          <Alert
            type="warning"
            message="Advisor is not configured. Set ATLAS_OPENROUTER_API_KEY to enable AI coaching."
          />
        )}
        {status.isError && (
          <Alert
            type="error"
            message="Failed to load advisor status"
            description={status.error.message}
          />
        )}
        <Space>
          <Select
            style={{ width: 260 }}
            placeholder="Select a team"
            value={teamId}
            onChange={(value) => setSearchParams({ team: value })}
            loading={teams.isLoading}
            options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
          />
          <Button
            type="primary"
            disabled={!teamId || !configured}
            loading={advice.isFetching}
            onClick={() => void advice.refetch()}
          >
            Get advice
          </Button>
        </Space>
        {!teamId && <Alert type="info" message="Select a team to get delivery advice." />}
        {advice.isError && (
          <Alert
            type="error"
            message="Failed to generate advice"
            description={advice.error.message}
          />
        )}
        {advice.data && (
          <>
            <Card title="Delivery summary">
              <Typography.Paragraph style={{ marginBottom: 0 }}>
                {advice.data.summary}
              </Typography.Paragraph>
            </Card>
            <List
              dataSource={advice.data.recommendations}
              renderItem={(rec) => (
                <List.Item style={{ display: "block" }}>
                  <Card
                    title={
                      <Space>
                        <Tag color={priorityColor[rec.priority]}>{rec.priority}</Tag>
                        {rec.title}
                      </Space>
                    }
                  >
                    <Typography.Paragraph>
                      <b>Problem:</b> {rec.problem}
                    </Typography.Paragraph>
                    <Typography.Paragraph>
                      <b>Root cause:</b> {rec.root_cause}
                    </Typography.Paragraph>
                    <Typography.Paragraph>
                      <b>Recommended action:</b> {rec.action}
                    </Typography.Paragraph>
                    <Typography.Paragraph style={{ marginBottom: 4 }}>
                      <b>Evidence:</b>
                    </Typography.Paragraph>
                    <ul>
                      {rec.evidence.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </Card>
                </List.Item>
              )}
            />
          </>
        )}
      </Space>
    </>
  );
}
