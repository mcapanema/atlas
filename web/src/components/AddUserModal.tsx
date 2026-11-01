import { Alert, Checkbox, Form, Input, Modal } from "antd";

import { newPasswordRules, PASSWORD_HINT } from "../lib/passwordRules";
import { useCreateUser } from "../api/users";

interface Values {
  name: string;
  email: string;
  password: string;
  is_admin?: boolean;
}

const FORM_ID = "add-user";

/** Admin creates an account with a starting password. */
export function AddUserModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const create = useCreateUser();

  const submit = ({ name, email, password, is_admin }: Values) => {
    // A second Enter while the request is out must not send a second POST.
    if (create.isPending) return;
    create.mutate({ email, name, password, is_admin: is_admin ?? false }, { onSuccess: onClose });
  };

  return (
    <Modal
      title="Add user"
      open={open}
      okText="Add user"
      cancelText="Cancel"
      confirmLoading={create.isPending}
      okButtonProps={{ htmlType: "submit", form: FORM_ID }}
      // Remount the form on each open, so autoFocus lands and no draft lingers.
      destroyOnHidden
      onCancel={onClose}
      afterClose={() => {
        create.reset();
      }}
    >
      {create.error && (
        <Alert type="error" showIcon title={create.error.message} style={{ marginBottom: 16 }} />
      )}
      <Form<Values> id={FORM_ID} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item
          label="Name"
          name="name"
          rules={[{ required: true, whitespace: true, message: "Enter a name" }]}
        >
          <Input autoComplete="off" autoFocus />
        </Form.Item>
        <Form.Item
          label="Email"
          name="email"
          normalize={(value?: string) => value?.trim()}
          rules={[{ required: true, message: "Enter an email" }]}
        >
          <Input type="email" autoComplete="off" />
        </Form.Item>
        <Form.Item
          label="Password"
          name="password"
          extra={PASSWORD_HINT}
          rules={newPasswordRules("Enter a password")}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
        <Form.Item name="is_admin" valuePropName="checked">
          <Checkbox>Administrator</Checkbox>
        </Form.Item>
      </Form>
    </Modal>
  );
}
