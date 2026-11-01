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
  isSelf,
  onReset,
  onRemove,
}: {
  user: CurrentUser;
  isSelf: boolean;
  onReset: () => void;
  onRemove: () => void;
}) {
  return (
    <Flex gap="small" justify="flex-end">
      <Button size="small" onClick={onReset}>
        Reset password
      </Button>
      {isSelf ? null : (
        <Popconfirm
          title={`Remove ${user.name}? Their sessions end now.`}
          okText="OK"
          cancelText="Cancel"
          // Keyboard: Enter on Remove, then Enter again confirms.
          okButtonProps={{ autoFocus: true }}
          onConfirm={onRemove}
        >
          <Button size="small" danger>
            Remove
          </Button>
        </Popconfirm>
      )}
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
      render: (_, user) => (
        <RowActions
          user={user}
          isSelf={user.id === me?.id}
          onReset={() => {
            setResetting(user);
          }}
          onRemove={() => {
            remove.mutate(user.id);
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
