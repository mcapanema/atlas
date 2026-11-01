import { Alert, Button, Flex, Popconfirm, Table, Tag, Typography } from "antd";
import type { TableColumnsType } from "antd";
import { useState } from "react";

import { useAuthStatus, type CurrentUser } from "../api/auth";
import { useDeleteUser, useUsers } from "../api/users";
import { AddUserModal } from "../components/AddUserModal";
import { ResetPasswordModal } from "../components/ResetPasswordModal";
import { formatDateTime } from "../lib/dates";

function RowActions({
  user,
  removing,
  onReset,
  onRemove,
}: {
  user: CurrentUser;
  removing: boolean;
  onReset: () => void;
  onRemove: () => Promise<unknown>;
}) {
  return (
    <Flex gap="small" justify="flex-end">
      <Button size="small" aria-label={`Reset password for ${user.name}`} onClick={onReset}>
        Reset password
      </Button>
      <Popconfirm
        title={`Remove ${user.name}? Their sessions end now.`}
        okText="OK"
        cancelText="Cancel"
        // Keyboard: Enter on Remove, then Enter again confirms; one DELETE at a time.
        okButtonProps={{ autoFocus: true, loading: removing }}
        // eslint-disable-next-line @typescript-eslint/no-misused-promises -- Popconfirm awaits this promise to keep OK loading
        onConfirm={onRemove}
      >
        <Button size="small" danger aria-label={`Remove ${user.name}`}>
          Remove
        </Button>
      </Popconfirm>
    </Flex>
  );
}

function UsersTable() {
  const me = useAuthStatus().data?.user;
  const users = useUsers();
  const remove = useDeleteUser();
  const [resetting, setResetting] = useState<CurrentUser | null>(null);

  const columns: TableColumnsType<CurrentUser> = [
    {
      title: "Name",
      dataIndex: "name",
      render: (name: string, user) => (
        <>
          {name}
          {user.id === me?.id && <Tag style={{ marginInlineStart: 8 }}>You</Tag>}
        </>
      ),
    },
    { title: "Email", dataIndex: "email" },
    {
      title: "Role",
      dataIndex: "is_admin",
      render: (isAdmin: boolean) => <Tag>{isAdmin ? "Admin" : "Member"}</Tag>,
    },
    {
      title: "Created",
      dataIndex: "created_at",
      render: (created: string) => formatDateTime(created),
    },
    {
      title: "Actions",
      align: "right",
      fixed: "right",
      key: "actions",
      // Your own row has no actions: resetting yourself ends your session (use
      // Change password in the account menu) and you cannot remove yourself.
      render: (_, user) =>
        user.id === me?.id ? null : (
          <RowActions
            user={user}
            removing={remove.isPending}
            onReset={() => {
              setResetting(user);
            }}
            onRemove={() => {
              // The promise keeps the popconfirm open (OK loading) until the DELETE ends;
              // a failure shows in the page alert, so it is not rethrown here.
              return remove.mutateAsync(user.id).catch(() => undefined);
            }}
          />
        ),
    },
  ];

  return (
    <>
      {users.error && <Alert type="error" showIcon title={users.error.message} />}
      {remove.error && (
        <Alert
          type="error"
          showIcon
          closable={{
            onClose: () => {
              remove.reset();
            },
          }}
          title={remove.error.message}
        />
      )}
      <Table<CurrentUser>
        size="middle"
        pagination={false}
        scroll={{ x: "max-content" }}
        rowKey="id"
        loading={users.isLoading}
        columns={columns}
        dataSource={users.data}
      />
      <ResetPasswordModal
        user={resetting}
        onClose={() => {
          setResetting(null);
        }}
      />
    </>
  );
}

export function UsersPage() {
  const status = useAuthStatus();
  const [adding, setAdding] = useState(false);
  const isAdmin = status.data?.user?.is_admin === true;

  return (
    <div className="page-settings">
      <Flex justify="space-between" align="baseline">
        <Typography.Title level={3}>Users</Typography.Title>
        {isAdmin && (
          <Button
            type="primary"
            onClick={() => {
              setAdding(true);
            }}
          >
            Add user
          </Button>
        )}
      </Flex>
      {isAdmin ? (
        <Flex vertical gap="middle">
          <UsersTable />
          <AddUserModal
            open={adding}
            onClose={() => {
              setAdding(false);
            }}
          />
        </Flex>
      ) : (
        status.data && <Alert type="warning" showIcon title="Only administrators manage users." />
      )}
    </div>
  );
}
