import { Alert, Button, Card, Input, Space, Typography } from "antd";

import type { useSendFeedback } from "../api/personas";

/**
 * "Was this helpful?" for one generated answer (advice or meeting prep).
 * The comment lives in the parent so a fresh "Get advice" / "Prepare
 * meeting" click can clear it alongside `feedback.reset()`.
 */
export function FeedbackCard({
  title,
  thanks,
  summary,
  feedback,
  comment,
  onCommentChange,
}: {
  title: string;
  thanks: string;
  /** The answer's headline/summary, stored with the rating as context. */
  summary: string;
  feedback: ReturnType<typeof useSendFeedback>;
  comment: string;
  onCommentChange: (comment: string) => void;
}) {
  const send = (rating: "up" | "down") =>
    feedback.mutate({ rating, comment: comment.trim() || null, advice_summary: summary });

  return (
    <Card size="small" title={title}>
      {feedback.isSuccess ? (
        <Typography.Text>{thanks}</Typography.Text>
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Input.TextArea
            rows={2}
            placeholder="Optional comment"
            value={comment}
            onChange={(event) => onCommentChange(event.target.value)}
          />
          <Space>
            <Button loading={feedback.isPending} onClick={() => send("up")}>
              Helpful
            </Button>
            <Button loading={feedback.isPending} onClick={() => send("down")}>
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
  );
}
