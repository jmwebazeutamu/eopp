import { PlusOutlined } from "@ant-design/icons";
import { App, Button, Card, Form, Input, Modal, Select, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import {
  ACCOUNT_STATUS_OPTIONS,
  ROLE_OPTIONS,
  WOREDA_SCOPED_ROLES,
  type Location,
  type ManagedUser,
  type Paginated,
  type Partner,
  type Role,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";

/**
 * Administrator user management — spec §10 Sprint 2.
 *
 * §7 gives user management to the system administrator alone; the API enforces
 * that independently, this only avoids showing a screen that would 403.
 */
export default function UsersPage() {
  const { user } = useAuth();
  const { message } = App.useApp();

  const [rows, setRows] = useState<ManagedUser[]>([]);
  const [woredas, setWoredas] = useState<Location[]>([]);
  const [partners, setPartners] = useState<Partner[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<ManagedUser | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<Record<string, unknown>>();

  const role = Form.useWatch("role", form) as Role | undefined;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [users, locs, parts] = await Promise.all([
        api.get<Paginated<ManagedUser>>("/users/"),
        api.get<Location[]>("/locations/", { params: { level: "WOREDA" } }),
        api.get<Paginated<Partner>>("/partners/", { params: { page_size: 500 } }),
      ]);
      setRows(users.data.results);
      setWoredas(locs.data);
      setPartners(parts.data.results);
    } catch (error) {
      message.error(errorMessage(error, "Could not load users."));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  if (user?.role !== "SYSTEM_ADMIN") {
    return (
      <Card>
        <Typography.Text type="secondary">
          User management is limited to system administrators (spec §7).
        </Typography.Text>
      </Card>
    );
  }

  function openCreate() {
    setEditing(null);
    setCreating(true);
    form.resetFields();
    form.setFieldsValue({ account_status: "ACTIVE", woreda_assignment: [] });
  }

  function openEdit(record: ManagedUser) {
    setEditing(record);
    setCreating(true);
    form.setFieldsValue({ ...record, password: undefined });
  }

  async function submit(values: Record<string, unknown>) {
    // The API rejects a partner on a non-partner role and requires one for
    // PARTNER_STAFF; clear the stale value rather than sending a contradiction.
    const payload = { ...values, partner: values.role === "PARTNER_STAFF" ? values.partner : null };
    try {
      if (editing) {
        await api.patch(`/users/${editing.id}/`, payload);
        message.success("User updated.");
      } else {
        await api.post("/users/", payload);
        message.success("User created.");
      }
      setCreating(false);
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not save the user."));
    }
  }

  const columns: ColumnsType<ManagedUser> = [
    { title: "Name", dataIndex: "full_name" },
    { title: "Username", dataIndex: "username", width: 150 },
    { title: "Role", dataIndex: "role_display", width: 260 },
    {
      title: "Scope",
      key: "scope",
      render: (_, row) =>
        row.partner_name ? (
          <Tag color="blue">{row.partner_name}</Tag>
        ) : row.woreda_assignment.length ? (
          row.woreda_assignment.map((w) => <Tag key={w}>{w}</Tag>)
        ) : (
          <Typography.Text type="secondary">All</Typography.Text>
        ),
    },
    {
      title: "Status",
      dataIndex: "account_status",
      width: 120,
      render: (value: string) => <Tag color={value === "ACTIVE" ? "green" : "red"}>{value}</Tag>,
    },
    {
      title: "",
      key: "actions",
      width: 80,
      render: (_, row) => (
        <Button type="link" onClick={() => openEdit(row)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <Card
      title="Users"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New user
        </Button>
      }
    >
      <Table rowKey="id" columns={columns} dataSource={rows} loading={loading} pagination={{ pageSize: 25 }} />

      <Modal
        open={creating}
        title={editing ? `Edit ${editing.full_name}` : "New user"}
        onCancel={() => setCreating(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="full_name" label="Full name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="username" label="Username" rules={[{ required: true }]}>
            <Input disabled={!!editing} />
          </Form.Item>
          <Form.Item name="email" label="Email">
            <Input type="email" />
          </Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>

          {role && WOREDA_SCOPED_ROLES.includes(role) && (
            <Form.Item
              name="woreda_assignment"
              label="Woredas"
              rules={[{ required: true, message: "This role is woreda-scoped and needs at least one." }]}
              extra="An account with no woreda would see nothing."
            >
              <Select mode="multiple" options={woredas.map((w) => ({ value: w.name, label: w.full_path }))} />
            </Form.Item>
          )}

          {role === "PARTNER_STAFF" && (
            <Form.Item
              name="partner"
              label="Partner organisation"
              rules={[{ required: true, message: "Partner staff must be linked to an institution." }]}
              extra="Scopes this account to its own institution's referrals."
            >
              <Select
                options={partners.map((p) => ({ value: p.id, label: `${p.partner_name} (${p.partner_type_display})` }))}
              />
            </Form.Item>
          )}

          <Form.Item
            name="password"
            label={editing ? "New password (leave blank to keep)" : "Password"}
            rules={editing ? [] : [{ required: true, min: 12 }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>

          <Form.Item
            name="account_status"
            label="Account status"
            extra="Accounts are deactivated, never deleted — the audit trail still references them."
          >
            <Select options={ACCOUNT_STATUS_OPTIONS} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
