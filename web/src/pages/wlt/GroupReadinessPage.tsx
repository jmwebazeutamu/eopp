import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { ServiceLinkage, WltReadiness } from "../../api/types";
import { Card, CapsLabel, Field, PageHeader } from "../../components/ui";
import { CONDITION_TONE, LINKAGE_TONE, WLT_GROUP_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import GroupRoster from "./GroupRoster";
import { freshness, summarise, type ConditionLine } from "./readinessLayout";

/**
 * The readiness card.
 *
 * The handoff calls immediate feedback at meeting close "most of the module's
 * behaviour-change value", and this is the screen that carries it. One rule
 * governs the whole page: **the actual value always sits next to the
 * threshold**. "Attendance 74% (need 80%)" tells a facilitator what to do next
 * week. A red dot tells her she failed and nothing else.
 *
 * Three states per condition, not two. "Not measurable yet" — no closed
 * meetings, no bylaw — is a different instruction from "below the threshold",
 * and rendering both in red would give the wrong one.
 */
export default function GroupReadinessPage() {
  const { groupId } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();

  const [data, setData] = useState<WltReadiness | null>(null);
  const [linkages, setLinkages] = useState<ServiceLinkage[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [readiness, linkageList] = await Promise.all([
        api.get<WltReadiness>(`/wlt/groups/${groupId}/readiness/`),
        api.get<{ results: ServiceLinkage[] }>("/wlt/linkages/", { params: { subject_group: groupId } }),
      ]);
      setData(readiness.data);
      setLinkages(linkageList.data.results ?? []);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.readinessLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [groupId, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!data) return null;

  const { group, indicators, risk_flags: riskFlags } = data;
  const summary = summarise(data.gate);
  const tone = WLT_GROUP_TONE[group.status];
  const stale = freshness(data.computed_at, new Date().toISOString().slice(0, 10));

  return (
    <div className="page stack">
      <PageHeader
        title={group.name}
        subtitle={
          <span>
            {group.kebele_name} · {t("wlt.membersCount", { count: group.members_current })} ·{" "}
            <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
              <span className="chip__mark" aria-hidden>
                {tone.mark}
              </span>
              {group.status_display}
            </span>
          </span>
        }
      />

      {/* A stale card that is honest about its age beats a fresh one that is
          wrong — the handoff's rule for offline reading. */}
      {stale && <div className="t-meta">{stale}</div>}

      <Card>
        <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
          <CapsLabel>{t("wlt.readiness")}</CapsLabel>
          <span className="t-meta">
            {group.current_phase ? group.phase_display : t("wlt.noPhase")}
            {summary ? ` · ${t("wlt.conditionsMet", { met: summary.met, total: summary.total })}` : ""}
          </span>
        </div>

        {!summary && <p className="t-meta">{t("wlt.noGate")}</p>}

        {summary && (
          <>
            <p style={{ marginTop: 8 }}>
              {summary.passed ? t("wlt.gatePassed") : t("wlt.gateOutstanding", { count: summary.outstanding.length })}
            </p>
            <ul className="stack" style={{ listStyle: "none", padding: 0, margin: "12px 0 0" }}>
              {summary.lines.map((line) => (
                <ConditionRow key={line.code} line={line} />
              ))}
            </ul>
          </>
        )}
      </Card>

      {/* The roster sits under the gate conditions because several of them are
          *about* it — group size, the office holders, the device rule. Reading
          "size 18 (need 15)" and then the eighteen names is the order a
          facilitator checks them in. */}
      <GroupRoster group={group} onChanged={load} />

      <div className="grid-cards">
        <Card>
          <CapsLabel>{t("wlt.savings")}</CapsLabel>
          <Field label={t("wlt.fund")}>{String(indicators.fund_etb ?? "0")} ETB</Field>
          <Field label={t("wlt.cash")}>{String(indicators.cash_balance_etb ?? "0")} ETB</Field>
          <Field label={t("wlt.bank")}>{String(indicators.bank_balance_etb ?? "0")} ETB</Field>
          <Field label={t("wlt.fundWeeks")}>
            {indicators.fund_weeks_of_contribution === null
              ? t("wlt.notMeasurable")
              : t("wlt.weeks", { count: String(indicators.fund_weeks_of_contribution) })}
          </Field>
        </Card>

        <Card>
          <CapsLabel>{t("wlt.meetings")}</CapsLabel>
          <Field label={t("wlt.meetingsHeld")}>{String(indicators.meetings_held_total ?? 0)}</Field>
          <Field label={t("wlt.attendance")}>
            {indicators.attendance_pct === null ? t("wlt.notMeasurable") : `${indicators.attendance_pct}%`}
          </Field>
          <Field label={t("wlt.savingsCompliance")}>
            {indicators.savings_compliance_pct === null
              ? t("wlt.notMeasurable")
              : `${indicators.savings_compliance_pct}%`}
          </Field>
          <Field label={t("wlt.lastMeeting")}>{String(indicators.last_meeting_on ?? "—")}</Field>
        </Card>

        <Card>
          <CapsLabel>{t("wlt.lending")}</CapsLabel>
          <Field label={t("wlt.outstanding")}>{String(indicators.loans_outstanding_etb ?? "0")} ETB</Field>
          <Field label="PAR30">
            {indicators.par30_pct === null ? t("wlt.notMeasurable") : `${indicators.par30_pct}%`}
          </Field>
          <Field label={t("wlt.completedCycles")}>{String(indicators.completed_loan_cycles ?? 0)}</Field>
        </Card>
      </div>

      {riskFlags.length > 0 && (
        <Card>
          <CapsLabel>{t("wlt.atRisk")}</CapsLabel>
          {/* An early warning, not a demotion. It is visible to the facilitator
              and does not by itself move the group backwards. */}
          <p className="t-meta">{t("wlt.atRiskExplainer")}</p>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {riskFlags.map((flag) => (
              <li key={flag.id}>
                {flag.reason_code.replace(/_/g, " ").toLowerCase()} · {flag.raised_on}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card>
        <CapsLabel>{t("wlt.linkages")}</CapsLabel>
        {linkages.length === 0 && <p className="t-meta">{t("wlt.noLinkages")}</p>}
        <div className="stack" style={{ marginTop: 8 }}>
          {linkages.map((linkage) => {
            const linkageTone = LINKAGE_TONE[linkage.status];
            return (
              <div key={linkage.id}>
                <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                  <strong>{linkage.type_label}</strong>
                  <span
                    className="chip"
                    style={{ color: linkageTone.fg, background: linkageTone.bg, borderColor: linkageTone.bd }}
                  >
                    <span className="chip__mark" aria-hidden>
                      {linkageTone.mark}
                    </span>
                    {linkage.status_display}
                  </span>
                </div>
                <div className="t-meta">{linkage.provider_name ?? t("wlt.noProvider")}</div>
                {linkage.block_reasons.length > 0 && (
                  <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                    {linkage.block_reasons.map((reason) => (
                      <li key={reason} className="t-meta">
                        {reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}

function ConditionRow({ line }: { line: ConditionLine }) {
  const tone = CONDITION_TONE[line.state];
  return (
    <li style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
      <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
        <span aria-hidden style={{ color: tone.fg }}>
          {tone.mark}
        </span>
        <span>{line.label}</span>
      </span>
      {/* The whole point of the card: what it has, then what it needs. */}
      <span style={{ whiteSpace: "nowrap" }}>
        <strong style={{ color: tone.fg }}>{line.state === "unmeasurable" ? "—" : line.actual}</strong>
        <span className="t-meta"> (need {line.threshold})</span>
      </span>
    </li>
  );
}
