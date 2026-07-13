import {
  Alert,
  Button,
  Card,
  Input,
  InputNumber,
  List,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useAdvisorStatus } from "../api/advisor";
import { useMeetingPrep, type MeetingType } from "../api/meetings";
import { useSendFeedback } from "../api/personas";
import { useTeams } from "../api/teams";
import { PersonaLearningCard } from "../components/PersonaLearningCard";

const MEETING_OPTIONS: { value: MeetingType; label: string }[] = [
  { value: "daily_standup", label: "Daily standup" },
  { value: "retrospective", label: "Retrospective" },
  { value: "planning", label: "Planning" },
];

export function MeetingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const meeting = (searchParams.get("meeting") as MeetingType | null) ?? "daily_standup";
  const teams = useTeams();
  const status = useAdvisorStatus(); // same OpenRouter key gates advisor and meeting prep
  const [sprintDays, setSprintDays] = useState(14);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [targetDate, setTargetDate] = useState("");
  const [comment, setComment] = useState("");
  const prep = useMeetingPrep({ teamId }, meeting, {
    windowDays: meeting === "retrospective" ? sprintDays : undefined,
    remaining: meeting === "planning" && remaining !== null ? remaining : undefined,
    targetDate: meeting === "planning" && targetDate !== "" ? targetDate : undefined,
  });
  const feedback = useSendFeedback(meeting);

  const sendFeedback = (rating: "up" | "down") => {
    if (!prep.data) return;
    feedback.mutate({
      rating,
      comment: comment.trim() || null,
      advice_summary: prep.data.headline,
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
      <Typography.Title level={3}>Meetings</Typography.Title>
      <Space direction="vertical" style={{ width: "100%" }} size="large">
        {status.isSuccess && !configured && (
          <Alert
            type="warning"
            message="Meeting prep is not configured. Set ATLAS_OPENROUTER_API_KEY to prepare meetings inside Atlas — or connect an external AI via MCP."
          />
        )}
        {status.isError && (
          <Alert
            type="error"
            message="Failed to load advisor status"
            description={status.error.message}
          />
        )}
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="Select a team"
            value={teamId}
            onChange={(value) => setParam("team", value)}
            loading={teams.isLoading}
            options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
          />
          <Select
            style={{ width: 200 }}
            value={meeting}
            onChange={(value) => setParam("meeting", value)}
            options={MEETING_OPTIONS}
          />
          {meeting === "retrospective" && (
            <InputNumber
              min={7}
              max={365}
              value={sprintDays}
              onChange={(value) => setSprintDays(value ?? 14)}
              addonAfter="days"
              aria-label="Sprint length (days)"
            />
          )}
          {meeting === "planning" && (
            <>
              <InputNumber
                min={0}
                placeholder="Planned scope (items)"
                value={remaining}
                onChange={setRemaining}
                style={{ width: 180 }}
              />
              <Input
                type="date"
                value={targetDate}
                onChange={(event) => setTargetDate(event.target.value)}
                style={{ width: 170 }}
                aria-label="Target date"
              />
            </>
          )}
          <Button
            type="primary"
            disabled={!teamId || !configured}
            loading={prep.isFetching}
            onClick={() => {
              feedback.reset();
              setComment("");
              void prep.refetch();
            }}
          >
            Prepare meeting
          </Button>
        </Space>
        <PersonaLearningCard persona={meeting} />
        {!teamId && <Alert type="info" message="Select a team to prepare a meeting." />}
        {prep.isError && (
          <Alert
            type="error"
            message="Failed to generate meeting prep"
            description={prep.error.message}
          />
        )}
        {prep.data && (
          <>
            <Card title="Headline">
              <Typography.Paragraph style={{ marginBottom: 0 }}>
                {prep.data.headline}
              </Typography.Paragraph>
            </Card>
            <List
              dataSource={prep.data.talking_points}
              renderItem={(point) => (
                <List.Item style={{ display: "block" }}>
                  <Card
                    title={
                      <Space>
                        {point.needs_decision && <Tag color="gold">needs decision</Tag>}
                        {point.point}
                      </Space>
                    }
                  >
                    <Typography.Paragraph>{point.detail}</Typography.Paragraph>
                    {point.evidence.length > 0 && (
                      <>
                        <Typography.Paragraph style={{ marginBottom: 4 }}>
                          <b>Evidence:</b>
                        </Typography.Paragraph>
                        <ul>
                          {point.evidence.map((item, i) => (
                            <li key={i}>{item}</li>
                          ))}
                        </ul>
                      </>
                    )}
                  </Card>
                </List.Item>
              )}
            />
            <Card size="small" title="Was this prep helpful?">
              {feedback.isSuccess ? (
                <Typography.Text>
                  Thanks for the feedback — it will shape this meeting persona's next
                  reflection.
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
