import type { ProgrammeTier } from "../../api/types";
import { MetricCards } from "../../components/dashboard/MetricCards";
import { OutcomeMatrixPanel, ParallelLoadPanel, PartnerLeaguePanel } from "../../components/dashboard/analytics";
import { AlertPanel, FunnelPanel, LagPanel, WoredaPanel } from "../../components/dashboard/panels";
import { CapsLabel, Card, MutedChip } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import TierPage from "./TierPage";
import { formatAsOf } from "../../i18n/asOf";
import { useTier } from "./useTier";

/**
 * The programme dashboard — the handoff's screen 8, for supervisors and the donor.
 *
 * One request for the whole screen: the brief's users are on 3G, where six round
 * trips cost more than the payload. Everything below is a pure render of it.
 *
 * The screen is scoped, not global. `scope_label` in the subtitle says what the
 * numbers cover — a supervisor's dashboard is their woredas, and reading it as
 * the programme's total would be the worst kind of wrong on a donor-facing
 * screen. §7 narrows the aggregate exactly as it narrows a list.
 *
 * Panels whose source entity is not built yet say so. Retention needs Placement
 * (§4.7, Sprint 5); a 0% there would read as a programme that retained nobody.
 */

/** PM-8. The same rows Tier 2 shows, because the gap costs both audiences. */
function HealthPanel({ rows }: { rows: ProgrammeTier["data_completeness"] }) {
  const { t } = useLang();
  return (
    <Card>
      <CapsLabel>{t("pm.health")}</CapsLabel>
      <table className="table" style={{ marginTop: 10 }}>
        <tbody>
          {rows.map((row) => (
            <tr key={row.field}>
              <td>{row.field}</td>
              <td className="tabular" style={{ textAlign: "end" }}>
                {!row.has_records ? (
                  <MutedChip>{t("ws.noRecords")}</MutedChip>
                ) : row.missing === 0 ? (
                  <MutedChip>{t("ws.complete")}</MutedChip>
                ) : (
                  t("ws.missing", { missing: row.missing, of: row.of })
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export default function ProgrammePage() {
  const { t } = useLang();

  const { data, loading } = useTier<ProgrammeTier>("/dashboard/programme/");

  return (
    <TierPage
      title={t("tier.programmeFull")}
      subtitle={
        data
          ? `${t("dash.subtitle", { period: data.period.label, scope: data.scope_label })} · ${t("pm.asOf", { when: formatAsOf(data.as_of) })}`
          : undefined
      }
    >

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {data && (
        <>
          <MetricCards metrics={data.metrics} />

          {/* auto-fit rather than the visibility helpers: these panels have no
              separate phone layout, they simply stop sitting side by side. One
              rule, so there is no way for both variants to render at once. */}
          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
            <FunnelPanel stages={data.funnel} />
            <LagPanel standardDays={data.confirmation_lag.standard_days} partners={data.confirmation_lag.partners} />
          </div>

          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
            <WoredaPanel rows={data.woredas} />
            <AlertPanel alerts={data.alerts} />
          </div>

          <PartnerLeaguePanel performance={data.partner_performance} />
          <OutcomeMatrixPanel matrix={data.outcome_matrix} />

          <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
            <ParallelLoadPanel load={data.parallel_load} />
            {/* G-13: PM-8 was computed and never rendered. */}
            <HealthPanel rows={data.data_completeness} />
          </div>
        </>
      )}
    </TierPage>
  );
}
