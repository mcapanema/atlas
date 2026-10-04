import { Alert, Button, Empty, Modal, Select, Space, Typography } from "antd";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { useMetricRules, useRecomputeHistory, type RecomputeStatus } from "../api/metricRules";
import { useOrganizations, type Organization } from "../api/organizations";
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
  canRetry,
}: {
  status: RecomputeStatus;
  onRetry: () => void;
  retrying: boolean;
  canRetry: boolean;
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
          <Button size="small" onClick={onRetry} loading={retrying} disabled={!canRetry}>
            Retry
          </Button>
        }
      />
    );
  }
  return null;
}

/** Switches scope via the URL, asking first when the form holds unsaved edits. */
function useScopeSwitch(dirty: boolean) {
  const [, setSearchParams] = useSearchParams();
  const [modal, modalContext] = Modal.useModal();
  const switchScope = (value: string) => {
    if (!dirty) return setSearchParams(scopeParams(value));
    modal.confirm({
      title: "Discard unsaved changes?",
      content: "Switching scope drops the edits you haven't saved.",
      okText: "Discard and switch",
      onOk: () => setSearchParams(scopeParams(value)),
    });
  };
  return [switchScope, modalContext] as const;
}

function RulesWorkspace({
  organizations,
  loading,
}: {
  organizations: Organization[];
  loading: boolean;
}) {
  const [searchParams] = useSearchParams();
  const [dirty, setDirty] = useState(false);
  const [switchScope, modalContext] = useScopeSwitch(dirty);
  const teams = useTeams();
  const scope = scopeFromParams(searchParams, organizations[0]?.id);
  const view = useMetricRules(scope);
  const organizationId = recomputeOrganization(scope, teams.data);
  const recompute = useRecomputeHistory(organizationId);
  const { reset: resetRecompute } = recompute;
  const scopeKey = scopeValue(scope);
  // A failed recompute belongs to the scope it ran for.
  useEffect(() => resetRecompute(), [scopeKey, resetRecompute]);

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      {modalContext}
      <Space wrap>
        <Select
          aria-label="Rules for"
          style={{ width: 320 }}
          placeholder="Select a team or the workspace default"
          value={scopeValue(scope)}
          options={scopeOptions(organizations, teams.data ?? [])}
          loading={loading || teams.isLoading}
          onChange={switchScope}
        />
        {scope?.kind === "organization" && (
          <Button onClick={() => recompute.mutate()} loading={recompute.isPending}>
            Recompute history
          </Button>
        )}
      </Space>
      {recompute.isError && (
        <Alert
          type="error"
          showIcon
          message="Couldn't start the recompute"
          description={recompute.error.message}
        />
      )}
      {view.isError && <Alert type="error" showIcon message="Couldn't load the rules" />}
      {view.data && scope && (
        <>
          <RecomputeBanner
            status={view.data.recompute}
            onRetry={() => recompute.mutate()}
            retrying={recompute.isPending}
            canRetry={organizationId !== undefined}
          />
          <MetricRulesForm
            key={scopeValue(scope)}
            scope={scope}
            view={view.data}
            onDirtyChange={setDirty}
          />
        </>
      )}
    </Space>
  );
}

export function MetricRulesPage() {
  const organizations = useOrganizations();
  return (
    <>
      <Typography.Title level={3}>Metric rules</Typography.Title>
      <Typography.Paragraph type="secondary">
        How Atlas reads your delivery data. Teams inherit the workspace default and can override any
        rule; every dashboard, forecast and the snapshot history follow the team&apos;s rules.
      </Typography.Paragraph>
      {organizations.isSuccess && organizations.data.length === 0 ? (
        <Empty description="No organizations yet. Create one to set its metric rules." />
      ) : (
        <RulesWorkspace
          organizations={organizations.data ?? []}
          loading={organizations.isLoading}
        />
      )}
    </>
  );
}
