import type { CompletenessRow, WoredaDashboard } from "../../api/types";
import { CapsLabel, Card, MutedChip } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import TierPage from "./TierPage";
import { NotYet } from "../../components/dashboard/panels";
import { formatAsOf } from "../../i18n/asOf";
import { useTier } from "./useTier";

/**
 * Tier 2 — woreda supervisor. "Which staff, which cases need me?"
 *
 * README §4's forbidden list: no donor indicators, no annual targets, and no
 * unadjusted staff leaderboards. So the team table shows **counts beside each
 * other**, never a per-staff rate: at one case manager's caseload a rate is
 * noise, and publishing one creates cream-skimming pressure with nothing gained.
 */

// Four segments, not six. Six adjacent segments cannot hold WCAG 1.4.11's 3:1
// non-text contrast against each other, which is what caps the stack — not
// taste. Each also carries its own count as a label, so identity never rests on
// colour alone.
const SEGMENT_FILL: Record<string, string> = {
  on_track: "var(--green-500)",
  awaiting_partner: "var(--gold-500)",
  stalled: "var(--terra-500)",
  closed: "var(--cancelled-bar)",
};

/**
 * Whether a segment is wide enough to hold its own count.
 *
 * Measured against the *track*, not against the manager's own caseload. Every
 * bar is scaled by `row.total / biggest`, so a segment's rendered width is its
 * share of the largest caseload — testing its share of its own row put numbers
 * inside segments a few pixels wide on a small caseload, and the outside-label
 * fallback was keyed off the same test so it never fired.
 *
 * ~6% of the track is about 40px at the widths this card is drawn at.
 */
const INLINE_LABEL_MIN_TRACK_PERCENT = 6;

function fitsInline(n: number, biggest: number): boolean {
  return (n / biggest) * 100 >= INLINE_LABEL_MIN_TRACK_PERCENT;
}

/**
 * A KPI tile. `null` renders as an em dash — a withheld median is not a zero.
 *
 * Laid out as three fixed rows rather than stacked content, so label, value and
 * caption share a baseline across the row whatever wraps. Two labels wrap to a
 * second line ("Registered, no case yet", "Median days to confirm") and one
 * caption does, which previously pushed each card's number to a different
 * height — five cards of equal height with nothing lining up inside them.
 *
 * `1fr` on the caption row is what pins the captions to a common bottom.
 */
function StatTile({
  label,
  value,
  meta,
  tone,
}: {
  label: string;
  value: number | null;
  meta: string;
  tone?: "warn" | "good";
}) {
  const bg = { warn: "var(--gold-100)", good: "var(--green-100)" };
  const bd = { warn: "var(--gold-border)", good: "var(--green-border)" };
  return (
    <Card
      style={{
        display: "grid",
        gridTemplateRows: "auto auto 1fr",
        gap: 4,
        ...(tone ? { background: bg[tone], borderColor: bd[tone] } : {}),
      }}
    >
      {/* Two lines reserved, so a label that wraps does not move its own
          number down relative to the card beside it. */}
      <CapsLabel style={{ minHeight: "2.2em" }}>{label}</CapsLabel>
      <div
        className="tabular"
        style={{
          fontSize: 30,
          fontWeight: 700,
          lineHeight: 1.1,
          // The withheld case is muted text on the same line box as a number,
          // not a bare glyph floating between the label and the caption.
          color: value === null ? "var(--ink-400)" : undefined,
        }}
      >
        {value === null ? "—" : value}
      </div>
      <div className="t-meta">{meta}</div>
    </Card>
  );
}

