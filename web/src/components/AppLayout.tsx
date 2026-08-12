import {
  ApartmentOutlined,
  LogoutOutlined,
  SolutionOutlined,
  TeamOutlined,
  UserSwitchOutlined,
} from "@ant-design/icons";
import { Avatar, Dropdown, Layout, Menu, Space, Tag, Typography } from "antd";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const { Header, Sider, Content } = Layout;

export default function AppLayout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const navItems = [
    { key: "/cases", icon: <SolutionOutlined />, label: "Cases" },
    { key: "/youth", icon: <TeamOutlined />, label: "Youth" },
    { key: "/partners", icon: <ApartmentOutlined />, label: "Partners" },
    // §7 gives user management to the system administrator alone. The API
    // enforces this independently; hiding it just avoids a screen that 403s.
    ...(user.role === "SYSTEM_ADMIN"
      ? [{ key: "/users", icon: <UserSwitchOutlined />, label: "Users" }]
      : []),
  ];

  const selectedKey = navItems.find((item) => location.pathname.startsWith(item.key))?.key ?? "/cases";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="0" theme="light">
        <div style={{ padding: 16 }}>
          <Typography.Text strong>Youth Employment</Typography.Text>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          onClick={({ key }) => navigate(key)}
          items={navItems}
        />
      </Sider>

      <Layout>
        <Header
          style={{
            background: "#fff",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            paddingInline: 24,
            borderBottom: "1px solid #f0f0f0",
          }}
        >
          <Dropdown
            menu={{
              items: [{ key: "logout", icon: <LogoutOutlined />, label: "Sign out", onClick: logout }],
            }}
          >
            <Space style={{ cursor: "pointer" }}>
              <Avatar>{user.full_name.charAt(0)}</Avatar>
              <span>
                {user.full_name} <Tag>{user.role_display}</Tag>
              </span>
            </Space>
          </Dropdown>
        </Header>

        <Content style={{ margin: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
