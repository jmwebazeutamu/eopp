import { App, Form, Input, Modal } from "antd";
import { useState } from "react";

import { api, errorMessage, tokens } from "../api/client";
import type { CurrentUser } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import { CapsLabel, Field } from "./ui";

/**
 * A user's own account: the details they may change, and their password.
 *
 * Two forms rather than one, because they submit to different endpoints and
 * fail for different reasons — a rejected password must not discard a name
 * the user has already typed, and a name that clashes must not read as a
 * password problem.
 *
 * What is *not* here is as deliberate as what is. Role, woreda assignment,
 * partner and account status are shown read-only: they are §7's, the
 * administrator sets them, and the server refuses to write them on this route
 * regardless. Showing them makes the boundary legible rather than mysterious.
 */
export default function ProfileModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useLang();
  const { user, setUser } = useAuth();
  const { message } = App.useApp();
  const [detailsForm] = Form.useForm();
  const [passwordForm] = Form.useForm();
  const [savingDetails, setSavingDetails] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  if (!user) return null;

  async function saveDetails(values: Record<string, string | undefined>) {
    setSavingDetails(true);
    try {
      const response = await api.patch<CurrentUser>("/users/me/", values);
      // The server returns the whole /me/ shape, so the rail's name, initials
      // and role update without a reload.
      setUser(response.data);
      message.success(t("profile.saved"));
    } catch (error) {
      message.error(errorMessage(error, t("profile.saveFailed")));
    } finally {
      setSavingDetails(false);
    }
  }

  async function savePassword(values: { current_password: string; new_password: string }) {
    setSavingPassword(true);
    try {
      const { data } = await api.post<{ access: string; refresh: string }>("/users/me/password/", values);
      // The server ends every session issued before the change, including this
      // one. It hands back a fresh pair for the device that did it — storing
      // them is what keeps the user on the screen they just used correctly.
      tokens.set(data.access, data.refresh);
      passwordForm.resetFields();
      message.success(t("profile.passwordChanged"));
    } catch (error) {
      message.error(errorMessage(error, t("profile.passwordFailed")));
    } finally {
      setSavingPassword(false);
    }
  }

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title={t("profile.title")}
      footer={null}
      destroyOnHidden
      width={560}
    >
      <Form
        form={detailsForm}
        layout="vertical"
        requiredMark={false}
        initialValues={{
          full_name: user.full_name,
          work_email: user.work_email,
          personal_email: user.personal_email,
          work_phone: user.work_phone,
          personal_phone: user.personal_phone,
        }}
        onFinish={saveDetails}
      >
        <Form.Item
          name="full_name"
          label={t("profile.fullName")}
          rules={[{ required: true, message: t("profile.nameRequired") }]}
        >
          <Input size="large" autoComplete="name" />
        </Form.Item>
        <div className="grid-pairs">
          <Form.Item
            name="work_email"
            label={t("profile.workEmail")}
            rules={[{ type: "email", message: t("profile.emailInvalid") }]}
          >
            <Input size="large" autoComplete="email" inputMode="email" />
          </Form.Item>
          <Form.Item
            name="personal_email"
            label={t("profile.personalEmail")}
            rules={[{ type: "email", message: t("profile.emailInvalid") }]}
          >
            <Input size="large" autoComplete="email" inputMode="email" />
          </Form.Item>
          <Form.Item name="work_phone" label={t("profile.workPhone")}>
            <Input size="large" autoComplete="tel" inputMode="tel" />
          </Form.Item>
          <Form.Item name="personal_phone" label={t("profile.personalPhone")}>
            <Input size="large" autoComplete="tel" inputMode="tel" />
          </Form.Item>
        </div>
        {/* Every one of these is optional. Field staff are not required to hand
            over a personal number to use the system. */}
        <div className="t-meta" style={{ marginTop: -4, marginBottom: 12 }}>
          {t("profile.contactWhy")}
        </div>
        <button type="submit" className="btn btn--primary" disabled={savingDetails}>
          {t(savingDetails ? "common.saving" : "profile.saveDetails")}
        </button>
      </Form>

      {/* Set by an administrator (§7). Shown so the boundary is legible rather
          than a field that silently refuses to save. */}
      <div className="card__rule" style={{ margin: "20px 0 14px" }} />
      <CapsLabel style={{ marginBottom: 8 }}>{t("profile.managedByAdmin")}</CapsLabel>
      <div className="grid-pairs">
        <Field label={t("users.role")}>{user.role_display}</Field>
        <Field label={t("shell.woreda")}>
          {user.woreda_assignment?.length ? user.woreda_assignment.join(", ") : t("shell.allWoredas")}
        </Field>
        <Field label={t("profile.username")}>{user.username}</Field>
        {user.partner_name && <Field label={t("profile.partner")}>{user.partner_name}</Field>}
      </div>

      <div className="card__rule" style={{ margin: "20px 0 14px" }} />
      <CapsLabel style={{ marginBottom: 8 }}>{t("profile.changePassword")}</CapsLabel>
      <Form form={passwordForm} layout="vertical" requiredMark={false} onFinish={savePassword}>
        <Form.Item
          name="current_password"
          label={t("profile.currentPassword")}
          extra={t("profile.currentPasswordWhy")}
          rules={[{ required: true, message: t("profile.currentPasswordRequired") }]}
        >
          <Input.Password size="large" autoComplete="current-password" />
        </Form.Item>
        <Form.Item
          name="new_password"
          label={t("profile.newPassword")}
          rules={[{ required: true, message: t("profile.newPasswordRequired") }]}
        >
          <Input.Password size="large" autoComplete="new-password" />
        </Form.Item>
        <button type="submit" className="btn btn--primary" disabled={savingPassword}>
          {t(savingPassword ? "common.saving" : "profile.changePassword")}
        </button>
      </Form>
    </Modal>
  );
}
