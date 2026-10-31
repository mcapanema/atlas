import { Alert, Button, Flex, Form, Input, Popconfirm, Typography } from "antd";
import type { ReactNode } from "react";

import { useRemoveCredentials, useSaveCredentials, type Integration } from "../api/connectors";

interface CredentialField {
  name: string;
  label: string;
  secret?: boolean;
}

type Values = Record<string, string>;

function CredentialsForm({
  name,
  fields,
  initial,
  configured,
  saving,
  saved,
  onSave,
  extra,
}: {
  name: string;
  fields: CredentialField[];
  /** Non-secret fields only: a stored secret never comes back to the browser. */
  initial: Values;
  configured: boolean;
  saving: boolean;
  saved: boolean;
  onSave: (values: Values) => void;
  extra: ReactNode;
}) {
  return (
    <Form<Values>
      name={name}
      layout="vertical"
      style={{ maxWidth: 480 }}
      initialValues={initial}
      onFinish={onSave}
    >
      {fields.map((field) => (
        <Form.Item
          key={field.name}
          name={field.name}
          label={field.label}
          rules={[{ required: true, whitespace: true }]}
        >
          {field.secret ? (
            <Input.Password
              autoComplete="off"
              placeholder={configured ? "Enter a new key to replace the stored one" : undefined}
            />
          ) : (
            <Input />
          )}
        </Form.Item>
      ))}
      <Flex wrap gap="small" align="center">
        <Button type="primary" htmlType="submit" loading={saving}>
          Save key
        </Button>
        {extra}
        {saved && <Typography.Text type="success">Key saved</Typography.Text>}
      </Flex>
    </Form>
  );
}

/** A connector's credentials: save (checked by the server first), replace, remove. */
export function CredentialsSection({
  integration,
  label,
  fields,
  initial,
  status,
}: {
  integration: Integration;
  /** The provider's name, as in "Could not save the {label} key". */
  label: string;
  fields: CredentialField[];
  initial: Values;
  status: { configured: boolean; hint: string | null };
}) {
  const save = useSaveCredentials(integration);
  const remove = useRemoveCredentials(integration);
  return (
    <Flex vertical gap="middle">
      {/* Keyed so a save or removal resets the fields and empties the secret ones. */}
      <CredentialsForm
        key={[status.hint, ...Object.values(initial)].join(":")}
        name={integration}
        fields={fields}
        initial={initial}
        configured={status.configured}
        saving={save.isPending}
        saved={save.isSuccess}
        onSave={(values) => {
          remove.reset();
          save.mutate(values);
        }}
        extra={
          status.configured && (
            <Popconfirm
              title={`Remove the ${label} key?`}
              okText="Remove"
              okButtonProps={{ danger: true }}
              onConfirm={() => {
                save.reset();
                remove.mutate();
              }}
            >
              <Button danger loading={remove.isPending}>
                Remove key
              </Button>
            </Popconfirm>
          )
        }
      />
      {save.isError && (
        <Alert
          type="error"
          showIcon
          title={`Could not save the ${label} key`}
          description={save.error.message}
        />
      )}
      {remove.isError && (
        <Alert
          type="error"
          showIcon
          title={`Could not remove the ${label} key`}
          description={remove.error.message}
        />
      )}
    </Flex>
  );
}
