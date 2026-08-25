import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { BeneficiaryHousehold, Journey, JourneyStage, LinkageStatus, Paginated, WltGroup, WltGroupStatus } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card, formatMoney } from "../../components/ui";
import { LINKAGE_TONE, WLT_GROUP_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import BeneficiaryIdentityCard from "./BeneficiaryIdentity";
import DraftGroupModal from "./DraftGroupModal";
import PathwayStages from "./PathwayStages";

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

  const grouped = journey.stages.find((stage) => stage.code === "GROUPED");
  const linked = journey.stages.find((stage) => stage.code === "LINKED");
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
      {/* Two crumbs, not three. The design puts the kebele between the registry
          and her name; there is no kebele route to land on, and a crumb that
          goes nowhere is worse than one fewer. */}
      <nav className="t-meta" aria-label={t("wlt.backToRegistry")}>
        <button type="button" className="row-link" onClick={() => navigate("/wlt/beneficiaries")}>
          {t("wlt.backToRegistry")}
        </button>
        <span aria-hidden> › </span>
        <span>{journey.full_name}</span>
      </nav>

      <BeneficiaryIdentityCard identity={journey.identity} />

      {/* Her story on the left, her numbers on the right. The single column it
          replaces ran to about 2,000px, which put "open a meeting" and the
          money she has saved below two screenfuls of gate conditions. */}
      <div className="record-overview">
        <div className="stack">
          <PathwayStages
            stages={journey.stages}
            done={journey.stages_done}
            total={journey.stages_total}
            nextAction={journey.next_action}
          >
            {(stage) => (
              <>
                {stage.code === "VERIFIED" && stage.state === "waiting" && (
                  <div style={{ marginTop: 12 }}>
                    <p className="t-meta">{t("wlt.awaitingVerification")}</p>
                    {canVerify && (
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <Button variant="primary" onClick={() => setVerificationDecision(true)}>
                          {t("wlt.verifyRegistration")}
                        </Button>
                        <Button variant="destructive-soft" onClick={() => setVerificationDecision(false)}>
                          {t("wlt.refuseRegistration")}
                        </Button>
                      </div>
                    )}
                  </div>
                )}

                {stage.code === "GROUPED" && stage.state === "ready" && (
                  <div style={{ marginTop: 12 }}>
                    <p className="t-meta">{t("wlt.addToGroupHelp")}</p>
                    <Button variant="primary" onClick={() => setAddToGroup(true)}>
                      {t("wlt.addHerToAGroup")}
                    </Button>
                  </div>
                )}
              </>
            )}
          </PathwayStages>

          {grouped && <GroupCard stage={grouped} onNavigate={navigate} />}

          {linked && <LinkagesCard stage={linked} onNavigate={navigate} />}
        </div>

        <div className="stack">
          <MoneyCard financials={journey.financials} />
          <HouseholdCard household={journey.household} />
        </div>
      </div>

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
/**
 * What she has saved, and what she still owes.
 *
 * The savings total leads on a green ground because it is the number the whole
 * programme is about; everything else is a supporting figure at the size of a
 * supporting figure. Before this they were four identical 22px numbers in a
 * row, so "she has saved 1,040" and "she owes 60" carried the same weight.
 *
 * **Outstanding is terracotta, and disappears at zero.** It is the only figure
 * here that is work rather than a record, and a woman who has repaid in full
 * should not have a coloured row telling her so.
 *
 * Money arrives from the API as a decimal *string* and is never parsed. A float
 * cannot hold 0.10 exactly, and this is a savings ledger that women sign a
 * paper register against.
 */
function MoneyCard({ financials }: { financials: Journey["financials"] }) {
  const { t } = useLang();
  const outstanding = financials.outstanding_principal_etb;
  const owes = Number(outstanding) > 0;

  return (
    <section className="card" aria-labelledby="money-title">
      <CapsLabel id="money-title">{t("wlt.moneyTitle")}</CapsLabel>

      <div className="money-well">
        <div className="t-meta">{t("wlt.totalSavings")}</div>
        <div className="tabular money-well__figure">
          {formatMoney(financials.savings_etb)} <span className="money-well__unit">ETB</span>
        </div>
      </div>

      <div className="grid-pairs" style={{ marginTop: 12 }}>
        <div>
          <div className="t-meta">{t("wlt.loansReceived")}</div>
          <div className="tabular t-metric-sm">{formatMoney(financials.loans_disbursed_etb)}</div>
          <div className="t-meta">{t("wlt.loanCount", { count: financials.loans_disbursed_count })}</div>
        </div>
        <div>
          <div className="t-meta">{t("wlt.repaymentsMade")}</div>
          <div className="tabular t-metric-sm">{formatMoney(financials.repayments_etb)}</div>
          <div className="t-meta">
            {t("wlt.repaymentsBreakdown", {
              principal: formatMoney(financials.principal_repaid_etb),
              charges: formatMoney(financials.charges_repaid_etb),
            })}
          </div>
        </div>
      </div>

      {/* A bordered block, not `.card__rule` — that class *is* the 1px divider
          (height: 1px, negative side margins), so wrapping a row in it put the
          figure outside the card and over the panel below. */}
      {owes && (
        <div className="money-outstanding">
          <div className="t-meta">{t("wlt.principalOutstanding")}</div>
          <div className="tabular t-metric-sm" style={{ color: "var(--terra-700)" }}>
            {formatMoney(outstanding)}
          </div>
        </div>
      )}
    </section>
  );
}

/**
 * Her household, with only the columns that exist.
 *
 * The design asks for household size, dependants and marital status. None of
 * the three is a field on `Youth` or on the profile — `household_id` is the
 * PSNP household *identifier*, not a count — so they are absent rather than
 * rendered as a zero somebody would report. Adding them is a migration, an
 * intake-form field and an ELS extract column, which is a programme decision.
 *
 * What is left is real: head of household, education, disability, PSNP caseload
 * category and her main activity. On a record that carries none of them the
 * card says so in a sentence rather than drawing five empty rows.
 */
function HouseholdCard({ household }: { household: BeneficiaryHousehold }) {
  const { t } = useLang();
  const rows: Array<[string, string | null]> = [
    [t("wlt.householdHead"), household.household_head === null ? null : t(household.household_head ? "common.yes" : "common.no")],
    [t("wlt.educationLabel"), household.education_level_display || null],
    [t("wlt.disabilityLabel"), household.disability_status_display || null],
    [t("wlt.psnpCategoryLabel"), household.psnp_client_category_display || null],
    [t("wlt.primaryIgaLabel"), household.primary_iga || null],
    [t("wlt.householdId"), household.household_id || null],
  ];
  const known = rows.filter(([, value]) => value !== null);

  return (
    <section className="card" aria-labelledby="household-title">
      <CapsLabel id="household-title">{t("wlt.householdTitle")}</CapsLabel>
      {known.length === 0 ? (
        <p className="t-meta" style={{ margin: "8px 0 0" }}>{t("wlt.householdEmpty")}</p>
      ) : (
        <ul className="stack" style={{ listStyle: "none", margin: "8px 0 0", padding: 0, gap: 4 }}>
          {known.map(([label, value]) => (
            <li key={label} className="indicator-row">
              <span>{label}</span>
              <strong>{value}</strong>
            </li>
          ))}
        </ul>
      )}
      <p className="t-meta" style={{ margin: "12px 0 0" }}>{t("wlt.householdNotHeld")}</p>
    </section>
  );
}

/** The linkage panel, lifted out of the LINKED stage card that no longer exists. */
function LinkagesCard({ stage, onNavigate }: { stage: JourneyStage; onNavigate: (to: string) => void }) {
  const { t } = useLang();
  if (!stage.detail.group) return null;
  return (
    <section className="card" aria-labelledby="linkages-title">
      <CapsLabel id="linkages-title">{t("wlt.groupLinkages")}</CapsLabel>
      <LinkageDetail stage={stage} onNavigate={onNavigate} />
    </section>
  );
}

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
  next_approval_role_display: string | null;
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
      {/* No sub-heading on this list: the card above already says "Her group's
          linkages", and it is not only the open ones — closed and
          awaiting-approval rows sit here too, live first. Labelling it "Open"
          put a Closed chip under a heading that denied it. */}
      {ordered.length > 0 && (
        <div>
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
                    {linkage.next_approval_role_display && (
                      <span className="t-meta" style={{ display: "block" }}>
                        Awaiting {linkage.next_approval_role_display}
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
