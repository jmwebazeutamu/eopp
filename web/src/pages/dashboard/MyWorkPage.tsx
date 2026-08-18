import { Link } from "react-router-dom";

import type { CaseStatus, MyWork } from "../../api/types";
import { CapsLabel, CaseStatusChip, Card, MutedChip } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import TierPage from "./TierPage";
import { useTier } from "./useTier";

/**
 * Tier 1 — the case manager work queue.
 *
 * `CASE_MANAGER_DASHBOARD.md` §2, the hard list of what must not appear here:
 * no percentages, no charts, no comparison with other case managers, no trend
 * lines. A caseload of 80-200 is far below the stability floor once
 * disaggregated, and a rate is not an action.
 *
 * Every number links to a list of named youth. Anything that does not link
 * somewhere should be deleted rather than styled.
 *
 * The same data also renders server-side at `/dashboard/` on the Django origin,
 * from the same `queues` module — one definition of "needs action today", two
 * renderings, so they cannot drift.
 */

/**
 * How long ago the figures were read.
 *
 * Tier 1 is live rather than refreshed on a schedule, but a dashboard that does
 * not state its age invites the reader to assume it is current — and this one
 * is only as current as the last page load.
 */
function freshness(iso: string, t: (key: "cm.justNow") => string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  return minutes < 1 ? t("cm.justNow") : `${minutes} min ago`;
}

/**
 * The wait, keyed to the configured threshold rather than to a literal 7.
 *
 * Colour is paired with the day count as text and with a mark, so the row still
 * reads on a monochrome screen and in direct sunlight.
 */
function WaitBadge({ days, threshold }: { days: number; threshold: number }) {
  const over = days >= threshold;
  const near = !over && days >= Math.ceil((threshold * 2) / 3);
  const tone = over
    ? { fg: "var(--red-700)", bg: "var(--red-100)", mark: "▲" }
    : near
      ? { fg: "var(--gold-700)", bg: "var(--gold-100)", mark: "◔" }
      : { fg: "var(--ink-600)", bg: "var(--fill-muted)", mark: "●" };
  return (
    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: "transparent" }}>
      <span className="chip__mark" aria-hidden>
        {tone.mark}
      </span>
      {days}d
    </span>
  );
}

function Tile({ label, value, meta, tone }: { label: string; value: number; meta: string; tone?: "bad" | "warn" | "good" }) {
  const background = { bad: "var(--red-100)", warn: "var(--gold-100)", good: "var(--green-100)" };
  const border = { bad: "var(--red-border)", warn: "var(--gold-border)", good: "var(--green-border)" };
  return (
    <Card style={tone ? { background: background[tone], borderColor: border[tone] } : undefined}>
      <CapsLabel>{label}</CapsLabel>
      <div className="tabular" style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.1, marginTop: 4 }}>
        {value}
      </div>
      <div className="t-meta">{meta}</div>
    </Card>
  );
}

