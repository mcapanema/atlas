import { Alert, Button, Card, Input, List, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAdvice, useAdvisorStatus, type Persona } from "../api/advisor";
import { useSendFeedback } from "../api/personas";
import { useTeams } from "../api/teams";

const priorityColor: Record<string, string> = {
  high: "red",
  medium: "orange",
  low: "blue",
};

const PERSONA_OPTIONS = [
  { value: "agile_coach", label: "Agile Coach" },
  { value: "engineering_advisor", label: "Engineering Advisor" },
  { value: "project_advisor", label: "Project Advisor" },
  { value: "delivery_analyst", label: "Delivery Analyst" },
];

export function AdvisorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const teams = useTeams();
  const status = useAdvisorStatus();
  const persona = (searchParams.get("persona") as Persona | null) ?? "agile_coach";
  const advice = useAdvice({ teamId }, persona);
  const feedback = useSendFeedback(persona);
  const [comment, setComment] = useState("");

  const sendFeedback = (rating: "up" | "down") => {
    if (!advice.data) return;
    feedback.mutate({
      rating,
      comment: comment.trim() || null,
      advice_summary: advice.data.summary,
    });
  };

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set(key, value);
    setSearchParams(next);
  };

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
            onChange={(value) => setParam("team", value)}
            loading={teams.isLoading}
            options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
          />
          <Select
            style={{ width: 220 }}
            value={persona}
            onChange={(value) => setParam("persona", value)}
            options={PERSONA_OPTIONS}
          />
          <Button
            type="primary"
            disabled={!teamId || !configured}
            loading={advice.isFetching}
            onClick={() => {
              feedback.reset();
              setComment("");
              void advice.refetch();
            }}
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
            <Card size="small" title="Was this advice helpful?">
              {feedback.isSuccess ? (
                <Typography.Text>
                  Thanks for the feedback — it will shape this persona's next reflection.
                </Typography.Text>
              ) : (
                <Space direction="vertical" style={{ width: "100%" }}>
                  <Input.TextArea
                    rows={2}
                    placeholder="Optional comment"
                    value={comment}
                    onChange={(event) => setComment(event.target.value)}
                  />
                  <Space>
                    <Button loading={feedback.isPending} onClick={() => sendFeedback("up")}>
                      Helpful
                    </Button>
                    <Button loading={feedback.isPending} onClick={() => sendFeedback("down")}>
                      Not helpful
                    </Button>
                  </Space>
                  {feedback.isError && (
                    <Alert
                      type="error"
                      message="Failed to submit feedback"
                      description={feedback.error.message}
                    />
                  )}
                </Space>
              )}
            </Card>
          </>
        )}
      </Space>
    </>
  );
}
