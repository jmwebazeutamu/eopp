import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { WltCandidate, WltExitReason, WltGroup, WltGroupMembership } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The roster — who is in this group, who has left, and the two moves that
 * change it.
 *
 * The group screen showed a member *count* and nothing else, so twenty women
 * existed in the database with no screen that named them. This is that screen.
 *
 * One rule shapes the whole panel: **a membership is a dated range, never a
 * flag**. A woman who leaves is not removed — her row closes with a date and a
 * reason, and she stays visible below the current roster. Every indicator in
 * the module computes against the roster as it stood on each meeting date, so
 * hiding her would make February's attendance change when she leaves in April.
 * The panel says so in as many words, because "why is she still listed?" is
 * otherwise the first question a facilitator asks.
 */

/** Exit reasons, in the order `wlt.ExitReason` declares them. */
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

  // The tab gate is not the security boundary — `CanAccessGroups` refuses the
  // write regardless. This only stops offering a button that would 403.
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
    // The header count and every readiness condition read the roster, so the
    // whole card is stale the moment a member is added or exits.
    onChanged();
  }, [load, onChanged]);

  return (
    <Card>
      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "baseline",
          justifyContent: "space-between",
        }}
      >
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
        <ul className="stack" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
          {current.map((membership) => (
            <li
              key={membership.id}
              style={{
                display: "flex",
                gap: 12,
                alignItems: "baseline",
                justifyContent: "space-between",
                flexWrap: "wrap",
              }}
            >
              <span>
                <strong>{membership.full_name}</strong>
                <span className="t-meta"> · {t("wlt.joinedOn", { date: membership.joined_on })}</span>
              </span>
              {canWrite && (
                <Button size="sm" onClick={() => setExiting(membership)}>
                  {t("wlt.exitMember")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canWrite && (
        <div style={{ marginTop: 16 }}>
          <Button variant="primary" onClick={() => setAdding(true)}>
            {t("wlt.addMember")}
          </Button>
        </div>
      )}

      {former.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <CapsLabel>{t("wlt.formerMembers")}</CapsLabel>
          <p className="t-meta">{t("wlt.formerMembersBody")}</p>
          <ul className="stack" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
            {former.map((membership) => (
              <li key={membership.id}>
                <span className="t-meta">
                  {membership.full_name} · {t("wlt.leftOn", { date: membership.exited_on ?? "" })} ·{" "}
                  {membership.exit_reason_display}
                </span>
              </li>
            ))}
          </ul>
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
// Adding
// ---------------------------------------------------------------------------

/**
 * The candidate pool, not a free search over the registry.
 *
 * `add_member` refuses an unverified or ineligible woman, and a picker that
 * offers her anyway turns a rule into an error message after the fact. The
 * server applies the same three filters the service does — eligible, verified,
 * not currently in a group — so what is listed is what will be accepted.
 */
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
    // `seated` is in the dependencies so the pool is refetched after an add:
    // the woman just seated must not still be offered.
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

// ---------------------------------------------------------------------------
// Leaving
// ---------------------------------------------------------------------------

/**
 * An exit needs a reason, and the reason is the point.
 *
 * The database can only say "not blank". "Moved away" and "expelled" are
 * opposite programme outcomes, and a group losing members to one is not the
 * same finding as a group losing them to the other. The server refuses a value
 * outside the enum, so this list cannot drift into a free-text field.
 *
 * It can also refuse the exit outright: a woman who owes on a group loan stays
 * a member until it is settled, written off, or transferred (assertion A11).
 * That sentence comes back from the service, so it names the amount.
 */
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
