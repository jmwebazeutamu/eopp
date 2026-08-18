import type { OutcomeMatrix, PartnerPerformanceRow, ProgrammeTier, Rate } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { CapsLabel, Card, MutedChip } from "../ui";
import { RateValue } from "./Figure";

/**
 * The analytical cards — PM-3, PM-4, PM-7.
 *
 * Two of the handoff's chart rejections are enforced here rather than described:
 * the category-to-outcome table is a pivot with visible counts instead of a
 * Sankey, and the partner comparison is a league table sorted by evidence
 * instead of a sorted bar chart of rates.
 */

// A single-hue scale. Colour restates the count that is already printed in the
// cell, so nothing is encoded by colour alone.
const HEAT = ["var(--surface)", "#EAF2EE", "#CFE3DA", "#A9CFC1", "#6FB39C", "#2E8A6C"];

function heatFor(value: number, peak: number): string {
  if (value <= 0 || peak <= 0) return HEAT[0];
  const step = Math.ceil((value / peak) * (HEAT.length - 1));
  return HEAT[Math.min(HEAT.length - 1, Math.max(1, step))];
}

export function OutcomeMatrixPanel({ matrix }: { matrix: OutcomeMatrix }) {
  const { t } = useLang();
  const byKey = new Map(matrix.cells.map((cell) => [`${cell.category}:${cell.outcome}`, cell]));
  const peak = Math.max(0, ...matrix.cells.map((cell) => cell.n_referrals));

  return (
    <Card>
      <CapsLabel>{t("pm.matrix")}</CapsLabel>
      <div className="t-meta" style={{ margin: "2px 0 10px" }}>
        {t("pm.matrixWhy")}
      </div>

      {/* Scrolls inside its own box; the page body never scrolls sideways. */}
      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ minWidth: 520 }}>
          <thead>
            <tr>
              <th>{t("pm.matrix")}</th>
              {matrix.outcomes.map((outcome) => (
                <th key={outcome.code} style={{ textAlign: "end" }}>
                  {outcome.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.categories.map((category) => (
              <tr key={category.code}>
                <td style={{ whiteSpace: "nowrap" }}>{category.label}</td>
                {matrix.outcomes.map((outcome) => {
                  const cell = byKey.get(`${category.code}:${outcome.code}`);
                  const n = cell?.n_referrals ?? 0;
                  return (
                    <td
                      key={outcome.code}
                      className="tabular"
                      title={`${category.label} → ${outcome.label}: ${n}`}
                      style={{
                        textAlign: "end",
                        background: heatFor(n, peak),
                        fontWeight: n ? 600 : 400,
                        color: n ? "var(--ink-900)" : "var(--ink-400)",
                      }}
                    >
                      {n}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* G-1. A diagonal matrix is either a finding about the programme or a
          restatement of the lookup table, and the reader cannot tell which
          without this. As configured it is the second. */}
      {!matrix.crossovers_possible && (
        <div className="t-meta" style={{ marginTop: 8 }}>
          {t("pm.noCrossovers")}
        </div>
      )}
      {matrix.other.percent !== null && matrix.other.percent >= 20 && (
        <div className="t-meta" style={{ marginTop: 8, color: "var(--terra-700)" }}>
          <span aria-hidden style={{ marginInlineEnd: 4 }}>
            ▲
          </span>
          {t("pm.otherShare", { percent: matrix.other.percent, n: matrix.other.n, d: matrix.other.d })}
        </div>
      )}
      {matrix.not_recorded > 0 && (
        <div className="t-meta" style={{ marginTop: 8 }}>
          {t("pm.notRecorded", { n: matrix.not_recorded })}
        </div>
      )}
    </Card>
  );
}

const VERDICT_TONE: Record<string, { fg: string; bg: string }> = {
  above: { fg: "var(--green-ink)", bg: "var(--green-100)" },
  below: { fg: "var(--red-700)", bg: "var(--red-100)" },
  as_expected: { fg: "var(--ink-600)", bg: "var(--fill-muted)" },
  too_few: { fg: "var(--ink-400)", bg: "transparent" },
};

export function PartnerLeaguePanel({
  performance,
}: {
  performance: { overall_rate: Rate; partners: PartnerPerformanceRow[] };
}) {
  const { t } = useLang();

  return (
    <Card>
      <CapsLabel>{t("pm.partners")}</CapsLabel>
      <div className="t-meta" style={{ margin: "2px 0 2px" }}>
        {t("pm.partnersWhy")}
      </div>
      <div className="t-meta" style={{ marginBottom: 10 }}>
        {t("pm.overall", { rate: performance.overall_rate.percent ?? "—" })} · {t("pm.unitReferrals")}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table className="table" style={{ minWidth: 520 }}>
          <thead>
            <tr>
              <th>{t("partners.title")}</th>
              <th style={{ textAlign: "end" }}>{t("pm.closed")}</th>
              <th style={{ textAlign: "end" }}>{t("pm.completed")}</th>
              <th style={{ textAlign: "end" }}>{t("pm.rate")}</th>
              <th>{t("pm.verdict")}</th>
            </tr>
          </thead>
          <tbody>
            {performance.partners.map((row) => {
              const tone = VERDICT_TONE[row.verdict];
              return (
                <tr key={row.partner}>
                  <td>{row.partner}</td>
                  <td className="tabular" style={{ textAlign: "end" }}>
                    {row.closed}
                  </td>
                  <td className="tabular" style={{ textAlign: "end" }}>
                    {row.completed}
                  </td>
                  <td style={{ textAlign: "end" }}>
                    <RateValue rate={row.rate} />
                    {row.ci && (
                      <div className="t-meta tabular">
                        [{row.ci.lower}–{row.ci.upper}]
                      </div>
                    )}
                  </td>
                  <td>
                    {/* The verdict is a word and a mark, never a colour on its
                        own — and `too_few` is the honest answer for anything
                        outside the report band, because a verdict is a
                        comparison and the provisional band is never compared. */}
                    <span
                      className="chip"
                      style={{ color: tone.fg, background: tone.bg, borderColor: "transparent", whiteSpace: "nowrap" }}
                    >
                      {row.verdict_label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function ParallelLoadPanel({ load }: { load: ProgrammeTier["parallel_load"] }) {
  const { t } = useLang();
  return (
    <Card>
      <CapsLabel>{t("pm.parallel")}</CapsLabel>
      <div className="t-meta" style={{ margin: "2px 0 10px" }}>
        {t("pm.parallelWhy")}
      </div>
      <div className="tabular" style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.1 }}>
        {load.cases_with_parallel}
      </div>
      <div className="t-meta">{t("pm.parallelCases", { n: load.cases_with_parallel, total: load.cases_total })}</div>
      <div style={{ marginTop: 8 }}>
        {load.breaches_cap > 0 ? (
          <span className="chip" style={{ color: "var(--red-700)", background: "var(--red-100)", borderColor: "transparent" }}>
            <span className="chip__mark" aria-hidden>
              ▲
            </span>
            {t("pm.breaches", { n: load.breaches_cap })}
          </span>
        ) : (
          <MutedChip>{t("pm.breaches", { n: 0 })}</MutedChip>
        )}
      </div>
    </Card>
  );
}
