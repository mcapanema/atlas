import { DownOutlined, KeyOutlined, LogoutOutlined, UserOutlined } from "@ant-design/icons";
import { App, Button, Dropdown } from "antd";
import { useRef, useState } from "react";

import { useAuthStatus, useSignOut } from "../api/auth";
import { ChangePasswordModal } from "./ChangePasswordModal";

/** The signed-in user's menu in the sidebar footer: change password, sign out. */
export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const user = useAuthStatus().data?.user;
  const signOut = useSignOut();
  const { message } = App.useApp();
  const button = useRef<HTMLButtonElement>(null);
  const [changing, setChanging] = useState(false);
  if (!user) return null;
  return (
    <>
      <Dropdown
        trigger={["click"]}
        placement="topLeft"
        menu={{
          items: [
            { key: "password", icon: <KeyOutlined />, label: "Change password" },
            { key: "sign-out", icon: <LogoutOutlined />, label: "Sign out" },
          ],
          onClick: ({ key }) => {
            if (key === "password") setChanging(true);
            else {
              signOut.mutate(undefined, {
                onError: () => void message.error("Couldn't sign out. Try again."),
              });
            }
          },
        }}
      >
        <Button
          ref={button}
          type="text"
          block
          aria-label={`Account: ${user.name}`}
          icon={<UserOutlined />}
          style={collapsed ? undefined : { display: "flex", alignItems: "center" }}
        >
          {collapsed ? null : (
            <>
              <span className="app-account-name">{user.name}</span>
              <DownOutlined />
            </>
          )}
        </Button>
      </Dropdown>
      <ChangePasswordModal
        open={changing}
        onClose={() => setChanging(false)}
        // Focus can only move once the dialog's focus trap has let go.
        onClosed={() => button.current?.focus()}
      />
    </>
  );
}
