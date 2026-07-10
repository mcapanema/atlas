import { Layout, Menu } from "antd";
import type { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";

const { Header, Sider, Content } = Layout;

export function AppLayout({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider>
        <div style={{ color: "white", padding: 16, fontWeight: 600 }}>Atlas</div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={[
            { key: "/organizations", label: <Link to="/organizations">Organizations</Link> },
            { key: "/connectors", label: <Link to="/connectors">Connectors</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: "#fff" }} />
        <Content style={{ margin: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  );
}
