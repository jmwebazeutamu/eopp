import {
  ApartmentOutlined,
  BellOutlined,
  LogoutOutlined,
  ShareAltOutlined,
  SolutionOutlined,
  TeamOutlined,
  UserSwitchOutlined,
} from "@ant-design/icons";
import { Avatar, Badge, Dropdown, Layout, Menu, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { AlertSummary } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const { Header, Sider, Content } = Layout;

/** How often the alert badge refreshes, in ms. */
const BADGE_POLL_MS = 120_000;

export default function AppLayout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [openAlerts, setOpenAlerts] = useState(0);

  const refreshBadge = useCallback(async () => {
    // The alert endpoints are gated on case access, so a role with none — no
    // longer the system administrator, but still anything the matrix does not
    // cover — would only 403 here. Skip rather than spam the console.
    if (!user || user.access.case_scope === "NONE") return;
    try {
      const response = await api.get<AlertSummary>("/alerts/summary/");
      setOpenAlerts(response.data.assigned_to_me);
    } catch {
      // A badge is not worth surfacing an error for.
    }
  }, [user]);

  useEffect(() => {
    void refreshBadge();
    // Alerts are raised by scheduled jobs rather than by anything the user did,
    // so the count has to be pulled; nothing in this tab will announce it.
    const timer = setInterval(refreshBadge, BADGE_POLL_MS);
    return () => clearInterval(timer);
  }, [refreshBadge, location.pathname]);

  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;

  const isAdmin = user.role === "SYSTEM_ADMIN";

  const navItems = [
    { key: "/cases", icon: <SolutionOutlined />, label: "Cases" },
    // Driven by the matrix rather than by role: the system administrator reads
    // referrals since the 2026-08-16 deviation, but a role the matrix does not
    // cover still gets nothing and would only 403. As with Users below, the API
    // is the authority; hiding the item just avoids a screen that cannot load.
    ...(user.access.referral_scope === "NONE"
      ? []
      : [{ key: "/referrals", icon: <ShareAltOutlined />, label: "Referrals" }]),
    {
      key: "/alerts",
      icon: <BellOutlined />,
      label: (
        <Space>
          Alerts
          {openAlerts > 0 && <Badge count={openAlerts} size="small" />}
        </Space>
      ),
    },
    { key: "/youth", icon: <TeamOutlined />, label: "Youth" },
    { key: "/partners", icon: <ApartmentOutlined />, label: "Partners" },
    // §7 gives user management to the system administrator alone. The API
    // enforces this independently; hiding it just avoids a screen that 403s.
    ...(isAdmin ? [{ key: "/users", icon: <UserSwitchOutlined />, label: "Users" }] : []),
  ];

  const selectedKey = navItems.find((item) => location.pathname.startsWith(item.key))?.key ?? "/cases";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="0" theme="light">
        <div style={{ padding: 16 }}>
          <Typography.Text strong>Youth Employment</Typography.Text>
        </div>
        <Menu mode="inline" selectedKeys={[selectedKey]} onClick={({ key }) => navigate(key)} items={navItems} />
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
                {user.partner_name && <Tag color="blue">{user.partner_name}</Tag>}
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
