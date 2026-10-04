import { Alert, Button, Select, Space, Typography } from "antd";
import { useSearchParams } from "react-router-dom";

import { useMetricRules, useRecomputeHistory, type RecomputeStatus } from "../api/metricRules";
import { useOrganizations } from "../api/organizations";
import { useTeams } from "../api/teams";
import { MetricRulesForm } from "../components/MetricRulesForm";
import {
  recomputeOrganization,
  scopeFromParams,
  scopeOptions,
  scopeParams,
  scopeValue,
} from "../lib/metricRules";

function RecomputeBanner({
  status,
  onRetry,
  retrying,
}: {
  status: RecomputeStatus;
  onRetry: () => void;
  retrying: boolean;
}) {
  if (status.state === "running") {
    return (
      <Alert
        type="info"
        showIcon
        message="Recomputing history…"
        description="Snapshot history and forecast backtests are being rewritten under the new rules. Live dashboards already use them."
      />
    );
  }
  if (status.state === "failed") {
    return (
      <Alert
        type="error"
        showIcon
        message="History recompute failed"
        description={status.error ?? undefined}
        action={
          <Button size="small" onClick={onRetry} loading={retrying}>
            Retry
          </Button>
        }
      />
    );
  }
  return null;
}

export function MetricRulesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const organizations = useOrganizations();
  const teams = useTeams();
  const scope = scopeFromParams(searchParams, organizations.data?.[0]?.id);
  const view = useMetricRules(scope);
  const recompute = useRecomputeHistory(recomputeOrganization(scope, teams.data));
  const running = view.data?.recompute.state === "running";

  return (
    <>
      <Typography.Title level={3}>Metric rules</Typography.Title>
      <Typography.Paragraph type="secondary">
        How Atlas reads your delivery data. Teams inherit the workspace default and can override any
        rule; every dashboard, forecast and the snapshot history follow the team&apos;s rules.
      </Typography.Paragraph>
      <Space direction="vertical" size="large" style={{ width: "100%" }}>
        <Space wrap>
          <Select
            aria-label="Rules for"
            style={{ width: 320 }}
            placeholder="Select a team or the workspace default"
            value={scopeValue(scope)}
            options={scopeOptions(organizations.data ?? [], teams.data ?? [])}
            loading={organizations.isLoading || teams.isLoading}
            onChange={(value: string) => setSearchParams(scopeParams(value))}
          />
          {scope?.kind === "organization" && (
            <Button
              onClick={() => recompute.mutate()}
              loading={recompute.isPending}
              disabled={running}
            >
              Recompute history
            </Button>
          )}
        </Space>
        {view.isError && <Alert type="error" showIcon message="Couldn't load the rules" />}
        {view.data && scope && (
          <>
            <RecomputeBanner
              status={view.data.recompute}
              onRetry={() => recompute.mutate()}
              retrying={recompute.isPending}
            />
            <MetricRulesForm key={scopeValue(scope)} scope={scope} view={view.data} />
          </>
        )}
      </Space>
    </>
  );
}
