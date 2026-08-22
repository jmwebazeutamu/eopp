import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage, formErrors } from "../../api/client";
import type {
  WltCandidate,
  WltCandidatePool,
  WltExitReason,
  WltGroup,
  WltGroupMembership,
  WltOfficeHolder,
  WltOfficeRole,
} from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import RegisterWomanModal from "./RegisterWomanModal";

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
  const navigate = useNavigate();

  const [roster, setRoster] = useState<WltGroupMembership[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [exiting, setExiting] = useState<WltGroupMembership | null>(null);
  const [officers, setOfficers] = useState<WltOfficeHolder[]>([]);
  const [editing, setEditing] = useState(false);
  const [registering, setRegistering] = useState(false);

  // The tab gate is not the security boundary — `CanAccessGroups` refuses the
  // write regardless. This only stops offering a button that would 403.
  const canWrite = Boolean(user?.access.group_write);
  const onOpenMember = (profileId: string) => navigate(`/wlt/beneficiaries/${profileId}`);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [members, holders] = await Promise.all([
        api.get<WltGroupMembership[]>(`/wlt/groups/${group.id}/members/`),
        api.get<WltOfficeHolder[]>(`/wlt/groups/${group.id}/officers/`),
      ]);
      setRoster(members.data);
      setOfficers(holders.data);
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
    <Card className="card--tight">
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

      {/* Twenty women, each wrapping onto two lines, was this screen's largest
          block. In fixed columns each is one line. The table is laptop-only:
          780px is the structural switch, and three columns at 360px is exactly
          the density the handoff asks about — so below it the rows stay cards,
          as they do on every other list screen. */}
      {current.length > 0 && (
        <>
          <div className="only-laptop">
            <table className="roster-table">
              <tbody>
                {current.map((membership) => (
                  <tr key={membership.id}>
                    <td style={{ fontWeight: 600 }}>
                      <MemberName membership={membership} onOpen={onOpenMember} />
                    </td>
                    <td className="t-meta">{t("wlt.joinedOn", { date: membership.joined_on })}</td>
                    <td style={{ textAlign: "right" }}>
                      <OfficeTag role={officeOf(officers, membership.person)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="stack only-phone" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
            {current.map((membership) => (
              // The exit button wraps to its own line at 360px, which put it
              // directly above the *next* woman's name and read as hers. The
              // separator is what the table gets from `.roster-table td`, and
              // it is what makes each row one unit here.
              <li
                key={membership.id}
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  paddingBottom: 8,
                  borderBottom: "1px solid var(--line-soft)",
                }}
              >
                <span>
                  <strong>
                    <MemberName membership={membership} onOpen={onOpenMember} />
                  </strong>
                  <span className="t-meta"> · {t("wlt.joinedOn", { date: membership.joined_on })}</span>
                </span>
                <OfficeTag role={officeOf(officers, membership.person)} />
              </li>
            ))}
          </ul>
        </>
      )}

      {canWrite && (
        <div style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <Button variant="primary" onClick={() => setAdding(true)}>
            {t("wlt.addMember")}
          </Button>
          <Button onClick={() => setRegistering(true)}>Register and add</Button>
          {/* One entry point rather than a button on every row. Removing a
              woman and electing an officer are the same kind of act — changing
              who is in the group and what they do in it — and twenty exit
              buttons made the roster read as a list of things to undo. */}
          <Button onClick={() => setEditing(true)}>{t("wlt.editMembers")}</Button>
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

      <EditMembersModal
        group={group}
        open={editing}
        members={current}
        officers={officers}
        onClose={() => setEditing(false)}
        onExit={(membership) => setExiting(membership)}
        onChanged={load}
      />

      <AddMemberModal
        group={group}
        open={adding}
        onClose={() => setAdding(false)}
        onDone={refresh}
        seated={current.length}
      />
      <ExitMemberModal group={group} membership={exiting} onClose={() => setExiting(null)} onDone={refresh} />
      <RegisterWomanModal open={registering} initialKebele={group.kebele} onClose={() => setRegistering(false)} onDone={() => undefined} onCreated={({ profileId, personId }) => {
        void (async () => {
          try {
            if (user?.role === "SYSTEM_ADMIN") await api.post(`/wlt/profiles/${profileId}/verify/`, { approved: true, reason: "Verified during group registration." });
            await api.post(`/wlt/groups/${group.id}/members/`, { person: personId });
            message.success("The woman was registered and added to this group.");
            setRegistering(false); refresh();
          } catch (error) {
            message.warning(errorMessage(error, "She was registered and is awaiting verification before she can join."));
            setRegistering(false); navigate(`/wlt/beneficiaries?search=${personId}`);
          }
        })();
      }} />
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
/** The three offices, in the order the handbook lists them. */
const OFFICES: WltOfficeRole[] = ["CHAIR", "SECRETARY", "TREASURER"];

/** Which office this woman currently holds, if any. */
function officeOf(officers: WltOfficeHolder[], personId: string): WltOfficeRole | null {
  const held = officers.find((row) => row.person === personId && row.to_date === null);
  return held ? held.role : null;
}

/**
 * The officer tag beside a name.
 *
 * Green fill with ink text, not a status colour: an office is a fact about a
 * member, not a state she is in, and giving it a status tone would compete
 * with the group's own chip at the top of the screen.
 */
function OfficeTag({ role }: { role: WltOfficeRole | null }) {
  const { t } = useLang();
  if (!role) return null;
  return <span className="officer-tag">{t(`wlt.office${role}`)}</span>;
}

/**
 * Editing who is in the group and what they do in it.
 *
 * Replaces a "record that she left" button on every roster row. Twenty exit
 * buttons made the roster read as a list of things to undo, and the roster is
 * mostly read rather than edited — the names, and now the offices, are what a
 * facilitator checks against the paper register.
 *
 * The exit still runs through `ExitMemberModal`, unchanged: the reason is
 * mandatory, and a woman with an outstanding loan is refused. This screen only
 * moves where it is launched from.
 */
function EditMembersModal({
  group,
  open,
  members,
  officers,
  onClose,
  onExit,
  onChanged,
}: {
  group: WltGroup;
  open: boolean;
  members: WltGroupMembership[];
  officers: WltOfficeHolder[];
  onClose: () => void;
  onExit: (membership: WltGroupMembership) => void;
  onChanged: () => void;
}) {
  const { message } = App.useApp();
  const { t } = useLang();
  const [saving, setSaving] = useState<string | null>(null);

  const vacant = OFFICES.filter((role) => !officers.some((row) => row.role === role && row.to_date === null));

  async function elect(membership: WltGroupMembership, role: WltOfficeRole) {
    setSaving(membership.id);
    try {
      await api.post(`/wlt/groups/${group.id}/officers/`, { person: membership.person, role });
      message.success(t("wlt.electDone", { name: membership.full_name, office: t(`wlt.office${role}`) }));
      onChanged();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.electFailed")));
    } finally {
      setSaving(null);
    }
  }

  return (
    <Modal
      open={open}
      title={t("wlt.editMembersTitle")}
      onCancel={onClose}
      onOk={onClose}
      okText={t("wlt.done")}
      cancelButtonProps={{ style: { display: "none" } }}
      width={620}
      destroyOnHidden
    >
      <p className="t-meta">{t("wlt.editMembersHelp")}</p>
      {vacant.length > 0 && (
        <p className="t-meta">
          {t("wlt.vacantOffices", { offices: vacant.map((role) => t(`wlt.office${role}`)).join(", ") })}
        </p>
      )}

      <table className="roster-table">
        <tbody>
          {members.map((membership) => {
            const role = officeOf(officers, membership.person);
            return (
              <tr key={membership.id}>
                <td style={{ fontWeight: 600 }}>{membership.full_name}</td>
                <td>
                  {/* A select rather than three buttons: the three offices are
                      mutually exclusive for one woman, and "no office" has to
                      be visible as her current state. Clearing it is not
                      offered — an office is vacated by electing somebody else,
                      which is what closes the sitting term. */}
                  <Select
                    size="small"
                    style={{ width: 150 }}
                    value={role ?? ""}
                    loading={saving === membership.id}
                    onChange={(next) => void elect(membership, next as WltOfficeRole)}
                    options={[
                      { value: "", label: t("wlt.officeNone"), disabled: true },
                      ...OFFICES.map((office) => ({ value: office, label: t(`wlt.office${office}`) })),
                    ]}
                  />
                </td>
                <td style={{ textAlign: "right" }}>
                  <Button size="sm" onClick={() => onExit(membership)}>
                    {t("wlt.exitMember")}
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Modal>
  );
}

/**
 * A member's name, which opens her record.
 *
 * A link only when there is somewhere to go. A membership written before
 * `add_member` required a profile carries none, and a name that looks like a
 * link and does nothing is worse than plain text — so those stay plain.
 */
function MemberName({
  membership,
  onOpen,
}: {
  membership: WltGroupMembership;
  onOpen: (profileId: string) => void;
}) {
  if (!membership.profile) return <>{membership.full_name}</>;
  return (
    <button
      type="button"
      className="row-link"
      onClick={(event) => {
        event.stopPropagation();
        onOpen(membership.profile as string);
      }}
    >
      {membership.full_name}
    </button>
  );
}

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
  const [form] = Form.useForm<{ people: string[] }>();

  const [candidates, setCandidates] = useState<WltCandidate[]>([]);
  // Eligible women this group cannot recruit, because they live elsewhere.
  const [elsewhere, setElsewhere] = useState(0);
  const [registeredHere, setRegisteredHere] = useState(0);
  const [alreadyGroupedHere, setAlreadyGroupedHere] = useState(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    void (async () => {
      try {
        const response = await api.get<WltCandidatePool>("/wlt/profiles/candidates/", {
          params: { kebele: group.kebele },
        });
        if (cancelled) return;
        setCandidates(response.data.results);
        setElsewhere(response.data.waiting_elsewhere);
        setRegisteredHere(response.data.registered_here ?? 0);
        setAlreadyGroupedHere(response.data.already_grouped_here ?? 0);
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

  const submit = async (values: { people: string[] }) => {
    setSubmitting(true);
    try {
      await api.post(`/wlt/groups/${group.id}/members/`, { people: values.people });
      message.success(`${values.people.length} ${values.people.length === 1 ? "woman was" : "women were"} added to the group.`);
      form.resetFields();
      onDone();
      onClose();
    } catch (error) {
      const fields = formErrors(error);
      if (fields.length) form.setFields(fields as Parameters<typeof form.setFields>[0]);
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
          <p>{t("wlt.candidatesEmpty", { kebele: group.kebele_name })}</p>
          <p>{registeredHere} {registeredHere === 1 ? "woman is" : "women are"} registered there; {alreadyGroupedHere} already {alreadyGroupedHere === 1 ? "belongs" : "belong"} to a group.</p>
          {elsewhere > 0 && (
            <p>
              {t(elsewhere === 1 ? "wlt.candidatesElsewhere" : "wlt.candidatesElsewherePlural", {
                count: elsewhere,
              })}
            </p>
          )}
          <p className="t-meta">{t("wlt.candidatesEmptyBody")}</p>
          <Button onClick={() => { onClose(); window.location.href = `/wlt/beneficiaries?kebele=${group.kebele}`; }}>View this kebele in the WLT register</Button>
        </>
      ) : (
        <Form form={form} layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item
            name="people"
            label={t("wlt.addMemberField")}
            rules={[{ required: true, message: t("wlt.addMemberRequired") }]}
          >
            <Select
              mode="multiple"
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
