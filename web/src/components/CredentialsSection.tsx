import {
  Alert,
  Button,
  Descriptions,
  Flex,
  Form,
  Input,
  Popconfirm,
  Select,
  Typography,
} from "antd";
import { useState, type ReactNode } from "react";

import { useRemoveCredentials, useSaveCredentials, type Integration } from "../api/connectors";
import { formatDateTime, formatRelative } from "../lib/dates";

interface CredentialField {
  name: string;
  label: string;
  secret?: boolean;
  /** A secret field's stored value as its hint ("…" plus its last 4 characters). */
  stored?: string | null;
  /** A note under the field. */
  help?: string;
  /** Renders a Select over these values instead of a text input. */
  options?: { value: string; label: string }[];
}

type Values = Record<string, string>;

/** A hint of "…" alone: the key is under 12 characters, so none of it shows. */
function StoredHint({ hint }: { hint: string | null | undefined }) {
  return (
    <span>
      <Typography.Text className="fig">{hint ?? "…"}</Typography.Text>
      {hint === "…" && <Typography.Text type="secondary"> (key too short to show)</Typography.Text>}
    </span>
  );
}

/** Which key is stored (its tail only) and when it was saved. */
function StoredCredential({
  fields,
  updatedAt,
}: {
  fields: CredentialField[];
  updatedAt: string | null;
}) {
  const keys = fields
    .filter((field) => field.secret)
    .map((field) => ({
      key: field.name,
      // Not the bare field label: the empty input below carries that one.
      label: `Stored ${field.label}`,
      children: <StoredHint hint={field.stored} />,
    }));
  const saved = updatedAt
    ? [
        {
          key: "saved",
          // Not "Saved": that is the form's own confirmation after a save.
          label: "Last saved",
          children: <span title={formatDateTime(updatedAt)}>{formatRelative(updatedAt)}</span>,
        },
      ]
    : [];
  return <Descriptions size="small" column={{ xs: 1, sm: 2 }} items={[...keys, ...saved]} />;
}

/** A stored secret with settings beside it may be left blank: the server keeps it. */
function secretPlaceholder(configured: boolean, keepable: boolean) {
  if (keepable) return "Leave blank to keep the stored key";
  return configured ? "Enter a new key to replace the stored one" : undefined;
}

/** Only the typed values: a blank secret is left out so the server keeps the stored one. */
function filled(values: Values): Values {
  return Object.fromEntries(
    Object.entries(values).filter(([, value]) => typeof value === "string" && value.trim()),
  );
}

function CredentialsForm({
  name,
  fields,
  initial,
  configured,
  hasSettings,
  keepSecrets,
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
  /** The form has a non-secret field (GitHub owner, OpenRouter model). */
  hasSettings: boolean;
  /** A blank secret may be left to keep the stored one (false when every key is required). */
  keepSecrets: boolean;
  saving: boolean;
  saved: boolean;
  onSave: (values: Values) => void;
  extra: ReactNode;
}) {
  const keepable = configured && hasSettings && keepSecrets;
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
          extra={field.help}
          rules={[
            {
              required: !(field.secret && keepable),
              whitespace: true,
              message: `${field.label} is required`,
            },
          ]}
        >
          {field.secret ? (
            // "new-password": browsers and password managers ignore "off" on password inputs.
            <Input.Password
              autoComplete="new-password"
              placeholder={secretPlaceholder(configured, keepable)}
            />
          ) : field.options ? (
            <Select options={field.options} />
          ) : (
            <Input autoComplete="off" />
          )}
        </Form.Item>
      ))}
      <Flex wrap gap="small" align="center">
        <Button type="primary" htmlType="submit" loading={saving}>
          {hasSettings ? "Save" : "Save key"}
        </Button>
        {extra}
        {saved && (
          <Typography.Text type="success">{hasSettings ? "Saved" : "Key saved"}</Typography.Text>
        )}
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
  keepSecrets = true,
}: {
  integration: Integration;
  /** The provider's name, as in "Could not save the {label} key" (or "credentials"). */
  label: string;
  fields: CredentialField[];
  initial: Values;
  status: { configured: boolean; hint: string | null; updated_at: string | null };
  /** False when the server needs every secret on each save (Datadog). */
  keepSecrets?: boolean;
}) {
  const save = useSaveCredentials(integration);
  const remove = useRemoveCredentials(integration);
  // Bumped by each successful save only: a rejected save keeps the typed key, and
  // so does a save that follows a successful one until it, too, succeeds.
  const [saves, setSaves] = useState(0);
  const hasSettings = fields.some((field) => !field.secret);
  return (
    <Flex vertical gap="middle">
      {status.configured && <StoredCredential fields={fields} updatedAt={status.updated_at} />}
      {/* Keyed so every save or removal resets the fields and empties the secret ones,
          even when the new key's hint matches the old one's. */}
      <CredentialsForm
        key={[status.hint, ...Object.values(initial), saves].join(":")}
        name={integration}
        fields={fields}
        initial={initial}
        configured={status.configured}
        hasSettings={hasSettings}
        keepSecrets={keepSecrets}
        saving={save.isPending}
        saved={save.isSuccess}
        onSave={(values) => {
          remove.reset();
          save.mutate(filled(values), { onSuccess: () => setSaves((n) => n + 1) });
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
          // A form with settings may have failed on the owner or model, not the key.
          title={`Could not save the ${label} ${hasSettings ? "credentials" : "key"}`}
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
