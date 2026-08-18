import type { ReactNode } from "react";

import type { FunnelStage, PartnerLag, ProgrammeDashboard, WoredaRow } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { ALERT_TONE } from "../../design/status";
import { CapsLabel, Card, MutedChip } from "../ui";
import { MeanValue, ProvisionalNote, RateValue } from "./Figure";
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
      <div className="t-meta" style={{ marginTop: -6 }}>
        {t("dash.funnelWhy")}
      </div>
      {/* G-6: the partner cards count referrals and this counts youth. Both are
          right, and unlabelled they read as a contradiction. */}
      <div className="t-meta" style={{ marginBottom: 12 }}>
        {t("pm.unitYouth")} {t("pm.emphasis")}
      </div>

      {top === 0 && <div className="t-meta">{t("dash.empty")}</div>}

      {stages.map((stage, index) => (
        <div key={stage.key}>
          {/* Label · shared-baseline track · value. The baseline is shared so
              two stages can be compared by eye; a funnel's taper cannot be. */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(96px, 148px) 1fr auto",
              gap: 10,
              alignItems: "center",
            }}
          >
            <div>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{stage.label}</div>
              <div className="t-meta" style={{ fontSize: 11 }}>
                {stage.sublabel}
              </div>
            </div>

            <div className="track" style={{ height: 16 }} title={stage.available ? "" : stage.reason}>
              {stage.available && (
                <div
                  className="track__fill"
                  style={{
                    width: `${barPercent(stage.count ?? 0, top)}%`,
                    background: stage.gating ? funnelFill(index, drawable.length) : "var(--fill-muted-2)",
                  }}
                />
              )}
            </div>

            <div style={{ textAlign: "end", minWidth: 74 }}>
              {stage.available && stage.share ? (
                <>
                  <div className="tabular" style={{ fontWeight: 700 }}>
                    {stage.count?.toLocaleString()}
                  </div>
                  <div style={{ fontSize: 12 }}>
                    <RateValue rate={stage.share} bold={false} />
                  </div>
                </>
              ) : (
                <MutedChip>{t("dash.notYet")}</MutedChip>
              )}
            </div>
          </div>

          {/* The loss on the way out of this stage, annotated between the rows
              rather than left to be subtracted. The mark carries it in
              monochrome; the words carry it without colour at all. */}
          {stage.lost && (
            <div
              className="t-meta"
              style={{ padding: "5px 0 5px 10px", marginBlock: 2, borderInlineStart: "2px solid var(--line)" }}
            >
              <span aria-hidden style={{ marginInlineEnd: 4 }}>
                ▼
              </span>
              <strong style={{ color: "var(--terra-700)" }}>
                {stage.lost.share.percent === null
                  ? t("dash.lostUnknown", { count: stage.lost.count })
                  : t("dash.lost", { count: stage.lost.count, percent: stage.lost.share.percent })}
              </strong>
              {" "}
              {t("dash.lostTo", { stage: stage.lost.to_label })}
              {/* The duration is the one for THIS transition. It used to read
                  the next row's median, which after the coverage rows landed
                  between the gates was a different transition entirely. */}
              {stage.lost.median_days !== null && (
                <> · {t("dash.medianInStage", { days: stage.lost.median_days })}</>
              )}
            </div>
          )}
        </div>
      ))}

      <ProvisionalNote shown={stages.some((stage) => stage.share?.band === "provisional")} />
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Confirmation lag
// ---------------------------------------------------------------------------

export function LagPanel({ standardDays, partners }: { standardDays: number; partners: PartnerLag[] }) {
  const { t } = useLang();
  // Only the means that survived banding can be scaled against; a withheld mean
  // has no bar, which is the point.
  const scale = lagScale(
    partners.map((row) => row.median_days).filter((days): days is number => days !== null),
    standardDays,
  );
  const mark = standardMarkPercent(standardDays, scale);

  return (
    <Panel title={t("dash.lag")}>
      <div className="t-meta">{t("dash.lagIntro")}</div>
      <div className="t-meta">{t("dash.lagStandard", { days: standardDays })}</div>
      <div className="t-meta" style={{ marginBottom: 12 }}>
        {t("dash.lagOrder")}
      </div>

      {partners.length === 0 ? (
        <div className="t-meta">{t("dash.lagNone")}</div>
      ) : (
        <div className="stack" style={{ gap: 10 }}>
          {partners.map((row) => (
            <div key={row.partner}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                <span style={{ fontSize: 14 }}>{row.partner}</span>
                <MeanValue mean={{ days: row.median_days, n: row.n, band: row.band, note: "" }} />
              </div>

              <div className="track" style={{ height: 12, marginTop: 4, position: "relative" }}>
                {row.median_days !== null && (
                  <div
                    className="track__fill"
                    style={{ width: `${barPercent(row.median_days, scale)}%`, background: "var(--gold-500)" }}
                  />
                )}
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
              <div className="t-meta" style={{ marginTop: 2 }}>
                {t("dash.lagReferrals", { count: row.n })}
                {row.staff_recorded > 0 && <> · {t("ws.staffRecorded", { count: row.staff_recorded })}</>}
              </div>
            </div>
          ))}
          <ProvisionalNote shown={partners.some((row) => row.band === "provisional")} />
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
                <RateValue rate={row.rate} />
              </div>
              {/* Every woreda is scaled against 100%, not against the leader:
                  the question is what share of registered youth reached work,
                  and a relative scale would make the best of a bad set look full. */}
              <div className="track" style={{ height: 20, marginTop: 4 }}>
                {row.rate.percent !== null && (
                  <div
                    className="track__fill"
                    style={{ width: `${barPercent(row.rate.percent, 100)}%`, background: "var(--green-500)" }}
                  />
                )}
              </div>
              <div className="t-meta" style={{ marginTop: 4 }}>
                {t("dash.woredaMeta", { registered: row.registered, placed: row.placed })}
              </div>
            </div>
          ))}
          <ProvisionalNote shown={rows.some((row) => row.rate.band === "provisional")} />
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
