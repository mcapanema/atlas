import { Alert, Button, Form, Input, Layout, Typography } from "antd";
import { useEffect } from "react";

import { useSetup, useSignIn } from "../api/auth";
import { PASSWORD_HINT, passwordLengthRules } from "../lib/passwordRules";

interface Credentials {
  email: string;
  name?: string;
  password: string;
}

const SETUP_HINT =
  "This account becomes the administrator. Add the rest of the team from Setup → Users.";

/** Full-page sign-in; the first-run account setup while no user exists. */
export function SignInPage({ setupRequired }: { setupRequired: boolean }) {
  const signIn = useSignIn();
  const setup = useSetup();
  const heading = setupRequired ? "Create the first account" : "Sign in";
  const error = (setupRequired ? setup : signIn).error;
  const pending = signIn.isPending || setup.isPending;

  useEffect(() => {
    document.title = `Atlas — ${heading}`;
  }, [heading]);

  const submit = ({ email, name, password }: Credentials) => {
    if (setupRequired) setup.mutate({ email, name: name ?? "", password });
    else signIn.mutate({ email, password });
  };

  // Layout carries AntD's css-var scope, so the --ant-* variables in
  // index.css resolve here as they do under AppLayout.
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <main className="auth-page">
        <div className="app-wordmark">Atlas</div>
        <Typography.Title level={3}>{heading}</Typography.Title>
        {setupRequired && (
          <Typography.Paragraph type="secondary">{SETUP_HINT}</Typography.Paragraph>
        )}
        {error && (
          <Alert type="error" showIcon title={error.message} className="auth-page__error" />
        )}
        <Form<Credentials> layout="vertical" requiredMark={false} onFinish={submit}>
          <Form.Item
            label="Email"
            name="email"
            // Trim before validating: " Ana@Acme.com " is valid (the server
            // normalizes case), but the email rule would reject the spaces.
            normalize={(value?: string) => value?.trim()}
            rules={[
              { required: true, message: "Enter your email address" },
              { type: "email", message: "Enter a valid email address" },
            ]}
          >
            <Input autoComplete="username" autoFocus />
          </Form.Item>
          {setupRequired && (
            <Form.Item
              label="Name"
              name="name"
              rules={[{ required: true, whitespace: true, message: "Enter your name" }]}
            >
              <Input autoComplete="name" />
            </Form.Item>
          )}
          <PasswordField setupRequired={setupRequired} />
          <Button type="primary" htmlType="submit" block loading={pending}>
            {setupRequired ? "Create account" : "Sign in"}
          </Button>
        </Form>
      </main>
    </Layout>
  );
}

function PasswordField({ setupRequired }: { setupRequired: boolean }) {
  return (
    <Form.Item
      label="Password"
      name="password"
      extra={setupRequired ? PASSWORD_HINT : undefined}
      rules={[
        { required: true, message: "Enter your password" },
        ...(setupRequired ? passwordLengthRules : []),
      ]}
    >
      <Input.Password autoComplete={setupRequired ? "new-password" : "current-password"} />
    </Form.Item>
  );
}
