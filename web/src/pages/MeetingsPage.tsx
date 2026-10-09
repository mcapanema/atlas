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
import {
  useMeetingPrep,
  type MeetingPrep,
  type MeetingPrepParams,
  type MeetingType,
  type TalkingPoint,
} from "../api/meetings";
import { useSendFeedback } from "../api/personas";
import { useTeams, type Team } from "../api/teams";
import { AdvisorStatusAlerts } from "../components/AdvisorStatusAlerts";
import { EvidenceList } from "../components/EvidenceList";
import { FeedbackCard } from "../components/FeedbackCard";
import { PersonaLearningCard } from "../components/PersonaLearningCard";

const MEETING_OPTIONS: { value: MeetingType; label: string }[] = [
  { value: "daily_standup", label: "Daily standup" },
  { value: "retrospective", label: "Retrospective" },
  { value: "planning", label: "Planning" },
];

interface MeetingInputs {
  /** An edited sprint length; null reads the selected team's rule. */
  sprintDays: number | null;
  remaining: number | null;
  targetDate: string;
}

/** The selected team's sprint length rule, once the team list has loaded. */
function teamSprintDays(teams: Team[] | undefined, teamId: string | undefined) {
  return teams?.find((team) => team.id === teamId)?.sprint_length_days;
}

/** Only the inputs the selected meeting type uses reach the request. */
function prepParams(
  meeting: MeetingType,
  inputs: MeetingInputs,
  sprintDefault: number | undefined,
): MeetingPrepParams {
  if (meeting === "retrospective") return { windowDays: inputs.sprintDays ?? sprintDefault };
  if (meeting === "planning") {
    return {
      remaining: inputs.remaining ?? undefined,
      targetDate: inputs.targetDate || undefined,
    };
  }
  return {};
}

function MeetingInputFields({
  meeting,
  inputs,
  sprintDefault,
  onChange,
}: {
  meeting: MeetingType;
  inputs: MeetingInputs;
  sprintDefault: number | undefined;
  onChange: (inputs: MeetingInputs) => void;
}) {
  if (meeting === "retrospective") {
    return (
      <InputNumber
        min={7}
        max={365}
        value={inputs.sprintDays ?? sprintDefault}
        onChange={(value) => onChange({ ...inputs, sprintDays: value })}
        addonAfter="days"
        aria-label="Sprint length (days)"
      />
    );
  }
  if (meeting === "planning") {
    return (
      <>
        <InputNumber
          min={0}
          placeholder="Planned scope (items)"
          value={inputs.remaining}
          onChange={(value) => onChange({ ...inputs, remaining: value })}
          style={{ width: 180 }}
        />
        <Input
          type="date"
          value={inputs.targetDate}
          onChange={(event) => onChange({ ...inputs, targetDate: event.target.value })}
          style={{ width: 170 }}
          aria-label="Target date"
        />
      </>
    );
  }
  return null;
}

function TalkingPointCard({ point }: { point: TalkingPoint }) {
  return (
    <Card
      title={
        <Space>
          {point.needs_decision && <Tag color="gold">needs decision</Tag>}
          {point.point}
        </Space>
      }
    >
      <Typography.Paragraph>{point.detail}</Typography.Paragraph>
      {point.evidence.length > 0 && <EvidenceList items={point.evidence} />}
    </Card>
  );
}

function PrepResult({
  prep,
  feedback,
  comment,
  onCommentChange,
}: {
  prep: MeetingPrep;
  feedback: ReturnType<typeof useSendFeedback>;
  comment: string;
  onCommentChange: (comment: string) => void;
}) {
  return (
    <>
      <Card title="Headline">
        <Typography.Paragraph style={{ marginBottom: 0 }}>{prep.headline}</Typography.Paragraph>
      </Card>
      <List
        dataSource={prep.talking_points}
        renderItem={(point) => (
          <List.Item style={{ display: "block" }}>
            <TalkingPointCard point={point} />
          </List.Item>
        )}
      />
      <FeedbackCard
        title="Was this prep helpful?"
        thanks="Thanks for the feedback — it will shape this meeting persona's next reflection."
        summary={prep.headline}
        feedback={feedback}
        comment={comment}
        onCommentChange={onCommentChange}
      />
    </>
  );
}

export function MeetingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const teamId = searchParams.get("team") ?? undefined;
  const meeting = (searchParams.get("meeting") as MeetingType | null) ?? "daily_standup";
  const teams = useTeams();
  const status = useAdvisorStatus(); // same OpenRouter key gates advisor and meeting prep
  const [inputs, setInputs] = useState<MeetingInputs>({
    sprintDays: null,
    remaining: null,
    targetDate: "",
  });
  const [comment, setComment] = useState("");
  const sprintDefault = teamSprintDays(teams.data, teamId);
  const prep = useMeetingPrep({ teamId }, meeting, prepParams(meeting, inputs, sprintDefault));
  const feedback = useSendFeedback(meeting);

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
        <AdvisorStatusAlerts
          status={status}
          notConfigured="Meeting prep is not configured. Set ATLAS_OPENROUTER_API_KEY to prepare meetings inside Atlas — or connect an external AI via MCP."
        />
        <Space wrap>
          <Select
            style={{ width: 260 }}
            placeholder="Select a team"
            value={teamId}
            onChange={(value) => {
              setInputs((current) => ({ ...current, sprintDays: null }));
              setParam("team", value);
            }}
            loading={teams.isLoading}
            options={(teams.data ?? []).map((team) => ({ value: team.id, label: team.name }))}
          />
          <Select
            style={{ width: 200 }}
            value={meeting}
            onChange={(value) => setParam("meeting", value)}
            options={MEETING_OPTIONS}
          />
          <MeetingInputFields
            meeting={meeting}
            inputs={inputs}
            sprintDefault={sprintDefault}
            onChange={setInputs}
          />
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
          <PrepResult
            prep={prep.data}
            feedback={feedback}
            comment={comment}
            onCommentChange={setComment}
          />
        )}
      </Space>
    </>
  );
}
