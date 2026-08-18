import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { App, Button, Card, Form, Input, Typography } from "antd";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { errorMessage } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import LanguageSwitch from "../components/shell/LanguageSwitch";
import { useLang } from "../i18n/LanguageContext";

export default function LoginPage() {
  const { t } = useLang();
  const { user, login } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/cases" replace />;

  async function onFinish(values: { username: string; password: string }) {
    setSubmitting(true);
    try {
      await login(values.username, values.password);
      navigate("/cases", { replace: true });
    } catch (error) {
      // Covers a suspended account too — the backend refuses the token and
      // explains why, rather than issuing one for an account that cannot act.
      message.error(errorMessage(error, "Could not sign in."));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "var(--paper)",
        padding: 24,
      }}
    >
      <Card style={{ width: "100%", maxWidth: 400 }}>
        <Typography.Title level={4} style={{ marginBottom: 4 }}>
          {t("app.name")}
        </Typography.Title>
        <Typography.Paragraph type="secondary">{t("login.subtitle")}</Typography.Paragraph>

        <Form layout="vertical" onFinish={onFinish} requiredMark={false} autoComplete="on">
          <Form.Item name="username" label={t("login.username")} rules={[{ required: true, message: t("login.usernameRequired") }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" size="large" />
          </Form.Item>
          <Form.Item name="password" label={t("login.password")} rules={[{ required: true, message: t("login.passwordRequired") }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" size="large" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={submitting}>
            {t("login.submit")}
          </Button>
        </Form>

        {/* The switch stays on this screen: a first-time user needs to choose a
            language before they have an account menu to find it in. */}
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--line)" }}>
          <LanguageSwitch />
        </div>
      </Card>
    </div>
  );
}
