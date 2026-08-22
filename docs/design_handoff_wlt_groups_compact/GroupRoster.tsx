import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { WltCandidate, WltExitReason, WltGroup, WltGroupMembership } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The roster — compact layout.
 *
 * Same rule as before: a membership is a dated range, never a flag, so an
 * exited member's row closes with a date and reason and stays visible below
 * the current roster rather than disappearing.
 *
 * What changed: the current roster was a `<ul>` of flex rows, each wrapping
 * name / joined-date / exit-button independently — roughly 40-48px per row
 * once two lines were forced on a narrow card. It's a `<table>` now: name,
 * joined date, and an officer tag or exit action in fixed columns, one line
 * each. `AddMemberModal` / `ExitMemberModal` and the API calls are unchanged.
 */

const EXIT_REASONS: Exclude<WltExitReason, "">[] = [
  "MOVED",
  "MARRIED_OUT",
  "DIED",
  "WITHDREW",
  "EXPELLED",
  "PSNP_EXIT",
  "GROUP_SPLIT",
];

export default function GroupRoster({ group, onChanged }: { group: WltGroup; onChanged: () => void }) {
  const { message } = App.useApp();
  const { t } = useLang();
  const { user } = useAuth();

  const [roster, setRoster] = useState<WltGroupMembership[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [exiting, setExiting] = useState<WltGroupMembership | null>(null);

  const canWrite = Boolean(user?.access.group_write);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<WltGroupMembership[]>(`/wlt/groups/${group.id}/members/`);
      setRoster(response.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.rosterLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [group.id, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const current = useMemo(() => roster.filter((row) => row.exited_on === null), [roster]);
  const former = useMemo(() => roster.filter((row) => row.exited_on !== null), [roster]);

  const refresh = useCallback(() => {
    void load();
    onChanged();
  }, [load, onChanged]);

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{t("wlt.roster")}</CapsLabel>
        <span className="t-meta">{t("wlt.rosterCount", { count: current.length })}</span>
      </div>

      {loading && roster.length === 0 && <p className="t-meta">{t("common.loading")}</p>}

      {!loading && current.length === 0 && (
        <>
          <p style={{ marginTop: 8 }}>{t("wlt.rosterEmpty")}</p>
          <p className="t-meta">{t("wlt.rosterEmptyBody")}</p>
        </>
      )}

      {current.length > 0 && (
        <table className="roster-table">
          <tbody>
            {current.map((membership) => (
              <tr key={membership.id}>
                <td style={{ fontWeight: 600 }}>{membership.full_name}</td>
                <td className="t-meta">{t("wlt.joinedOn", { date: membership.joined_on })}</td>
                <td style={{ textAlign: "right" }}>
                  {canWrite && (
                    <Button size="sm" onClick={() => setExiting(membership)}>
                      {t("wlt.exitMember")}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canWrite && (
        <div style={{ marginTop: 12 }}>
          <Button variant="primary" onClick={() => setAdding(true)}>
            {t("wlt.addMember")}
          </Button>
        </div>
      )}

      {former.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <CapsLabel>{t("wlt.formerMembers")}</CapsLabel>
          <p className="t-meta">{t("wlt.formerMembersBody")}</p>
          <table className="roster-table">
            <tbody>
              {former.map((membership) => (
                <tr key={membership.id}>
                  <td className="t-meta" colSpan={3}>
                    {membership.full_name} · {t("wlt.leftOn", { date: membership.exited_on ?? "" })} ·{" "}
                    {membership.exit_reason_display}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <AddMemberModal
        group={group}
        open={adding}
        onClose={() => setAdding(false)}
        onDone={refresh}
        seated={current.length}
      />
      <ExitMemberModal group={group} membership={exiting} onClose={() => setExiting(null)} onDone={refresh} />
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Adding / leaving — unchanged from the source page
// ---------------------------------------------------------------------------

function AddMemberModal({
  group,
  open,
  onClose,
  onDone,
  seated,
}: {
  group: WltGroup;
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  seated: number;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [form] = Form.useForm<{ person: string }>();

  const [candidates, setCandidates] = useState<WltCandidate[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await api.get<WltCandidate[]>("/wlt/profiles/candidates/", {
          params: { kebele: group.kebele },
        });
        if (!cancelled) setCandidates(response.data);
      } catch (error) {
        if (!cancelled) message.error(errorMessage(error, t("wlt.candidatesLoadFailed")));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, group.kebele, seated, message, t]);

  const submit = async (values: { person: string }) => {
    setSubmitting(true);
    try {
      const created = await api.post<{ full_name: string }>(`/wlt/groups/${group.id}/members/`, {
        person: values.person,
      });
      message.success(t("wlt.addMemberDone", { name: created.data.full_name }));
      form.resetFields();
      onDone();
      onClose();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.addMemberFailed")));
    } finally {
      setSubmitting(false);
    }
  };

  const empty = !loading && candidates.length === 0;

  return (
    <Modal
      open={open}
      title={t("wlt.addMemberTitle")}
      okText={t("wlt.addMemberOk")}
      okButtonProps={{ disabled: empty }}
      cancelText={t("common.cancel")}
      confirmLoading={submitting}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      {empty ? (
        <>
          <p>{t("wlt.candidatesEmpty")}</p>
          <p className="t-meta">{t("wlt.candidatesEmptyBody")}</p>
        </>
      ) : (
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item
            name="person"
            label={t("wlt.addMemberField")}
            rules={[{ required: true, message: t("wlt.addMemberRequired") }]}
          >
            <Select
              showSearch
              loading={loading}
              placeholder={t("wlt.addMemberPlaceholder")}
              optionFilterProp="label"
              options={candidates.map((candidate) => ({
                value: candidate.person,
                label: candidate.full_name,
              }))}
            />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}

function ExitMemberModal({
  group,
  membership,
  onClose,
  onDone,
}: {
  group: WltGroup;
  membership: WltGroupMembership | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [form] = Form.useForm<{ reason: WltExitReason; note?: string }>();
  const [submitting, setSubmitting] = useState(false);

  const submit = async (values: { reason: WltExitReason; note?: string }) => {
    if (!membership) return;
    setSubmitting(true);
    try {
      await api.post(`/wlt/groups/${group.id}/members/${membership.id}/exit/`, {
        reason: values.reason,
        note: values.note ?? "",
      });
      message.success(t("wlt.exitMemberDone", { name: membership.full_name }));
      form.resetFields();
      onDone();
      onClose();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.exitMemberFailed")));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={membership !== null}
      title={t("wlt.exitMemberTitle", { name: membership?.full_name ?? "" })}
      okText={t("wlt.exitMemberOk")}
      cancelText={t("common.cancel")}
      confirmLoading={submitting}
      onCancel={() => {
        form.resetFields();
        onClose();
      }}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <p className="t-meta" style={{ marginBottom: 16 }}>
        {t("wlt.exitKeepsHistory")}
      </p>
      <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
        <Form.Item
          name="reason"
          label={t("wlt.exitReason")}
          rules={[{ required: true, message: t("wlt.exitReasonRequired") }]}
        >
          <Select
            options={EXIT_REASONS.map((reason) => ({
              value: reason,
              label: t(`wlt.exitReason${reason}`),
            }))}
          />
        </Form.Item>
        <Form.Item name="note" label={t("wlt.exitNote")}>
          <Input.TextArea rows={3} placeholder={t("wlt.exitNotePlaceholder")} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
