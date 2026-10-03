import { Alert, Button, Card, List, Select, Space, Tag, Typography } from "antd";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  useAdvice,
  useAdvisorStatus,
  type DeliveryAdvice,
  type Persona,
  type Recommendation,
} from "../api/advisor";
import { useSendFeedback } from "../api/personas";
import { useTeams } from "../api/teams";
import { AdvisorStatusAlerts } from "../components/AdvisorStatusAlerts";
import { EvidenceList } from "../components/EvidenceList";
import { FeedbackCard } from "../components/FeedbackCard";
import { PersonaLearningCard } from "../components/PersonaLearningCard";

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

function RecommendationCard({ rec }: { rec: Recommendation }) {
  return (
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
      <EvidenceList items={rec.evidence} />
    </Card>
  );
}

function AdviceResult({
  advice,
  feedback,
  comment,
  onCommentChange,
}: {
  advice: DeliveryAdvice;
  feedback: ReturnType<typeof useSendFeedback>;
  comment: string;
  onCommentChange: (comment: string) => void;
}) {
  return (
    <>
      <Card title="Delivery summary">
        <Typography.Paragraph style={{ marginBottom: 0 }}>{advice.summary}</Typography.Paragraph>
      </Card>
      <List
        dataSource={advice.recommendations}
        renderItem={(rec) => (
          <List.Item style={{ display: "block" }}>
            <RecommendationCard rec={rec} />
          </List.Item>
        )}
      />
      <FeedbackCard
        title="Was this advice helpful?"
        thanks="Thanks for the feedback — it will shape this persona's next reflection."
        summary={advice.summary}
        feedback={feedback}
        comment={comment}
        onCommentChange={onCommentChange}
      />
    </>
  );
}

export function AdvisorPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const teams = useTeams();
  const status = useAdvisorStatus();
  const persona = (searchParams.get("persona") as Persona | null) ?? "agile_coach";
  const advice = useAdvice({ teamId }, persona);
  const feedback = useSendFeedback(persona);
  const [comment, setComment] = useState("");

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
        <AdvisorStatusAlerts
          status={status}
          notConfigured="Advisor is not configured. Set ATLAS_OPENROUTER_API_KEY to enable AI coaching."
        />
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
        <PersonaLearningCard persona={persona} />
        {!teamId && <Alert type="info" message="Select a team to get delivery advice." />}
        {advice.isError && (
          <Alert
            type="error"
            message="Failed to generate advice"
            description={advice.error.message}
          />
        )}
        {advice.data && (
          <AdviceResult
            advice={advice.data}
            feedback={feedback}
            comment={comment}
            onCommentChange={setComment}
          />
        )}
      </Space>
    </>
  );
}
