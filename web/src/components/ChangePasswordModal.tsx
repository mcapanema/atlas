import { Alert, App, Form, Input, Modal } from "antd";

import { useChangePassword } from "../api/auth";

interface Values {
  current_password: string;
  new_password: string;
  confirm: string;
}

const FORM_ID = "change-password";
const PASSWORD_HINT = "At least 12 characters";

/** Lets the signed-in user replace their own password. */
export function ChangePasswordModal({
  open,
  onClose,
  onClosed,
}: {
  open: boolean;
  onClose: () => void;
  /** Runs once the dialog has finished closing, when focus is free to move. */
  onClosed?: () => void;
}) {
  const [form] = Form.useForm<Values>();
  const change = useChangePassword();
  const { message } = App.useApp();

  const submit = ({ current_password, new_password }: Values) => {
    // A second Enter while the request is out must not send a second PUT.
    if (change.isPending) return;
    change.mutate(
      { current_password, new_password },
      {
        onSuccess: () => {
          void message.success("Password changed");
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      title="Change password"
      open={open}
      // The opener (a menu item) is gone by then; onClosed places focus.
      focusTriggerAfterClose={false}
      okText="Change password"
      cancelText="Cancel"
      confirmLoading={change.isPending}
      // A real submit button, so Enter in a field submits the form.
      okButtonProps={{ htmlType: "submit", form: FORM_ID }}
      onCancel={onClose}
      afterClose={() => {
        form.resetFields();
        change.reset();
        onClosed?.();
      }}
    >
      {change.error && (
        <Alert type="error" showIcon title={change.error.message} style={{ marginBottom: 16 }} />
      )}
      <Form<Values>
        id={FORM_ID}
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={submit}
      >
        <Form.Item
          label="Current password"
          name="current_password"
          rules={[{ required: true, message: "Enter your current password" }]}
        >
          <Input.Password autoComplete="current-password" autoFocus />
        </Form.Item>
        <Form.Item
          label="New password"
          name="new_password"
          extra={PASSWORD_HINT}
          rules={[
            { required: true, message: "Enter a new password" },
            { min: 12, message: PASSWORD_HINT },
          ]}
        >
          <Input.Password autoComplete="new-password" />
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