export default function MyWorkPage() {
  const { t } = useLang();
  const { data, loading } = useTier<MyWork>("/dashboard/my-work/");

  if (loading && !data) return <div className="t-meta">{t("common.loading")}</div>;
  if (!data) return null;

  return (
    <TierPage
      title={t("tier.myWorkFull")}
      subtitle={
        <>
          {t("tier.myWorkWhy")}
          {data.woredas.length > 0 && <> · {data.woredas.join(", ")}</>}
          {" · "}
          {t("cm.freshness", { when: freshness(data.generated_at, t) })}
        </>
      }
    >
      <div className="kpi-row">
        <Tile
          label={t("cm.needsAction")}
          value={data.needs_action_count}
          meta={t("cm.needsActionWhy")}
          tone={data.needs_action_count ? "bad" : undefined}
        />
        <Tile
          label={t("cm.awaiting")}
          value={data.awaiting_partner_count}
          meta={
            data.awaiting_over_threshold
              ? t("cm.overThreshold", { count: data.awaiting_over_threshold, days: data.confirmation_threshold })
              : t("cm.noneOverThreshold", { days: data.confirmation_threshold })
          }
          tone={data.awaiting_over_threshold ? "warn" : undefined}
        />
        <Tile
          label={t("cm.active")}
          value={data.active.referrals}
          meta={t("cm.activeMeta", { youth: data.active.youth })}
        />
        {/* The headline silently picked the "opened" half while the subtext
            read "0 opened · 20 closed", so a busy week looked like a dead one. */}
        <Tile
          label={t("cm.weekOpened")}
          value={data.week.opened}
          meta={t("cm.weekMeta", { closed: data.week.closed })}
        />
        <Tile
          label={t("cm.verified")}
          value={data.outcomes_verified.verified}
          meta={t("cm.verifiedMeta", { recorded: data.outcomes_verified.recorded })}
          tone="good"
        />
      </div>

      <div className="grid-panels">
        <Card>
          <CapsLabel>{t("cm.needsAction")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("cm.needsActionWhy")}
          </div>
          {data.needs_action.length === 0 ? (
            // "Nothing is overdue" is a claim about the programme. For a
            // supervisor with nothing assigned but hundreds open in view, the
            // true statement is the narrower one.
            <div className="t-meta">
              {data.open_alerts_in_scope > 0
                ? t("cm.noneAssigned", { count: data.open_alerts_in_scope })
                : t("cm.nothingOverdue")}
            </div>
          ) : (
            <div className="stack" style={{ gap: 0 }}>
              {data.needs_action.map((row) => (
                <Link
                  key={row.id}
                  to={`/cases/${row.case}`}
                  style={{
                    display: "flex",
                    gap: 10,
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    padding: "9px 0",
                    borderBottom: "1px solid var(--line)",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <span>
                    <span className="t-body-strong">{row.youth_name}</span>
                    <span className="t-meta" style={{ display: "block" }}>
                      {row.reason}
                    </span>
                  </span>
                  <span
                    className="chip"
                    style={{
                      color: row.days_overdue > 0 ? "var(--red-700)" : "var(--gold-700)",
                      background: row.days_overdue > 0 ? "var(--red-100)" : "var(--gold-100)",
                      borderColor: "transparent",
                      whiteSpace: "nowrap",
                    }}
                  >
                    <span className="chip__mark" aria-hidden>
                      {row.days_overdue > 0 ? "▲" : "◔"}
                    </span>
                    {row.days_overdue > 0 ? t("cm.overdue", { days: row.days_overdue }) : t("cm.dueToday")}
                  </span>
                </Link>
              ))}
            </div>
          )}
          {data.needs_action_count > data.needs_action.length && (
            <Link className="t-meta" style={{ display: "inline-block", marginTop: 10, fontWeight: 600 }} to="/alerts">
              {t("cm.viewAll", { n: data.needs_action_count })}
            </Link>
          )}
        </Card>

        <Card>
          <CapsLabel>{t("cm.awaiting")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("cm.awaitingWhy")}
          </div>
          {data.awaiting_partner.length === 0 ? (
            <div className="t-meta">{t("cm.nothingWaiting")}</div>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{t("queue.col.youth")}</th>
                  <th scope="col">{t("queue.col.partner")}</th>
                  <th scope="col">{t("queue.col.waiting")}</th>
                </tr>
              </thead>
              <tbody>
                {data.awaiting_partner.map((row) => (
                  <tr key={row.id}>
                    <td>{row.youth_name}</td>
                    <td>{row.partner}</td>
                    <td>
                      <WaitBadge days={row.days_waiting} threshold={data.confirmation_threshold} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.awaiting_partner_count > data.awaiting_partner.length && (
            <Link className="t-meta" style={{ display: "inline-block", marginTop: 10, fontWeight: 600 }} to="/referrals">
              {t("cm.viewAll", { n: data.awaiting_partner_count })}
            </Link>
          )}
          <div className="t-meta" style={{ marginTop: 8 }}>
            {t("cm.thresholdNote", { days: data.confirmation_threshold })}
          </div>
        </Card>

        <Card>
          <CapsLabel style={{ marginBottom: 10 }}>{t("cm.caseload")}</CapsLabel>
          <table className="table">
            <thead>
              <tr>
                <th>{t("cases.col.status")}</th>
                <th>{t("cm.cases")}</th>
                <th>{t("cm.oldest")}</th>
              </tr>
            </thead>
            <tbody>
              {data.caseload_by_status.map((row) => (
                <tr key={row.status}>
                  <td>
                    <Link to={`/cases?case_status=${row.status}`} style={{ textDecoration: "none" }}>
                      <CaseStatusChip status={row.status as CaseStatus} label={row.label} />
                    </Link>
                  </td>
                  <td className="tabular">{row.n}</td>
                  <td className="tabular">{row.n ? `${row.oldest_days}d` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card>
          <CapsLabel>{t("cm.atRisk")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("cm.atRiskWhy")}
          </div>
          {data.at_risk.length === 0 ? (
            <div className="t-meta">{t("cm.noneAtRisk")}</div>
          ) : (
            <div className="stack" style={{ gap: 0 }}>
              {data.at_risk.map((row) => (
                <Link
                  key={row.case}
                  to={`/cases/${row.case}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 10,
                    padding: "9px 0",
                    borderBottom: "1px solid var(--line)",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <span>
                    <span className="t-body-strong">{row.youth_name}</span>
                    <span className="t-meta" style={{ display: "block" }}>
                      {row.reason}
                    </span>
                  </span>
                  <MutedChip>{row.badge}</MutedChip>
                </Link>
              ))}
            </div>
          )}

          {data.at_risk_count > data.at_risk.length && (
            <Link className="t-meta" style={{ display: "inline-block", marginTop: 10, fontWeight: 600 }} to="/cases">
              {t("cm.viewAll", { n: data.at_risk_count })}
            </Link>
          )}

          {/* Naming the three conditions this cannot see, rather than implying
              it checked them. */}
          <div
            className="t-meta"
            style={{ marginTop: 12, padding: "9px 11px", borderRadius: "var(--r-group)", background: "var(--fill-muted)" }}
          >
            {t("cm.notInstrumented")}
            <ul style={{ margin: "6px 0 0", paddingInlineStart: 18 }}>
              {data.uninstrumented_risk.map((condition) => (
                <li key={condition}>{condition}</li>
              ))}
            </ul>
          </div>
        </Card>
      </div>
    </TierPage>
  );
}
