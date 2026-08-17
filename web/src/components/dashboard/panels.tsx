import type { ReactNode } from "react";

import type { FunnelStage, PartnerLag, ProgrammeDashboard, WoredaRow } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { ALERT_TONE } from "../../design/status";
import { CapsLabel, Card, MutedChip } from "../ui";
import { barPercent, funnelFill, lagScale, standardMarkPercent } from "./dashboardLayout";

/**
 * The programme dashboard's panels — the handoff's screen 8.
 *
 * Bars are hand-built divs on the token layer, per the brief: no chart library,
 * because the users are on 3G and a charting bundle costs more than every screen
 * in this app put together.
 *
 * Every bar is paired with its own number in text. The bar is the comparison;
 * the number is the fact. On a cheap LCD at half brightness in sunlight, the
 * number is the part that survives.
 */

/** A panel whose source entity has not been built yet. */
export function NotYet({ reason }: { reason: string }) {
  const { t } = useLang();
  return (
    <div>
      <div className="t-body-strong" style={{ color: "var(--ink-600)" }}>
        {t("dash.notYet")}
      </div>
      <div className="t-meta" style={{ marginTop: 4 }}>
        {reason}
      </div>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CapsLabel>{title}</CapsLabel>
      <div style={{ marginTop: 12 }}>{children}</div>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Registration → placement
// ---------------------------------------------------------------------------

export function FunnelPanel({ stages }: { stages: FunnelStage[] }) {
  const { t } = useLang();
  const drawable = stages.filter((stage) => stage.available);
  const top = drawable[0]?.count ?? 0;

  return (
    <Panel title={t("dash.funnel")}>
      {top === 0 && <div className="t-meta">{t("dash.empty")}</div>}
      <div className="stack" style={{ gap: 10 }}>
        {stages.map((stage, index) => (
          <div key={stage.key}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
              <span style={{ fontSize: 14 }}>{stage.label}</span>
              {stage.available ? (
                <span className="tabular" style={{ fontWeight: 600 }}>
                  {stage.count?.toLocaleString()}
                  <span className="t-meta" style={{ marginInlineStart: 6, fontWeight: 400 }}>
                    {stage.percent}%
                  </span>
                </span>
              ) : (
                <MutedChip>{t("dash.notYet")}</MutedChip>
              )}
            </div>

            {/* An unavailable stage draws an empty track rather than a zero-width
                fill: the row keeps its place in the funnel, and the absence is
                visibly an absence rather than a floor. */}
            <div className="track" style={{ height: 16, marginTop: 4 }} title={stage.available ? "" : stage.reason}>
              {stage.available && (
                <div
                  className="track__fill"
                  style={{
                    width: `${barPercent(stage.count ?? 0, top)}%`,
                    background: funnelFill(index, drawable.length),
                  }}
                />
              )}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Confirmation lag
// ---------------------------------------------------------------------------

export function LagPanel({ standardDays, partners }: { standardDays: number; partners: PartnerLag[] }) {
  const { t } = useLang();
  const scale = lagScale(
    partners.map((row) => row.days),
    standardDays,
  );
  const mark = standardMarkPercent(standardDays, scale);

  return (
    <Panel title={t("dash.lag")}>
      <div className="t-meta">{t("dash.lagIntro")}</div>
      <div className="t-meta" style={{ marginBottom: 12 }}>
        {t("dash.lagStandard", { days: standardDays })}
      </div>

      {partners.length === 0 ? (
        <div className="t-meta">{t("dash.lagNone")}</div>
      ) : (
        <div className="stack" style={{ gap: 10 }}>
          {partners.map((row) => (
            <div key={row.partner}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <span style={{ fontSize: 14 }}>{row.partner}</span>
                <span className="tabular" style={{ fontWeight: 600 }}>
                  {row.days === 1 ? t("dash.day") : t("dash.days", { days: row.days })}
                </span>
              </div>

              <div className="track" style={{ height: 12, marginTop: 4, position: "relative" }}>
                <div
                  className="track__fill"
                  style={{ width: `${barPercent(row.days, scale)}%`, background: "var(--gold-500)" }}
                />
                {/* The standard as a reference line, not a second colour: a
                    partner over it is read off the bar's own end crossing the
                    mark, which stays legible in monochrome. */}
                <span
                  aria-hidden
                  style={{
                    position: "absolute",
                    insetBlock: 0,
                    insetInlineStart: `${mark}%`,
                    width: 2,
                    background: "var(--ink-400)",
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Woreda comparison
// ---------------------------------------------------------------------------

export function WoredaPanel({ rows }: { rows: WoredaRow[] }) {
  const { t } = useLang();

  return (
    <Panel title={t("dash.woredas")}>
      {rows.length === 0 ? (
        <div className="t-meta">{t("dash.woredaNone")}</div>
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          {rows.map((row) => (
            <div key={row.woreda}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <span className="t-body-strong">{row.woreda}</span>
                <span className="tabular" style={{ fontWeight: 600 }}>
                  {row.rate}%
                </span>
              </div>
              {/* Every woreda is scaled against 100%, not against the leader:
                  the question is what share of registered youth reached work,
                  and a relative scale would make the best of a bad set look full. */}
              <div className="track" style={{ height: 20, marginTop: 4 }}>
                <div
                  className="track__fill"
                  style={{ width: `${barPercent(row.rate, 100)}%`, background: "var(--green-500)" }}
                />
              </div>
              <div className="t-meta" style={{ marginTop: 4 }}>
                {t("dash.woredaMeta", { registered: row.registered, placed: row.placed })}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Open alerts
// ---------------------------------------------------------------------------

export function AlertPanel({ alerts }: { alerts: ProgrammeDashboard["alerts"] }) {
  const { t } = useLang();

  return (
    <Panel title={t("dash.openAlerts")}>
      {alerts.open_total === 0 ? (
        <div className="t-meta">{t("dash.alertsNone")}</div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {alerts.by_type.map((row) => {
              const tone = ALERT_TONE[row.type] ?? { fg: "var(--ink-600)", bg: "var(--fill-muted)" };
              return (
                <span
                  key={row.type}
                  className="chip"
                  style={{ color: tone.fg, background: tone.bg, borderColor: "transparent" }}
                >
                  <span className="tabular" style={{ fontWeight: 700, marginInlineEnd: 6 }}>
                    {row.count}
                  </span>
                  {row.type.replaceAll("_", " ").toLowerCase()}
                </span>
              );
            })}
          </div>
          {alerts.stalled_cases > 0 && (
            <div className="t-meta" style={{ marginTop: 10 }}>
              {t("dash.stalledCases", { count: alerts.stalled_cases })}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