function Completeness({ rows }: { rows: CompletenessRow[] }) {
  const { t } = useLang();
  return (
    <table className="table table--fixed">
      <colgroup>
        <col style={{ width: "30%" }} />
        <col style={{ width: "20%" }} />
        <col style={{ width: "50%" }} />
      </colgroup>
      <thead>
        <tr>
          <th scope="col">{t("me.indicator")}</th>
          <th scope="col">{t("ws.missingCol")}</th>
          <th scope="col">{t("ws.cost")}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.field}>
            <td>{row.field}</td>
            <td className="tabular">
              {!row.has_records ? (
                <MutedChip>{t("ws.noRecords")}</MutedChip>
              ) : row.missing === 0 ? (
                <MutedChip>{t("ws.complete")}</MutedChip>
              ) : (
                <span
                  className="chip"
                  style={{ color: "var(--gold-700)", background: "var(--gold-100)", borderColor: "transparent" }}
                >
                  {t("ws.missing", { missing: row.missing, of: row.of })}
                </span>
              )}
            </td>
            <td className="t-meta">{row.cost}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function WoredaPage() {
  const { t } = useLang();
  const { data, loading } = useTier<WoredaDashboard>("/dashboard/woreda/");

  if (loading && !data) return <div className="t-meta">{t("common.loading")}</div>;
  if (!data) return null;

  const biggest = Math.max(1, ...data.team_caseload.map((row) => row.total));

  return (
    <TierPage
      title={t("tier.woredaFull")}
      subtitle={`${t("tier.woredaWhy")} · ${data.scope_label} · ${t("ws.asOf", { when: formatAsOf(data.as_of) })}`}
    >

      {/* W-5. Four of these were already computed further down the page and
          only needed surfacing; the fifth is the ceiling nobody was reading. */}
      <div className="kpi-row">
        <StatTile label={t("ws.openCases")} value={data.tiles.open_cases} meta={data.scope_label} />
        <StatTile
          label={t("ws.overdueActions")}
          value={data.tiles.overdue_actions}
          meta={t("ws.acrossTeam")}
          tone={data.tiles.overdue_actions ? "warn" : undefined}
        />
        {/* The overdue-confirmation count used to sit under this tile, which
            counts youth with no case — two unrelated metrics on one card. */}
        <StatTile
          label={t("ws.noCaseYet")}
          value={data.tiles.registered_without_case}
          meta={t("ws.noCaseMeta")}
        />
        <StatTile
          label={t("ws.medianConfirm")}
          value={data.tiles.median_days_to_confirm}
          meta={t("ws.awaitingAlerts", { count: data.awaiting_partner_alerts })}
        />
        <StatTile
          label={t("ws.verified")}
          value={data.tiles.outcomes_verified}
          meta={t("ws.thisMonth", { recorded: data.tiles.outcomes_recorded })}
          tone="good"
        />
      </div>

      <div className="dash-grid">
        <Card style={{ gridColumn: "1 / -1" }}>
          <CapsLabel>{t("ws.team")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 8px" }}>
            {t("ws.teamWhy")}
          </div>
          <div className="t-meta" style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "0 0 12px" }}>
            {data.segments.map((segment) => (
              <span key={segment.key}>
                <span
                  aria-hidden
                  style={{
                    display: "inline-block",
                    width: 10,
                    height: 10,
                    borderRadius: 2,
                    background: SEGMENT_FILL[segment.key],
                    marginInlineEnd: 5,
                  }}
                />
                {segment.label}
              </span>
            ))}
          </div>

          <div className="stack" style={{ gap: 12 }}>
            {data.team_caseload.map((row) => (
              <div key={row.case_manager ?? row.name}>
                <div className="team-row__head">
                  <span className="t-body-strong">{row.name}</span>
                  <span className="t-meta tabular team-row__fact">
                    {t("ws.caseload")} {row.total}
                  </span>
                  <span className="team-row__fact">
                    {row.over_ceiling && (
                      <span
                        className="chip"
                        style={{
                          color: "var(--terra-700)",
                          background: "var(--terra-100)",
                          borderColor: "transparent",
                        }}
                      >
                        <span className="chip__mark" aria-hidden>
                          ▲
                        </span>
                        {t("ws.ceilingFlag")}
                      </span>
                    )}
                  </span>
                  {/* Both warnings on this row are chips now. One was a chip
                      and the other bare red bold text, on the same line. */}
                  <span className="team-row__fact">
                    {row.overdue > 0 && (
                      <span
                        className="chip"
                        style={{
                          color: "var(--red-700)",
                          background: "var(--red-100)",
                          borderColor: "transparent",
                        }}
                      >
                        <span className="chip__mark" aria-hidden>
                          ▲
                        </span>
                        {row.overdue} {t("ws.overdue").toLowerCase()}
                      </span>
                    )}
                  </span>
                </div>

                {/* Scaled against the largest caseload, so two managers are
                    compared by length as well as by number. */}
                <div className="team-row__bar">
                  <div
                    style={{
                      display: "flex",
                      height: 22,
                      borderRadius: "var(--r-group)",
                      overflow: "hidden",
                      width: `${(row.total / biggest) * 100}%`,
                    }}
                  >
                    {data.segments.map((segment) => {
                      const n = row.segments[segment.key] ?? 0;
                      if (!n) return null;
                      return (
                        <span
                          key={segment.key}
                          title={`${segment.label}: ${n}`}
                          style={{
                            flex: `0 0 ${(n / row.total) * 100}%`,
                            background: SEGMENT_FILL[segment.key],
                            color: segment.key === "awaiting_partner" ? "var(--ink-900)" : "var(--on-dark)",
                            fontSize: 12,
                            fontWeight: 700,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            overflow: "hidden",
                          }}
                        >
                          {fitsInline(n, biggest) ? n : ""}
                        </span>
                      );
                    })}
                  </div>
                  {/* Every segment carries its count. The ones too narrow to
                      hold a label inside put it here rather than losing it. */}
                  <span className="t-meta tabular" style={{ whiteSpace: "nowrap" }}>
                    {data.segments
                      .filter((segment) => {
                        const n = row.segments[segment.key] ?? 0;
                        return n > 0 && !fitsInline(n, biggest);
                      })
                      .map((segment) => `${segment.label} ${row.segments[segment.key]}`)
                      .join(" · ")}
                  </span>
                </div>
              </div>
            ))}
          </div>

        </Card>


        <Card style={{ gridColumn: "1 / -1" }}>
          <CapsLabel>{t("ws.response")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("ws.responseWhy")}
          </div>
          <table className="table table--fixed">
            <colgroup>
              <col style={{ width: "40%" }} />
              <col style={{ width: "20%" }} />
              <col style={{ width: "20%" }} />
              <col style={{ width: "20%" }} />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">{t("partners.one")}</th>
                <th scope="col">{t("ws.medianDays")}</th>
                <th scope="col">{t("ws.confirmedReferrals")}</th>
                {/* Was stacked under the count above, so one cell carried two
                    unrelated facts and wrapped under its own header. */}
                <th scope="col">{t("ws.staffRecordedCol")}</th>
              </tr>
            </thead>
            <tbody>
              {data.partner_response.map((row) => (
                <tr key={row.partner}>
                  <td>{row.partner}</td>
                  <td className="tabular">
                    {row.median_days === null ? (
                      <span style={{ color: "var(--ink-400)", whiteSpace: "nowrap" }}>— {t("dash.tooFew")}</span>
                    ) : (
                      `${row.median_days}d${row.band === "provisional" ? "*" : ""}`
                    )}
                  </td>
                  <td className="tabular">{row.n}</td>
                  <td className="tabular t-meta">{row.staff_recorded > 0 ? row.staff_recorded : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="t-meta" style={{ marginTop: 8 }}>
            {t("ws.staffRecordedNote")}
          </div>
        </Card>

        <Card style={{ gridColumn: "1 / -1" }}>
          <CapsLabel>{t("ws.completeness")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("ws.completenessWhy")}
          </div>
          <Completeness rows={data.data_completeness} />

          {/* Folded in from the "Unassigned youth" card, which held only this
              message plus a copy of the "Registered, no case yet" tile at the
              top of the page. Both panels answer the same question — what this
              dashboard cannot tell you — and the card it came from stretched to
              match the table beside it, leaving ~500px of white. */}
          <div className="card__rule" style={{ margin: "16px 0 12px" }} />
          <CapsLabel>{t("ws.unassigned")}</CapsLabel>
          <div style={{ marginTop: 8 }}>
            <NotYet reason={data.unassigned_youth.reason} />
          </div>
        </Card>
      </div>
    </TierPage>
  );
}
