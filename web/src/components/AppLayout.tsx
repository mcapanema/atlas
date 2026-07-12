import { Layout, Menu } from "antd";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

const { Sider, Content } = Layout;

export function AppLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [, firstSegment = ""] = location.pathname.split("/");
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider>
        <div style={{ color: "white", padding: 16, fontWeight: 600 }}>Atlas</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[`/${firstSegment}`]}
          items={[
            { key: "/", label: <Link to="/">Executive</Link> },
            { key: "/organizations", label: <Link to="/organizations">Organizations</Link> },
            { key: "/work-items", label: <Link to="/work-items">Work Items</Link> },
            { key: "/teams", label: <Link to="/teams">Teams</Link> },
            { key: "/projects", label: <Link to="/projects">Projects</Link> },
            { key: "/advisor", label: <Link to="/advisor">Advisor</Link> },
            { key: "/connectors", label: <Link to="/connectors">Connectors</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Content style={{ margin: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
