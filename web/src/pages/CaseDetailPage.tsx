import { App, Form, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import {
  PATHWAY_OPTIONS,
  type CaseDetail,
  type Paginated,
  type Pathway,
  type PathwayAssignment,
  type Referral,
  type Youth,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import CaseAlerts from "../components/CaseAlerts";
import CaseFormModal from "../components/CaseFormModal";
import ReferralPanel from "../components/ReferralPanel";
import { Button, CapsLabel, CaseStatusChip, Card, Field, MutedChip, ProgressTrack, maskPhone } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

/**
 * The case screen — the handoff's core screen.
 *
 * Its organising claim is that the visible goal is a young person in paid work
 * six months later, not paperwork completion. So the top of the screen is a
 * goal panel and a next action, and the record itself comes after them.
 */

/**
 * The journey the goal panel counts against.
 *
 * Derived from records that exist rather than from a stored progress field:
 * each step is a fact already on the case. The handoff's panel also names a
 * retention target date, which needs Sprint 5's Placement entity and its 30/60/
 * 90-day checkpoints — until those land there is no honest date to print, so
 * the panel shows the step count alone rather than a made-up deadline.
 */
const JOURNEY = ["Registered", "Profiled", "Pathway assigned", "Referred", "Placed"] as const;

export default function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();

  const [record, setRecord] = useState<CaseDetail | null>(null);
  const [pathwayHistory, setPathwayHistory] = useState<PathwayAssignment[]>([]);
  const [youth, setYouth] = useState<Youth | null>(null);
  const [referralCount, setReferralCount] = useState(0);
  const [oldestPending, setOldestPending] = useState<Referral | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [revising, setRevising] = useState(false);
  const [editing, setEditing] = useState(false);
  const [revealPhone, setRevealPhone] = useState(false);
  const [reviseForm] = Form.useForm<{ selected_pathway: Pathway; revision_reason: string }>();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const detail = await api.get<CaseDetail>(`/cases/${caseId}/`);
      setRecord(detail.data);

      // Fetched separately because the case serializer carries a youth summary
      // and consent is on the full record — §9 makes it the legal basis for
      // holding any of this, so the screen has to be able to show it.
      const [youthDetail, referrals, pathways] = await Promise.all([
        api.get<Youth>(`/youth/${detail.data.youth}/`),
        api.get<Paginated<Referral>>("/referrals/", { params: { case: caseId, page_size: 100 } }),
        // §4.4 keeps every revision, and the superseded ones carry the rationale
        // §9 requires on a pathway change — so the history is the record, not a
        // nicety. The current assignment alone cannot answer "why did this
        // change?", which is the question a supervisor actually asks.
        api.get<Paginated<PathwayAssignment>>("/cases/pathways/", { params: { case: caseId } }),
      ]);
      setYouth(youthDetail.data);
      setPathwayHistory(pathways.data.results);
      setReferralCount(referrals.data.count);
      const pending = referrals.data.results
        .filter((referral) => referral.status === "PENDING_CONFIRMATION")
        .sort((a, b) => a.initiated_date.localeCompare(b.initiated_date));
      setOldestPending(pending[0] ?? null);
    } catch (error) {
      // A case outside the user's scope 404s rather than 403 — the API does not
      // confirm that a record they cannot see exists.
      message.error(errorMessage(error, "Could not load this case."));
      navigate("/cases", { replace: true });
    } finally {
      setLoading(false);
    }
  }, [caseId, message, navigate]);

  useEffect(() => {
    void load();
  }, [load]);

  // Reveal is per-view and never persisted: the point is a deliberate act in a
  // shared office, and a sticky setting would defeat it.
  useEffect(() => {
    setRevealPhone(false);
  }, [caseId]);

  async function saveNextAction(values: { next_action: string }) {
    setSaving(true);
    try {
      const response = await api.patch<CaseDetail>(`/cases/${caseId}/`, values);
      setRecord(response.data);
      message.success("Next action updated.");
    } catch (error) {
      message.error(errorMessage(error, "Could not update the case."));
    } finally {
      setSaving(false);
    }
  }

  async function revisePathway(values: { selected_pathway: Pathway; revision_reason: string }) {
    if (!record?.current_pathway) return;
    try {
      await api.post(`/cases/pathways/${record.current_pathway.id}/revise/`, values);
      message.success("Pathway revised.");
      setRevising(false);
      reviseForm.resetFields();
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not revise the pathway."));
    }
  }

  if (loading) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!record) return null;

  const summary = record.youth_detail;
  const canWrite = user?.access.case_write ?? false;
  const profiling = record.current_profiling;

  const stepsDone = [
    true,
    Boolean(profiling),
    Boolean(record.current_pathway),
    referralCount > 0,
    record.case_status === "PLACED",
  ].filter(Boolean).length;

  const pendingDays = oldestPending
    ? Math.max(0, Math.floor((Date.now() - new Date(oldestPending.initiated_date).getTime()) / 86_400_000))
    : 0;

  return (
    <div className="page stack">
      <Button size="sm" onClick={() => navigate("/cases")} style={{ alignSelf: "flex-start" }}>
        ← {t("case.back")}
      </Button>

      {/* -- Header row ----------------------------------------------------- */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, justifyContent: "space-between" }}>
        <div style={{ flex: "1 1 320px" }}>
          <CapsLabel>
            {t("case.eyebrow", { ref: caseRef(record.id), woreda: record.woreda })}
          </CapsLabel>
          <h1 className="t-display" style={{ margin: "2px 0 6px" }}>
            {summary.full_name}
          </h1>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
            <CaseStatusChip status={record.case_status} label={record.case_status_display} />
            <span className="t-meta">
              {record.current_pathway
                ? t("case.pathway", { pathway: record.current_pathway.selected_pathway_display })
                : t("case.noPathway")}
            </span>
            {canWrite && (
              <Button size="sm" onClick={() => setEditing(true)}>
                {t("case.edit")}
              </Button>
            )}
          </div>
        </div>

        {/* Goal panel — the screen's organising claim, stated first. */}
        <div
          style={{
            minWidth: 230,
            flex: "0 1 320px",
            background: "var(--green-900)",
            color: "var(--on-dark)",
            borderRadius: "var(--r-card)",
            padding: "14px 16px",
          }}
        >
          <div className="t-caps" style={{ color: "var(--gold-300)" }}>
            {t('case.goal')}
          </div>
          <div style={{ margin: "8px 0 10px", fontSize: 15 }}>
            {JOURNEY[Math.min(stepsDone, JOURNEY.length) - 1]}
          </div>
          <ProgressTrack
            value={stepsDone / JOURNEY.length}
            height={6}
            fill="var(--gold-300)"
            track="rgba(255,255,255,.2)"
          />
          <div style={{ marginTop: 8, fontSize: 13, color: "var(--on-dark-2)" }}>
            Step {stepsDone} of {JOURNEY.length} · {JOURNEY.slice(0, stepsDone).join(", ")}
          </div>
        </div>
      </div>

      {/* -- Next action banner ---------------------------------------------- */}
      <div className="banner banner--next-action">
        <div style={{ flex: 1, minWidth: 240 }}>
          <div className="t-caps" style={{ color: "var(--gold-700)" }}>
            {t("case.nextAction")}
          </div>
          <div className="t-body-strong" style={{ margin: "2px 0" }}>
            {record.next_action || t("case.noNextAction")}
          </div>
          <div style={{ fontSize: 13, color: "var(--gold-700)" }}>
            {oldestPending
              ? `${oldestPending.referral_category_label} · waiting ${pendingDays} days`
              : `Last activity ${record.last_activity_date} · ${record.days_since_activity} days ago`}
          </div>
        </div>
        {canWrite && (
          <Button variant="primary" onClick={() => setEditing(true)}>
            {t("case.setNextAction")}
          </Button>
        )}
      </div>

      {/* -- Pathway (§4.4) --------------------------------------------------- */}
      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", justifyContent: "space-between" }}>
          <CapsLabel>{t("case.pathwayHeading")}</CapsLabel>
          {canWrite && record.current_pathway && (
            <Button size="sm" onClick={() => setRevising(true)}>
              {t("case.revisePathway")}
            </Button>
          )}
        </div>

        {record.current_pathway ? (
          <>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", marginTop: 8 }}>
              <span
                className="chip"
                style={{
                  color: "var(--green-ink)",
                  background: "var(--green-100)",
                  borderColor: "var(--green-border)",
                  fontSize: 14,
                }}
              >
                {record.current_pathway.selected_pathway_display}
              </span>
              <span className="t-meta">
                {t("case.assessedBy", {
                  date: record.current_pathway.assessment_date,
                  name: record.current_pathway.assessor_name,
                })}
              </span>
            </div>

            {/* Only worth a heading once something has actually been superseded. */}
            {pathwayHistory.length > 1 && (
              <>
                <div className="card__rule" />
                <CapsLabel style={{ marginBottom: 8 }}>{t("case.revisionHistory")}</CapsLabel>
                <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
                  {pathwayHistory.map((item, index) => (
                    // No accent rail; entries are separated by a rule instead,
                    // and the current one is already marked by its chip.
                    <li
                      key={item.id}
                      style={
                        index === 0
                          ? undefined
                          : { borderTop: "1px solid var(--line-soft)", paddingTop: 10 }
                      }
                    >
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{item.selected_pathway_display}</span>
                        {item.is_current && <MutedChip style={{ fontSize: 12 }}>{t("case.current")}</MutedChip>}
                      </div>
                      <div className="t-meta">
                        {t("case.assessedBy", { date: item.assessment_date, name: item.assessor_name })}
                      </div>
                      {item.revision_reason && (
                        <div className="t-meta">
                          {t("case.superseded", { reason: item.revision_reason })}
                        </div>
                      )}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </>
        ) : (
          <div className="t-meta" style={{ marginTop: 8 }}>
            {t("case.noPathway")}
          </div>
        )}
      </Card>

      {/* -- Identity and profiling ------------------------------------------ */}
      <div className="grid-cards">
        <Card>
          <CapsLabel style={{ marginBottom: 10 }}>{t("case.identity")}</CapsLabel>
          <div className="grid-pairs">
            <Field label={t("case.age")}>{summary.age}</Field>
            <Field label={t("case.sex")}>{summary.sex}</Field>
            <Field label={t("case.dob")}>{summary.date_of_birth}</Field>
            <Field label={t("case.kebele")}>
              {record.woreda} · {summary.kebele}
            </Field>
          </div>

          <div className="card__rule" />

          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <Field label={t("case.phone")}>
              <span className="tabular">
                {summary.phone_number
                  ? revealPhone
                    ? summary.phone_number
                    : maskPhone(summary.phone_number)
                  : t("common.none")}
              </span>
            </Field>
            {summary.phone_number && (
              <Button size="sm" onClick={() => setRevealPhone(!revealPhone)}>
                {revealPhone ? t("case.hide") : t("case.reveal")}
              </Button>
            )}
          </div>

          <div className="t-meta" style={{ marginTop: 8 }}>
            {youth?.consent_date ? t("case.consent", { date: youth.consent_date }) : t("case.noConsent")}
          </div>
        </Card>

        <Card>
          <CapsLabel style={{ marginBottom: 10 }}>{t("case.profiling")}</CapsLabel>
          {profiling ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {/* The handoff's card lists verified/self-reported per criterion.
                  §4.3 records eligibility flags and an assessor rather than a
                  verification state per row, so each flag is shown as recorded
                  by whoever assessed it — inventing a verification level here
                  would put a claim on screen the record does not make. */}
              {profiling.eligibility_flags_display.map((flag) => (
                <Row key={flag} label={flag} value="✓ Recorded" tone="var(--green-ink)" />
              ))}
              <Row
                label="Skills"
                value={profiling.skills_list.length ? profiling.skills_list.join(", ") : "None recorded"}
              />
              <Row
                label="Vulnerability score"
                value={profiling.vulnerability_index_score ?? "Methodology pending"}
                tone={profiling.vulnerability_index_score ? undefined : "var(--ink-400)"}
              />
              {profiling.priority_flag && <Row label="Priority" value="▲ Flagged" tone="var(--terra-700)" />}
              <div className="t-meta">
                Assessed {profiling.assessed_date} by {profiling.assessor_name}
              </div>
            </div>
          ) : (
            <div className="t-meta">{t("case.noProfiling")}</div>
          )}
        </Card>
      </div>

      <CaseAlerts caseId={record.id} onChanged={load} />

      <ReferralPanel caseId={record.id} woreda={record.woreda} onChanged={load} />

      {canWrite && (
        <Card>
          <CapsLabel style={{ marginBottom: 8 }}>{t("case.nextAction")}</CapsLabel>
          <Form layout="vertical" initialValues={{ next_action: record.next_action }} onFinish={saveNextAction}>
            <Form.Item name="next_action">
              <Input.TextArea rows={3} placeholder="e.g. Confirm TVET enrolment with Adama Polytechnic" />
            </Form.Item>
            <Button variant="primary" type="submit" disabled={saving}>
              {t("common.save")}
            </Button>
          </Form>
        </Card>
      )}

      <CaseFormModal open={editing} record={record} onClose={() => setEditing(false)} onSaved={() => load()} />

      <Modal
        open={revising}
        title="Revise pathway"
        onCancel={() => setRevising(false)}
        onOk={() => reviseForm.submit()}
        destroyOnHidden
      >
        <Form form={reviseForm} layout="vertical" onFinish={revisePathway} requiredMark={false}>
          <Form.Item name="selected_pathway" label="New pathway" rules={[{ required: true }]}>
            <Select options={PATHWAY_OPTIONS} />
          </Form.Item>
          <Form.Item
            name="revision_reason"
            label="Why is it changing?"
            rules={[{ required: true, message: "A rationale is required on every pathway change." }]}
            extra="Recorded against the superseded assignment (spec §9)."
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function Row({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 14 }}>
      <span>{label}</span>
      <span style={{ color: tone, fontWeight: 600, textAlign: "right" }}>{value}</span>
    </div>
  );
}

/**
 * A case's human reference.
 *
 * §4.2 gives a case a UUID and no programme-facing reference, while the
 * handoff's eyebrow shows `YE-OR-AD-04821` — a structured code encoding region,
 * woreda and a sequence. None of that is in the schema, and fabricating it
 * would put an identifier on screen that no other system could resolve, so this
 * renders the real id in short form until a reference field is specified.
 */
function caseRef(id: string): string {
  return id.replace(/-/g, "").slice(0, 8).toUpperCase();
}
