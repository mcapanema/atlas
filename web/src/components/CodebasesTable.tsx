import { Alert, Flex, Input, Select, Table, Typography } from "antd";
import { useState } from "react";

import { useCodebases, useUpdateCodebase, type Codebase } from "../api/codebases";
import { useTeams } from "../api/teams";
import { formatDateTime } from "../lib/dates";

type Save = (
  codebase: Codebase,
  change: Partial<Pick<Codebase, "team_id" | "production_environment">>,
) => void;

function EnvironmentInput({ codebase, save }: { codebase: Codebase; save: Save }) {
  const [value, setValue] = useState(codebase.production_environment);
  return (
    <Input
      aria-label={`Production environment for ${codebase.name}`}
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onBlur={() => {
        if (value !== codebase.production_environment)
          save(codebase, { production_environment: value });
      }}
    />
  );
}

/** Repositories found by the GitHub sync; mapping one to a team switches its sync on. */
export function CodebasesTable({ organizationId }: { organizationId: string }) {
  const codebases = useCodebases(organizationId);
  const teams = useTeams();
  const update = useUpdateCodebase();
  const teamOptions = (teams.data ?? [])
    .filter((team) => team.organization_id === organizationId)
    .map((team) => ({ value: team.id, label: team.name }));
  const save: Save = (codebase, change) =>
    update.mutate({
      id: codebase.id,
      team_id: codebase.team_id,
      production_environment: codebase.production_environment,
      ...change,
    });
  return (
    <Flex vertical gap="small">
      {(codebases.error ?? update.error) && (
        <Alert
          type="error"
          showIcon
          title="Codebases failed"
          description={(codebases.error ?? update.error)?.message}
        />
      )}
      <Table<Codebase>
        size="small"
        rowKey="id"
        pagination={false}
        loading={codebases.isLoading}
        dataSource={codebases.data ?? []}
        scroll={{ x: "max-content" }}
        columns={[
          {
            title: "Repository",
            dataIndex: "name",
            render: (name: string, row) =>
              row.url ? (
                <a href={row.url} target="_blank" rel="noreferrer">
                  {name}
                </a>
              ) : (
                name
              ),
          },
          {
            title: "Team",
            dataIndex: "team_id",
            render: (teamId: string | null, row) => (
              <Select
                aria-label={`Team for ${row.name}`}
                style={{ width: 180 }}
                allowClear
                placeholder="Not tracked"
                value={teamId}
                options={teamOptions}
                onChange={(value: string | undefined) => save(row, { team_id: value ?? null })}
              />
            ),
          },
          {
            title: "Production environment",
            dataIndex: "production_environment",
            // Keyed on the saved value so a refetch resets the draft.
            render: (_: string, row) => (
              <EnvironmentInput key={row.production_environment} codebase={row} save={save} />
            ),
          },
          { title: "Pull requests", dataIndex: "pull_requests", align: "right" },
          { title: "Deployments", dataIndex: "deployments", align: "right" },
          {
            title: "Last synced",
            dataIndex: "last_synced_at",
            render: (at: string | null) => (at ? formatDateTime(at) : "Never"),
          },
        ]}
      />
      <Typography.Text type="secondary">
        Only repositories mapped to a team are synced.
      </Typography.Text>
    </Flex>
  );
}
