import { Alert, Typography } from "antd";

import { formatRelative } from "../lib/dates";

/** When a stored run finished, as a relative time. */
export function RunGeneratedAt({
  run,
}: {
  run: { finished_at: string | null; requested_at: string };
}) {
  return (
    <Typography.Text type="secondary">
      Generated {formatRelative(run.finished_at ?? run.requested_at)}
    </Typography.Text>
  );
}

/** The failure of a run (or of starting/reading one); nothing when there is none. */
export function RunError({ title, error }: { title: string; error: string | undefined }) {
  return error === undefined ? null : <Alert type="error" message={title} description={error} />;
}
