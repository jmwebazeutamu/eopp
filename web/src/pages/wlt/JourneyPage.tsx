import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Journey, JourneyStage, JourneyStageState, LinkageStatus, Paginated, WltGroup, WltGroupStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card, PageHeader } from "../../components/ui";
import { LINKAGE_TONE, STAGE_TONE, WLT_GROUP_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import DraftGroupModal from "./DraftGroupModal";

/**
 * One woman's path: registered → verified → in a group → linked.
 *
 * The four stages existed only as services that refuse things. A facilitator
 * found out that a woman was ineligible at the moment she tried to seat her,
 * and was told *that* she was refused rather than which of the conditions was
 * the problem. This is the same set of refusals, read forwards.
 *
 * It follows the readiness card's rule exactly, because it is the same kind of
 * screen and a facilitator should not have to learn it twice: **the actual
 * value always sits next to the threshold**. "ELS grant received: No (need
 * Yes)" tells her what to collect on the next visit.
 *
 * Four states per stage rather than two. `waiting` is not `blocked` — one is a
 * woreda officer's decision and the other is hers — and only `ready` carries a
 * button. A screen that offered a facilitator a button for somebody else's
 * decision would be lying about who is accountable.
 */
export default function JourneyPage() {
  const { profileId } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [journey, setJourney] = useState<Journey | null>(null);
  const [loading, setLoading] = useState(true);
  const [verificationDecision, setVerificationDecision] = useState<boolean | null>(null);
  const [verificationReason, setVerificationReason] = useState("");
  const [savingVerification, setSavingVerification] = useState(false);
  const [addToGroup, setAddToGroup] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Journey>(`/wlt/profiles/${profileId}/journey/`);
      setJourney(response.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.journeyLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [profileId, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !journey) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!journey) return null;

  const next = journey.next_action;
  const verification = journey.stages.find((stage) => stage.code === "VERIFIED");
  const grouped = journey.stages.find((stage) => stage.code === "GROUPED");
  const canVerify = ["WLT_WOREDA_OFFICER", "WLT_REGION_OFFICER", "WLT_FEDERAL_OFFICER", "SYSTEM_ADMIN"].includes(
    user?.role ?? "",
  );

  async function submitVerification() {
    if (verificationDecision === null) return;
    if (!verificationDecision && !verificationReason.trim()) {
      message.error(t("wlt.verificationReasonRequired"));
      return;
    }
    setSavingVerification(true);
    try {
      await api.post(`/wlt/profiles/${profileId}/verify/`, {
        approved: verificationDecision,
        reason: verificationReason.trim(),
      });
      message.success(t(verificationDecision ? "wlt.verificationApproved" : "wlt.verificationRefused"));
      setVerificationDecision(null);
      setVerificationReason("");
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.verificationSaveFailed")));
    } finally {
      setSavingVerification(false);
    }
  }

  return (
    <div className="page stack">
      <PageHeader
        title={journey.full_name}
        subtitle={
          <span>
            {t("wlt.journeyTitle")} ·{" "}
            {t("wlt.journeyProgress", { done: journey.stages_done, total: journey.stages_total })}
          </span>
        }
      />

      <Card>
        <CapsLabel>{t("wlt.journeyTitle")}</CapsLabel>
        <p style={{ margin: "8px 0 16px" }}>
          {next ? t("wlt.journeyNext", { stage: next.label }) : t("wlt.journeyComplete")}
        </p>
        <JourneySequence stages={journey.stages} />
        {canVerify && verification?.state === "waiting" && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}>
            <Button variant="primary" onClick={() => setVerificationDecision(true)}>
              {t("wlt.verifyRegistration")}
            </Button>
            <Button variant="destructive-soft" onClick={() => setVerificationDecision(false)}>
              {t("wlt.refuseRegistration")}
            </Button>
          </div>
        )}
      </Card>

      {/* Above the stage list, because it is the answer to the question the
          register sends a facilitator here with: which group is she in, and is
          that group all right? The stages below explain how she got there. */}
      {grouped && <GroupCard stage={grouped} onNavigate={navigate} />}

      {journey.stages.map((stage) => (
        <StageCard key={stage.code} stage={stage} onNavigate={navigate} onAddToGroup={() => setAddToGroup(true)} />
      ))}

      <AddToGroupModal
        open={addToGroup}
        person={journey.person}
        stage={grouped}
        onClose={() => setAddToGroup(false)}
        onDone={() => { setAddToGroup(false); void load(); }}
      />

      <Modal
        open={verificationDecision !== null}
        title={t(verificationDecision ? "wlt.verifyRegistration" : "wlt.refuseRegistration")}
        okText={t(verificationDecision ? "wlt.confirmVerification" : "wlt.confirmRefusal")}
        cancelText={t("common.cancel")}
        confirmLoading={savingVerification}
        onOk={() => void submitVerification()}
        onCancel={() => {
          setVerificationDecision(null);
          setVerificationReason("");
        }}
      >
        <p className="t-meta">
          {t(verificationDecision ? "wlt.verifyRegistrationHelp" : "wlt.refuseRegistrationHelp")}
        </p>
        <label>
          <span className="t-caps">{t("wlt.verificationNote")}</span>
          <Input.TextArea
            rows={3}
            value={verificationReason}
            onChange={(event) => setVerificationReason(event.target.value)}
            placeholder={t(verificationDecision ? "wlt.verificationNoteOptional" : "wlt.verificationReasonPlaceholder")}
          />
        </label>
      </Modal>
    </div>
  );
}

