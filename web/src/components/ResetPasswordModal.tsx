import { Alert, App, Form, Input, Modal } from "antd";
import { useState } from "react";

import type { CurrentUser } from "../api/auth";
import { useResetPassword } from "../api/users";

interface Values {
  new_password: string;
  confirm: string;
}

const FORM_ID = "reset-password";
const PASSWORD_HINT = "At least 12 characters";

/** Admin sets a new password for another account; that user's sessions end. */
export function ResetPasswordModal({
  user,
  onClose,
}: {
  user: CurrentUser | null;
  onClose: () => void;
}) {
  const reset = useResetPassword();
  const { message } = App.useApp();
  // The parent clears `user` on close; keep the name for the closing animation.
  const [name, setName] = useState(user?.name ?? "");
  if (user && user.name !== name) setName(user.name);

  const submit = ({ new_password }: Values) => {
    // A second Enter while the request is out must not send a second PUT.
    if (reset.isPending || !user) return;
    reset.mutate(
      { id: user.id, new_password },
      {
        onSuccess: () => {
          void message.success(`Password reset. ${user.name}'s sessions ended.`);
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      title={`Reset password for ${name}`}
      open={user !== null}
      okText="Reset password"
      cancelText="Cancel"
      confirmLoading={reset.isPending}
      okButtonProps={{ htmlType: "submit", form: FORM_ID }}
      // Remount the form on each open, so autoFocus lands and no draft lingers.
      destroyOnHidden
      onCancel={onClose}
      afterClose={() => {
        reset.reset();
      }}
    >
      {reset.error && (
        <Alert type="error" showIcon title={reset.error.message} style={{ marginBottom: 16 }} />
      )}
      <Form<Values> id={FORM_ID} layout="vertical" requiredMark={false} onFinish={submit}>
        <Form.Item
          label="New password"
          name="new_password"
          extra={PASSWORD_HINT}
          rules={[
            { required: true, message: "Enter a new password" },
            { min: 12, message: PASSWORD_HINT },
          ]}
        >
          <Input.Password autoComplete="new-password" autoFocus />
        </Form.Item>
        <Form.Item
          label="Confirm new password"
          name="confirm"
          dependencies={["new_password"]}
          rules={[
            { required: true, message: "Confirm the new password" },
            ({ getFieldValue }) => ({
              validator: (_, value: string | undefined) =>
                !value || getFieldValue("new_password") === value
                  ? Promise.resolve()
                  : Promise.reject(new Error("The passwords don't match")),
            }),
          ]}
        >
          <Input.Password autoComplete="new-password" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
