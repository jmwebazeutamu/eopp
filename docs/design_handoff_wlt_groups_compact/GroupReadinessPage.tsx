import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { ServiceLinkage, WltReadiness } from "../../api/types";
import { Card, CapsLabel, PageHeader } from "../../components/ui";
import { CONDITION_TONE, LINKAGE_TONE, WLT_GROUP_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import GroupRoster from "./GroupRoster";
import { freshness, summarise, type ConditionLine } from "./readinessLayout";

/**
 * The readiness card — compact layout.
 *
 * Same rule as before: the actual value always sits next to the threshold,
 * and three states per condition, not two. What changed is density: one
 * condition per full-width row cost roughly 32px each with only one column of
 * information in it. `.condition-grid` gives the same text a tile that wraps
 * at 150px, so six conditions read as two rows instead of six.
 *
 * The three indicator cards (savings / meetings / lending) are now one card
 * with three flex columns — same `Field`-shaped label/value pairs, one line
 * each instead of two.
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
    <div className="page" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
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

      {stale && <div className="t-meta">{stale}</div>}

      <Card className="card--tight">
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
            <p style={{ marginTop: 8, fontSize: 13 }}>
              {summary.passed ? t("wlt.gatePassed") : t("wlt.gateOutstanding", { count: summary.outstanding.length })}
            </p>
            <div className="condition-grid">
              {summary.lines.map((line) => (
                <ConditionTile key={line.code} line={line} />
              ))}
            </div>
          </>
        )}
      </Card>

      {/* Still directly under the gate, for the same reason as before: several
          conditions (size, officers, device rule) are about the roster, so
          reading "size 18 (need 15)" then the eighteen names is the order a
          facilitator checks them in. */}
      <GroupRoster group={group} onChanged={load} />

      <Card className="card--tight">
        <div className="indicator-cols">
          <IndicatorColumn
            title={t("wlt.savings")}
            rows={[
              [t("wlt.fund"), `${String(indicators.fund_etb ?? "0")} ETB`],
              [t("wlt.cash"), `${String(indicators.cash_balance_etb ?? "0")} ETB`],
              [t("wlt.bank"), `${String(indicators.bank_balance_etb ?? "0")} ETB`],
              [
                t("wlt.fundWeeks"),
                indicators.fund_weeks_of_contribution === null
                  ? t("wlt.notMeasurable")
                  : t("wlt.weeks", { count: String(indicators.fund_weeks_of_contribution) }),
              ],
            ]}
          />
          <IndicatorColumn
            title={t("wlt.meetings")}
            rows={[
              [t("wlt.meetingsHeld"), String(indicators.meetings_held_total ?? 0)],
              [t("wlt.attendance"), indicators.attendance_pct === null ? t("wlt.notMeasurable") : `${indicators.attendance_pct}%`],
              [
                t("wlt.savingsCompliance"),
                indicators.savings_compliance_pct === null ? t("wlt.notMeasurable") : `${indicators.savings_compliance_pct}%`,
              ],
              [t("wlt.lastMeeting"), String(indicators.last_meeting_on ?? "—")],
            ]}
          />
          <IndicatorColumn
            title={t("wlt.lending")}
            rows={[
              [t("wlt.outstanding"), `${String(indicators.loans_outstanding_etb ?? "0")} ETB`],
              ["PAR30", indicators.par30_pct === null ? t("wlt.notMeasurable") : `${indicators.par30_pct}%`],
              [t("wlt.completedCycles"), String(indicators.completed_loan_cycles ?? 0)],
            ]}
          />
        </div>
      </Card>

      {riskFlags.length > 0 && (
        <Card className="card--tight">
          <CapsLabel>{t("wlt.atRisk")}</CapsLabel>
          <p className="t-meta">{t("wlt.atRiskExplainer")}</p>
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {riskFlags.map((flag) => (
              <li key={flag.id} style={{ fontSize: 13 }}>
                {flag.reason_code.replace(/_/g, " ").toLowerCase()} · {flag.raised_on}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="card--tight">
        <CapsLabel>{t("wlt.linkages")}</CapsLabel>
        {linkages.length === 0 && <p className="t-meta">{t("wlt.noLinkages")}</p>}
        <div style={{ marginTop: 4 }}>
          {linkages.map((linkage) => {
            const linkageTone = LINKAGE_TONE[linkage.status];
            return (
              <div
                key={linkage.id}
                style={{ padding: "6px 0", borderBottom: "1px solid var(--line-soft)" }}
              >
                <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 13 }}>{linkage.type_label}</strong>
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

function IndicatorColumn({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="indicator-col">
      <CapsLabel>{title}</CapsLabel>
      {rows.map(([label, value]) => (
        <div key={label} className="indicator-row">
          <span className="t-meta">{label}</span>
          <span className="tabular" style={{ fontWeight: 600 }}>
            {value}
          </span>
        </div>
      ))}
    </div>
  );
}

function ConditionTile({ line }: { line: ConditionLine }) {
  const tone = CONDITION_TONE[line.state];
  return (
    <div className="condition-tile">
      <div className="condition-tile__label">
        <span aria-hidden style={{ color: tone.fg }}>
          {tone.mark}
        </span>
        <span>{line.label}</span>
      </div>
      <div className="condition-tile__value" style={{ color: tone.fg }}>
        {line.state === "unmeasurable" ? "—" : line.actual}
        <span className="t-meta" style={{ fontWeight: 500 }}>
          {" "}
          (need {line.threshold})
        </span>
      </div>
    </div>
  );
}
