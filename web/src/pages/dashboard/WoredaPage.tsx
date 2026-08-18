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

/** A tile. `null` renders as an em dash — a withheld median is not a zero. */
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
    <Card style={tone ? { background: bg[tone], borderColor: bd[tone] } : undefined}>
      <CapsLabel>{label}</CapsLabel>
      <div className="tabular" style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.1, marginTop: 4 }}>
        {value === null ? "—" : value}
      </div>
      <div className="t-meta">{meta}</div>
    </Card>
  );
}

function Completeness({ rows }: { rows: CompletenessRow[] }) {
  const { t } = useLang();
  return (
    <table className="table">
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
                t("ws.missing", { missing: row.missing, of: row.of })
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
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
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

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
        <Card style={{ gridColumn: "1 / -1" }}>
          <CapsLabel>{t("ws.team")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 12px" }}>
            {t("ws.teamWhy")}
          </div>

          <div className="stack" style={{ gap: 12 }}>
            {data.team_caseload.map((row) => (
              <div key={row.case_manager ?? row.name}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "baseline" }}>
                  <span className="t-body-strong">{row.name}</span>
                  <span className="t-meta tabular">
                    {t("ws.caseload")} {row.total}
                    {row.over_ceiling && (
                      <span
                        className="chip"
                        style={{
                          color: "var(--terra-700)",
                          background: "var(--terra-100)",
                          borderColor: "transparent",
                          marginInlineStart: 8,
                        }}
                      >
                        <span className="chip__mark" aria-hidden>
                          ▲
                        </span>
                        {t("ws.ceilingFlag")}
                      </span>
                    )}
                    {row.overdue > 0 && (
                      <span style={{ color: "var(--red-700)", fontWeight: 700, marginInlineStart: 10 }}>
                        ▲ {row.overdue} {t("ws.overdue").toLowerCase()}
                      </span>
                    )}
                  </span>
                </div>

                {/* Scaled against the largest caseload, so two managers are
                    compared by length as well as by number. */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
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
                          {(n / row.total) * 100 >= 12 ? n : ""}
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
                        return n > 0 && (n / row.total) * 100 < 12;
                      })
                      .map((segment) => `${segment.label} ${row.segments[segment.key]}`)
                      .join(" · ")}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="t-meta" style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
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
        </Card>

        <Card>
          <CapsLabel>{t("ws.unassigned")}</CapsLabel>
          <div style={{ marginTop: 8 }}>
            <NotYet reason={data.unassigned_youth.reason} />
          </div>
          <div className="card__rule" style={{ margin: "12px 0" }} />
          <CapsLabel>{t("ws.noCaseYet")}</CapsLabel>
          <div className="tabular" style={{ fontSize: 30, fontWeight: 700, lineHeight: 1.1 }}>
            {data.registered_without_case}
          </div>
        </Card>

        <Card>
          <CapsLabel>{t("ws.response")}</CapsLabel>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("ws.responseWhy")}
          </div>
          <table className="table">
            <thead>
              <tr>
                <th scope="col">{t("partners.one")}</th>
                <th scope="col">{t("ws.medianDays")}</th>
                <th scope="col">{t("ws.confirmedReferrals")}</th>
              </tr>
            </thead>
            <tbody>
              {data.partner_response.map((row) => (
                <tr key={row.partner}>
                  <td>{row.partner}</td>
                  <td className="tabular">
                    {row.median_days === null ? (
                      <span style={{ color: "var(--ink-400)" }}>— {t("dash.tooFew")}</span>
                    ) : (
                      `${row.median_days}d${row.band === "provisional" ? "*" : ""}`
                    )}
                  </td>
                  <td className="tabular t-meta">
                    {row.n}
                    {row.staff_recorded > 0 && (
                      <div style={{ color: "var(--ink-400)" }}>{t("ws.staffRecorded", { count: row.staff_recorded })}</div>
                    )}
                  </td>
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
        </Card>
      </div>
    </TierPage>
  );
}