function JourneySequence({ stages }: { stages: JourneyStage[] }) {
  const { t } = useLang();
  return (
    <ol aria-label={t("wlt.journeySequence")} style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {stages.map((stage, index) => {
        const tone = STAGE_TONE[stage.state];
        return (
          <li key={stage.code} style={{ display: "grid", gridTemplateColumns: "28px 1fr", gap: 10, minHeight: 54 }}>
            <div aria-hidden style={{ position: "relative" }}>
              <span style={{ display: "grid", placeItems: "center", width: 24, height: 24, borderRadius: 24, color: tone.fg, background: tone.bg, border: `1px solid ${tone.bd}`, fontWeight: 700 }}>
                {stage.state === "done" ? "✓" : tone.mark}
              </span>
              {index < stages.length - 1 && <span style={{ position: "absolute", top: 25, bottom: 0, left: 11, borderLeft: "2px solid var(--border)" }} />}
            </div>
            <div style={{ paddingBottom: 14 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap" }}>
                <strong>{stage.label}</strong>
                <span style={{ color: tone.fg, fontSize: 12, fontWeight: 700 }}>{t(STATE_LABEL[stage.state])}</span>
              </div>
              {stage.conditions.length > 0 && (
                <div className="t-meta">
                  {stage.conditions.filter((condition) => condition.met).length} of {stage.conditions.length} checks complete
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** Written out rather than derived from the state name: a template-literal key
 *  cannot be checked against the string table, which is the whole point of it. */
const STATE_LABEL = {
  done: "wlt.stateDone",
  ready: "wlt.stateReady",
  waiting: "wlt.stateWaiting",
  blocked: "wlt.stateBlocked",
} as const satisfies Record<JourneyStageState, string>;

/**
 * Her group, on her own page.
 *
 * The register lands here, and the journey stage below carried only a name —
 * so a facilitator had to open the group screen to learn whether that group was
 * even operating. Status, phase, place and size are what she is actually
 * checking, so they belong on the row she is already looking at.
 *
 * Drawn from the GROUPED stage's detail rather than a second fetch: the journey
 * is computed on request, so this cannot disagree with the stage beneath it.
 */
function GroupCard({ stage, onNavigate }: { stage: JourneyStage; onNavigate: (to: string) => void }) {
  const { t } = useLang();
  const detail = stage.detail as Record<string, unknown>;
  const groupId = detail.group as string | undefined;

  if (!groupId) {
    return (
      <Card>
        <CapsLabel>{t("wlt.herGroup")}</CapsLabel>
        <p className="t-meta" style={{ margin: "8px 0 0" }}>
          {t("wlt.notInAGroupYet")}
        </p>
      </Card>
    );
  }

  const status = detail.group_status as WltGroupStatus;
  const tone = WLT_GROUP_TONE[status];
  const rows: Array<[string, string]> = [
    [t("wlt.groupKebeleLabel"), String(detail.kebele_name ?? "—")],
    [t("wlt.groupPhaseLabel"), String(detail.group_phase_display || t("wlt.noPhaseYet"))],
    [t("wlt.groupMembersLabel"), String(detail.members_current ?? "—")],
    [t("wlt.groupFacilitatorLabel"), String(detail.facilitator_name ?? "—")],
    [t("wlt.groupJoinedLabel"), String(detail.joined_on ?? "—")],
  ];

  return (
    <Card>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{t("wlt.herGroup")}</CapsLabel>
        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
          <span className="chip__mark" aria-hidden>
            {tone.mark}
          </span>
          {String(detail.group_status_display ?? "")}
        </span>
      </div>

      <p style={{ margin: "8px 0 12px", fontWeight: 600 }}>{String(detail.group_name ?? "")}</p>

      <dl
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
          gap: 12,
          margin: 0,
        }}
      >
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="t-meta" style={{ margin: 0 }}>
              {label}
            </dt>
            <dd style={{ margin: 0 }}>{value}</dd>
          </div>
        ))}
      </dl>

      <div style={{ marginTop: 12 }}>
        <Button size="sm" onClick={() => onNavigate(`/wlt/groups/${groupId}`)}>
          {t("wlt.goToGroup")}
        </Button>
      </div>
    </Card>
  );
}

function StageCard({ stage, onNavigate, onAddToGroup }: { stage: JourneyStage; onNavigate: (to: string) => void; onAddToGroup: () => void }) {
  const { t } = useLang();
  const tone = STAGE_TONE[stage.state];

  return (
    <Card>
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{stage.label}</CapsLabel>
        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
          <span className="chip__mark" aria-hidden>
            {tone.mark}
          </span>
          {t(STATE_LABEL[stage.state])}
        </span>
      </div>

      <ul className="stack" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
        {stage.conditions.map((condition) => {
          const conditionTone = condition.met ? STAGE_TONE.done : STAGE_TONE.blocked;
          return (
            <li
              key={condition.code}
              style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}
            >
              <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                <span aria-hidden style={{ color: conditionTone.fg }}>
                  {conditionTone.mark}
                </span>
                <span>{condition.label}</span>
              </span>
              {/* The rule this screen shares with the readiness card — what she
                  has, then what she needs — but the threshold is shown only
                  where it is still wanted. Most conditions here are yes/no, and
                  "Yes (need Yes)" is noise on a satisfied row: it says nothing,
                  and at 360px it wraps the rows that *do* need reading. */}
              <span style={{ whiteSpace: "nowrap" }}>
                <strong style={{ color: conditionTone.fg }}>{condition.actual ?? "—"}</strong>
                {!condition.met && <span className="t-meta"> (need {condition.threshold})</span>}
              </span>
            </li>
          );
        })}
      </ul>

      {stage.code === "VERIFIED" && stage.state === "waiting" && (
        <p className="t-meta" style={{ marginTop: 12 }}>
          {t("wlt.awaitingVerification")}
        </p>
      )}

      {stage.code === "GROUPED" && stage.state === "ready" && (
        <div style={{ marginTop: 12 }}><p className="t-meta">{t("wlt.addToGroupHelp")}</p><Button variant="primary" onClick={onAddToGroup}>Add her to a group</Button></div>
      )}

      {stage.code === "LINKED" && <LinkageDetail stage={stage} onNavigate={onNavigate} />}
    </Card>
  );
}

function AddToGroupModal({ open, person, stage, onClose, onDone }: { open: boolean; person: string; stage?: JourneyStage; onClose: () => void; onDone: () => void }) {
  const { message } = App.useApp(); const [form] = Form.useForm<{ group: string }>();
  const [groups, setGroups] = useState<WltGroup[]>([]); const [loading, setLoading] = useState(false); const [saving, setSaving] = useState(false); const [drafting, setDrafting] = useState(false);
  const kebele = stage?.detail.kebele as string | undefined; const kebeleName = String(stage?.detail.kebele_name || "this kebele");
  const loadGroups = useCallback(async () => { if (!open || !kebele) return; setLoading(true); try { const response = await api.get<Paginated<WltGroup>>("/wlt/groups/", { params: { kebele, page_size: 200 } }); setGroups(response.data.results); } catch (error) { message.error(errorMessage(error, "Could not load groups in this kebele.")); } finally { setLoading(false); } }, [kebele, message, open]);
  useEffect(() => { void loadGroups(); }, [loadGroups]);
  async function submit(values: { group: string }) { setSaving(true); try { await api.post(`/wlt/groups/${values.group}/members/`, { person }); message.success("She was added to the group."); form.resetFields(); onDone(); } catch (error) { message.error(errorMessage(error, "Could not add her to this group.")); } finally { setSaving(false); } }
  return <><Modal open={open && !drafting} title="Add her to a group" onCancel={onClose} onOk={() => form.submit()} okText="Add to group" confirmLoading={saving} destroyOnHidden><p className="t-meta">Groups in {kebeleName}</p><Form form={form} layout="vertical" onFinish={(values) => void submit(values)}><Form.Item name="group" label="Savings group" rules={[{ required: true, message: "Choose a group." }]}><Select loading={loading} showSearch optionFilterProp="label" options={groups.map((group) => ({ value: group.id, label: `${group.name} · ${group.status_display} · ${group.members_current} ${group.members_current === 1 ? "member" : "members"}` }))} notFoundContent={`No available groups in ${kebeleName}.`} /></Form.Item></Form><Button onClick={() => setDrafting(true)}>Start a new group</Button></Modal><DraftGroupModal open={open && drafting} initialKebele={kebele} onClose={() => setDrafting(false)} onDone={() => { setDrafting(false); void loadGroups(); }} /></>;
}

/** One linkage her group holds — every status, not only the live ones. */
type JourneyLinkage = {
  id: string;
  type_label: string;
  status: LinkageStatus;
  status_display: string;
  provider_name: string | null;
  opened_on: string | null;
  activated_on: string | null;
  is_live: boolean;
  is_settled: boolean;
};

type LinkageRow = {
  code: string;
  label: string;
  min_phase_display: string;
  group_phase_display: string;
};

function LinkageDetail({ stage, onNavigate }: { stage: JourneyStage; onNavigate: (to: string) => void }) {
  const { t } = useLang();
  const available = (stage.detail.available_types as LinkageRow[] | undefined) ?? [];
  const blocked = (stage.detail.blocked_types as LinkageRow[] | undefined) ?? [];
  const held = (stage.detail.service_linkages as JourneyLinkage[] | undefined) ?? [];

  // Live first, then the ones somebody has to act on, then settled history.
  // Sorting by date instead would bury a blocked bank linkage under a closed
  // one, and the blocked row is the whole reason this list is worth reading.
  const rank = (linkage: JourneyLinkage) => (linkage.is_live ? 0 : linkage.is_settled ? 2 : 1);
  const ordered = [...held].sort((a, b) => rank(a) - rank(b));

  if (!stage.detail.group) return null;

  return (
    <div className="stack" style={{ marginTop: 12 }}>
      {ordered.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.groupLinkages")}</CapsLabel>
          <ul className="stack" style={{ listStyle: "none", margin: "6px 0 0", padding: 0, gap: 6 }}>
            {ordered.map((linkage) => {
              const tone = LINKAGE_TONE[linkage.status];
              return (
                <li
                  key={linkage.id}
                  style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}
                >
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block" }}>{linkage.type_label}</span>
                    {(linkage.provider_name || linkage.activated_on || linkage.opened_on) && (
                      <span className="t-meta" style={{ display: "block" }}>
                        {[
                          linkage.provider_name,
                          linkage.activated_on
                            ? t("wlt.linkageActiveSince", { date: linkage.activated_on })
                            : linkage.opened_on
                              ? t("wlt.linkageOpened", { date: linkage.opened_on })
                              : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    )}
                  </span>
                  <span
                    className="chip"
                    style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd, whiteSpace: "nowrap" }}
                  >
                    <span className="chip__mark" aria-hidden>
                      {tone.mark}
                    </span>
                    {linkage.status_display}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {ordered.length === 0 && <p className="t-meta" style={{ margin: 0 }}>{t("wlt.noGroupLinkages")}</p>}

      {available.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.availableLinkages")}</CapsLabel>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {available.map((row) => (
              <li key={row.code}>{row.label}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Named rather than omitted. A facilitator asking why the bank option is
          absent gets the phase it needs, not an empty list. */}
      {blocked.length > 0 && (
        <div>
          <CapsLabel>{t("wlt.blockedLinkages")}</CapsLabel>
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
            {blocked.map((row) => (
              <li key={row.code} className="t-meta">
                {row.label} —{" "}
                {t("wlt.needsPhase", {
                  phase: row.min_phase_display,
                  actual: row.group_phase_display || t("wlt.noPhaseYet"),
                })}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <Button size="sm" onClick={() => onNavigate("/wlt/linkages")}>
          {t("wlt.goToLinkages")}
        </Button>
      </div>
    </div>
  );
}
