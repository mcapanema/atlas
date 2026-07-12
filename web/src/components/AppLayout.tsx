import {
  ApartmentOutlined,
  ApiOutlined,
  BulbOutlined,
  FundOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MoonOutlined,
  ProfileOutlined,
  ProjectOutlined,
  SunOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Tooltip } from "antd";
import type { MenuProps } from "antd";
import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

import { useThemeMode } from "../theme/context";

const { Sider, Content } = Layout;

const NAV: MenuProps["items"] = [
  {
    type: "group",
    label: "Overview",
    children: [{ key: "/", icon: <FundOutlined />, label: <Link to="/">Executive</Link> }],
  },
  {
    type: "group",
    label: "Delivery",
    children: [
      { key: "/teams", icon: <TeamOutlined />, label: <Link to="/teams">Teams</Link> },
      { key: "/projects", icon: <ProjectOutlined />, label: <Link to="/projects">Projects</Link> },
      {
        key: "/work-items",
        icon: <ProfileOutlined />,
        label: <Link to="/work-items">Work Items</Link>,
      },
    ],
  },
  {
    type: "group",
    label: "Intelligence",
    children: [
      { key: "/advisor", icon: <BulbOutlined />, label: <Link to="/advisor">Advisor</Link> },
    ],
  },
  {
    type: "group",
    label: "Setup",
    children: [
      {
        key: "/organizations",
        icon: <ApartmentOutlined />,
        label: <Link to="/organizations">Organizations</Link>,
      },
      {
        key: "/connectors",
        icon: <ApiOutlined />,
        label: <Link to="/connectors">Connectors</Link>,
      },
    ],
  },
];

// Route segment → document title, for the seven-tabs-open EM.
const TITLES: Record<string, string> = {
  "": "Executive",
  teams: "Teams",
  projects: "Projects",
  "work-items": "Work Items",
  advisor: "Advisor",
  organizations: "Organizations",
  connectors: "Connectors",
};

// Collapsed to the 64px rail there is no room for group titles (AntD
// truncates them to "Intelligen…"); flatten to icons with dividers.
const NAV_COLLAPSED: MenuProps["items"] = NAV.flatMap((group, index) => {
  const children = group && "children" in group ? (group.children ?? []) : [];
  return index === 0 ? children : [{ type: "divider" as const }, ...children];
});

export function AppLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const { mode, toggle } = useThemeMode();
  const [collapsed, setCollapsed] = useState(false);
  const [, firstSegment = ""] = location.pathname.split("/");
  const dark = mode === "dark";
  useEffect(() => {
    const page = TITLES[firstSegment];
    document.title = page ? `Atlas — ${page}` : "Atlas";
  }, [firstSegment]);
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <Sider
        width={224}
        collapsedWidth={64}
        collapsed={collapsed}
        collapsible
        trigger={null}
        breakpoint="lg"
        onBreakpoint={setCollapsed}
        style={{
          position: "sticky",
          top: 0,
          height: "100vh",
          overflow: "auto",
          borderInlineEnd: "1px solid var(--ant-color-split)",
        }}
      >
        <div className="app-sider-inner">
          <div className="app-sider-header">
            <Link to="/" className="app-wordmark" aria-label="Atlas home">
              {collapsed ? "A" : "Atlas"}
            </Link>
            <Button
              type="text"
              size="small"
              aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((value) => !value)}
            />
          </div>
          <Menu
            mode="inline"
            selectedKeys={[`/${firstSegment}`]}
            items={collapsed ? NAV_COLLAPSED : NAV}
            style={{ flex: 1, background: "transparent", borderInlineEnd: 0 }}
          />
          <div className="app-sider-footer">
            <Tooltip title={dark ? "Switch to light mode" : "Switch to dark mode"}>
              <Button
                type="text"
                block
                aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
                icon={dark ? <SunOutlined /> : <MoonOutlined />}
                onClick={toggle}
              >
                {collapsed ? null : dark ? "Light mode" : "Dark mode"}
              </Button>
            </Tooltip>
          </div>
        </div>
      </Sider>
      <Layout>
        <Content className="app-content" id="main" tabIndex={-1}>
          <div className="app-page">{children}</div>
        </Content>
      </Layout>
    </Layout>
  );
}
