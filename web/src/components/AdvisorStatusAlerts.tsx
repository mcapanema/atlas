import { Alert } from "antd";

import type { useAdvisorStatus } from "../api/advisor";

/** Not-configured warning or load error for the shared OpenRouter key. */
export function AdvisorStatusAlerts({
  status,
  notConfigured,
}: {
  status: ReturnType<typeof useAdvisorStatus>;
  notConfigured: string;
}) {
  if (status.isError) {
    return (
      <Alert
        type="error"
        message="Failed to load advisor status"
        description={status.error.message}
      />
    );
  }
  if (status.isSuccess && !status.data.configured) {
    return <Alert type="warning" message={notConfigured} />;
  }
  return null;
}
