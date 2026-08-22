import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

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
import ListPage from "../components/ListPage";
import Paginator from "../components/Paginator";
import UserDetailModal from "../components/UserDetailModal";
import { Button, Card, MutedChip } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

const PAGE_SIZE = 25;

/**
 * Administrator user management — spec §10 Sprint 2.
 *
 * §7 gives user management to the system administrator alone; the API enforces
 * that independently, this only avoids showing a screen that would 403.
 */
export default function UsersPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();

  const [params] = useSearchParams();
  const [viewing, setViewing] = useState<ManagedUser | null>(null);
  const [rows, setRows] = useState<ManagedUser[]>([]);
  const [total, setTotal] = useState(0);
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
        api.get<Paginated<ManagedUser>>("/users/", {
          params: {
            search: params.get("q") || undefined,
            page: Number(params.get("page") ?? 1),
            page_size: PAGE_SIZE,
            role: params.get("role") ?? undefined,
            account_status: params.get("account_status") ?? undefined,
          },
        }),
        api.get<Location[]>("/locations/", { params: { level: "WOREDA" } }),
        api.get<Paginated<Partner>>("/partners/", {
          params: { page_size: 500 },
        }),
      ]);
      setRows(users.data.results);
      setTotal(users.data.count);
      setWoredas(locs.data);
      setPartners(parts.data.results);
    } catch (error) {
      message.error(errorMessage(error, "Could not load users."));
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  if (user?.role !== "SYSTEM_ADMIN") {
    return (
      <div className="page">
        <Card>
          <div className="t-meta">
            User management is limited to system administrators (spec §7).
          </div>
        </Card>
      </div>
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
    const payload = {
      ...values,
      partner: values.role === "PARTNER_STAFF" ? values.partner : null,
    };
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

  return (
    <ListPage
      title={t("users.title")}
      subtitle={`${total} accounts`}
      action={
        <Button variant="primary" onClick={openCreate}>
          {t("users.add")}
        </Button>
      }
      searchPlaceholder={t("users.search")}
      resource="/users"
      empty={{
        when: !loading && rows.length === 0,
        title: t("empty.users"),
        body: t("empty.usersBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">User</th>
                    <th scope="col">Role</th>
                    <th scope="col">Scope</th>
                    <th scope="col">Caseload</th>
                    <th scope="col">Last seen</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.id}
                      onClick={() => setViewing(row)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>
                        <button
                          type="button"
                          className="row-link t-body-strong"
                          onClick={(event) => {
                            event.stopPropagation();
                            setViewing(row);
                          }}
                        >
                          {row.full_name}
                        </button>
                        <div className="t-meta">{row.username}</div>
                      </td>
                      <td>{row.role_display}</td>
                      <td>{userScope(row)}</td>
                      <td className="tabular">
                        {row.role === "CASE_MANAGER" ? row.caseload_count : "—"}
                      </td>
                      <td>{lastSeen(row)}</td>
                      <td>
                        <AccountStatus status={row.account_status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="only-phone">
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {rows.map((row) => (
                /* The record opens read-only; the edit form is a step inside it,
             because that form carries the role and a password field. */
                <Card
                  key={row.id}
                  onClick={() => setViewing(row)}
                  hasOwnKeyboardTarget
                >
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 12,
                      alignItems: "flex-start",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: 200 }}>
                      <button
                        type="button"
                        className="row-link t-body-strong"
                        onClick={(event) => {
                          event.stopPropagation();
                          setViewing(row);
                        }}
                      >
                        {row.full_name}
                      </button>
                      <div className="t-meta">
                        {row.role_display} · {row.username}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          flexWrap: "wrap",
                          gap: 4,
                          marginTop: 6,
                        }}
                      >
                        <MutedChip style={{ fontSize: 12 }}>
                          {userScope(row)}
                        </MutedChip>
                      </div>
                    </div>

                    <div style={{ textAlign: "right" }}>
                      {/* Caseload is the number an administrator acts on — §11's
                    CASELOAD_CEILING is 50, still a placeholder pending sign-off. */}
                      {row.role === "CASE_MANAGER" && (
                        <div className="tabular" style={{ fontWeight: 600 }}>
                          {row.caseload_count} cases
                        </div>
                      )}
                      <div className="t-meta">
                        {/* Presence and the offline queue are Sprint 8 concerns; last
                      sign-in is what this system actually knows today. */}
                        {lastSeen(row)}
                      </div>
                      <div style={{ marginTop: 4 }}>
                        <AccountStatus status={row.account_status} />
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </div>

          <Paginator
            total={total}
            pageSize={PAGE_SIZE}
            label={t("users.title")}
          />

          <UserDetailModal
            user={viewing}
            onClose={() => setViewing(null)}
            onEdit={(user) => {
              setViewing(null);
              openEdit(user);
            }}
          />

          <Modal
            open={creating}
            title={editing ? `Edit ${editing.full_name}` : "New user"}
            onCancel={() => setCreating(false)}
            onOk={() => form.submit()}
            destroyOnHidden
          >
            <Form
              form={form}
              layout="vertical"
              onFinish={submit}
              requiredMark={false}
            >
              <Form.Item
                name="full_name"
                label="Full name"
                rules={[{ required: true }]}
              >
                <Input />
              </Form.Item>
              <Form.Item
                name="username"
                label="Username"
                rules={[{ required: true }]}
              >
                <Input disabled={!!editing} />
              </Form.Item>
              <Form.Item name="work_email" label={t("profile.workEmail")}>
                <Input type="email" autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="personal_email"
                label={t("profile.personalEmail")}
              >
                <Input type="email" autoComplete="off" />
              </Form.Item>
              <Form.Item name="work_phone" label={t("profile.workPhone")}>
                <Input inputMode="tel" autoComplete="off" />
              </Form.Item>
              <Form.Item
                name="personal_phone"
                label={t("profile.personalPhone")}
              >
                <Input inputMode="tel" autoComplete="off" />
              </Form.Item>
              <Form.Item name="role" label="Role" rules={[{ required: true }]}>
                <Select options={ROLE_OPTIONS} />
              </Form.Item>

              {role && WOREDA_SCOPED_ROLES.includes(role) && (
                <Form.Item
                  name="woreda_assignment"
                  label="Woredas"
                  rules={[
                    {
                      required: true,
                      message:
                        "This role is woreda-scoped and needs at least one.",
                    },
                  ]}
                  extra="An account with no woreda would see nothing."
                >
                  <Select
                    mode="multiple"
                    options={woredas.map((w) => ({
                      value: w.name,
                      label: w.full_path,
                    }))}
                  />
                </Form.Item>
              )}

              {role === "PARTNER_STAFF" && (
                <Form.Item
                  name="partner"
                  label="Partner organisation"
                  rules={[
                    {
                      required: true,
                      message:
                        "Partner staff must be linked to an institution.",
                    },
                  ]}
                  extra="Scopes this account to its own institution's referrals."
                >
                  <Select
                    options={partners.map((p) => ({
                      value: p.id,
                      label: `${p.partner_name} (${p.partner_type_display})`,
                    }))}
                  />
                </Form.Item>
              )}

              <Form.Item
                name="password"
                label={
                  editing ? "New password (leave blank to keep)" : "Password"
                }
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
        </>
      )}
    </ListPage>
  );
}

function userScope(user: ManagedUser): string {
  if (user.partner_name) return user.partner_name;
  if (user.woreda_assignment.length) return user.woreda_assignment.join(", ");
  return "All woredas";
}

function lastSeen(user: ManagedUser): string {
  return user.last_login
    ? new Date(user.last_login).toLocaleDateString("en-GB")
    : "Never signed in";
}

function AccountStatus({ status }: { status: ManagedUser["account_status"] }) {
  const active = status === "ACTIVE";
  return (
    <span
      className="chip"
      style={{
        color: active ? "var(--green-ink)" : "var(--terra-700)",
        background: active ? "var(--green-100)" : "var(--terra-100)",
        borderColor: active ? "var(--green-border)" : "var(--terra-border)",
        fontSize: 12,
      }}
    >
      {active ? "Active" : status}
    </span>
  );
}
