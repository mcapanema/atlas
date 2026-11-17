import { Alert, Button, Flex, Form, Input, Modal, Radio, Typography } from "antd";

import { useCreateMcpToken, type IssuedMcpToken, type McpAccess } from "../api/mcpTokens";
import { connectSnippets } from "../lib/mcpConnect";

interface Values {
  name: string;
  access: McpAccess;
}

const FORM_ID = "create-mcp-token";

function Snippet({ label, text, note }: { label: string; text: string; note?: string }) {
  return (
    <div>
      <Typography.Text strong>{label}</Typography.Text>
      <Typography.Paragraph copyable code style={{ marginBottom: 0, wordBreak: "break-all" }}>
        {text}
      </Typography.Paragraph>
      {note && <Typography.Text type="secondary">{note}</Typography.Text>}
    </div>
  );
}

function IssuedStep({ issued, onDone }: { issued: IssuedMcpToken; onDone: () => void }) {
  const snippets = connectSnippets(window.location.origin, issued.token);
  return (
    <Flex vertical gap="middle">
      <Alert type="warning" showIcon title="Copy this token now. Atlas does not show it again." />
      <Snippet label="Claude Code" text={snippets.claudeCode} />
      <div>
        <Typography.Text strong>claude.ai or Claude Desktop</Typography.Text>
        <Typography.Paragraph copyable code style={{ marginBottom: 0, wordBreak: "break-all" }}>
          {snippets.tunnelCommand}
        </Typography.Paragraph>
        <Typography.Paragraph copyable code style={{ marginBottom: 0, wordBreak: "break-all" }}>
          {snippets.tunnelUrl}
        </Typography.Paragraph>
        <Typography.Text type="secondary">
          Replace {"<tunnel-host>"} with the host the tunnel prints.
        </Typography.Text>
      </div>
      <Snippet label="Endpoint on this machine" text={snippets.endpoint} />
      <Flex justify="flex-end">
        <Button type="primary" onClick={onDone}>
          Done
        </Button>
      </Flex>
    </Flex>
  );
}

/**
 * Step 1 asks for a name and an access level; step 2 shows the secret once.
 * The parent mounts this only while it is open, so Done drops the secret
 * (held only in the mutation result) with the component.
 */
export function CreateMcpTokenModal({ onClose }: { onClose: () => void }) {
  const create = useCreateMcpToken();

  const submit = ({ name, access }: Values) => {
    // A second Enter while the request is out must not issue a second token.
    if (create.isPending) return;
    create.mutate({ name, access });
  };

  return (
    <Modal
      title="Create token"
      open
      footer={null}
      onCancel={onClose}
      // The secret must not be dismissed by a stray click outside.
      mask={{ closable: !create.data }}
    >
      {create.data ? (
        <IssuedStep issued={create.data} onDone={onClose} />
      ) : (
        <>
          {create.error && (
            <Alert
              type="error"
              showIcon
              title={create.error.message}
              style={{ marginBottom: 16 }}
            />
          )}
          <Form<Values>
            id={FORM_ID}
            layout="vertical"
            requiredMark={false}
            initialValues={{ access: "read" }}
            onFinish={submit}
          >
            <Form.Item
              label="Name"
              name="name"
              rules={[
                { required: true, whitespace: true, message: "Enter a name" },
                { max: 100, message: "Use at most 100 characters" },
              ]}
            >
              <Input autoComplete="off" autoFocus />
            </Form.Item>
            <Form.Item label="Access" name="access">
              <Radio.Group>
                <Flex vertical gap="small">
                  <Radio value="read">
                    Read
                    <br />
                    <Typography.Text type="secondary">Reads data and runs syncs.</Typography.Text>
                  </Radio>
                  <Radio value="read_write">
                    Read and change settings
                    <br />
                    <Typography.Text type="secondary">
                      Can also change metric rules, the sync schedule, people and codebase mapping.
                    </Typography.Text>
                  </Radio>
                </Flex>
              </Radio.Group>
            </Form.Item>
            <Flex justify="flex-end" gap="small">
              <Button onClick={onClose}>Cancel</Button>
              <Button type="primary" htmlType="submit" loading={create.isPending}>
                Create token
              </Button>
            </Flex>
          </Form>
        </>
      )}
    </Modal>
  );
}
