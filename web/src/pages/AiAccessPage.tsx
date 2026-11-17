import { Alert, Button, Flex, Popconfirm, Table, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { useState } from "react";

import { useMcpTokens, useRevokeMcpToken, type McpAccess, type McpToken } from "../api/mcpTokens";
import { CreateMcpTokenModal } from "../components/CreateMcpTokenModal";
import { formatDateTime } from "../lib/dates";

const ACCESS_LABEL: Record<McpAccess, string> = {
  read: "Read",
  read_write: "Read and change settings",
};

function RevokeButton({
  token,
  revoking,
  onRevoke,
}: {
  token: McpToken;
  revoking: boolean;
  onRevoke: () => Promise<unknown>;
}) {
  return (
    <Popconfirm
      title={`Revoke ${token.name}? Its client loses access now.`}
      okText="OK"
      cancelText="Cancel"
      okButtonProps={{ autoFocus: true, loading: revoking }}
      // eslint-disable-next-line @typescript-eslint/no-misused-promises -- Popconfirm awaits this promise to keep OK loading
      onConfirm={onRevoke}
    >
      <Button size="small" danger aria-label={`Revoke ${token.name}`}>
        Revoke
      </Button>
    </Popconfirm>
  );
}

function TokensTable() {
  const tokens = useMcpTokens();
  const revoke = useRevokeMcpToken();

  const columns: TableColumnsType<McpToken> = [
    { title: "Name", dataIndex: "name" },
    {
      title: "Access",
      dataIndex: "access",
      render: (access: McpAccess) => ACCESS_LABEL[access],
    },
    {
      title: "Token",
      dataIndex: "hint",
      render: (hint: string) => <Typography.Text code>{`…${hint}`}</Typography.Text>,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      render: (created: string) => formatDateTime(created),
    },
    {
      title: "Last used",
      dataIndex: "last_used_at",
      render: (used: string | null) => (used ? formatDateTime(used) : "Never"),
    },
    {
      title: "Actions",
      align: "right",
      fixed: "right",
      key: "actions",
      render: (_, token) => (
        <RevokeButton
          token={token}
          revoking={revoke.isPending}
          // A failure shows in the page alert, so it is not rethrown here.
          onRevoke={() => revoke.mutateAsync(token.id).catch(() => undefined)}
        />
      ),
    },
  ];

  return (
    <>
      {tokens.error && <Alert type="error" showIcon title={tokens.error.message} />}
      {revoke.error && (
        <Alert
          type="error"
          showIcon
          closable={{
            onClose: () => {
              revoke.reset();
            },
          }}
          title={revoke.error.message}
        />
      )}
      <Table<McpToken>
        size="middle"
        pagination={false}
        scroll={{ x: "max-content" }}
        rowKey="id"
        loading={tokens.isLoading}
        columns={columns}
        dataSource={tokens.data}
      />
    </>
  );
}

export function AiAccessPage() {
  const [creating, setCreating] = useState(false);

  return (
    <div className="page-settings">
      <Flex justify="space-between" align="baseline">
        <Typography.Title level={3}>AI access</Typography.Title>
        <Button
          type="primary"
          onClick={() => {
            setCreating(true);
          }}
        >
          Create token
        </Button>
      </Flex>
      <Flex vertical gap="middle">
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          Connect Claude or another MCP client to Atlas. Each token belongs to you. Revoke a token
          to disconnect its client at once.
        </Typography.Paragraph>
        <TokensTable />
      </Flex>
      {creating && (
        <CreateMcpTokenModal
          onClose={() => {
            setCreating(false);
          }}
        />
      )}
    </div>
  );
}
