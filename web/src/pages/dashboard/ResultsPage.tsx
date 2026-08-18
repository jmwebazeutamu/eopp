import type { DonorDashboard } from "../../api/types";
import { CapsLabel, Card, PageHeader } from "../../components/ui";
import { NotYet } from "../../components/dashboard/panels";
import { RateValue } from "../../components/dashboard/Figure";
import { barPercent } from "../../components/dashboard/dashboardLayout";
import { useLang } from "../../i18n/LanguageContext";
import { useTier } from "./useTier";

/**
 * Tier 4 — M&E and the donor. "Are we hitting targets?"
 *
 * README §6: the smallest of the four dashboards, and nothing on it may need
 * more than a sentence to define. Indicator wording is verbatim from the parent
 * operations (PSNP 5 / SEASN, the Jobs M&E Toolkit, UPSNJP) so woreda figures
 * roll up without reconciliation — do not improve the phrasing.
 *
 * The trend is one axis with both series in counts, direct-labelled. Never a
 * dual axis, which invents correlations that are not in the data, and never a
 * gauge, which spends a whole card on one number with no comparative context.
 */
export default function ResultsPage() {
  const { t } = useLang();
  const { data, loading } = useTier<DonorDashboard>("/dashboard/results/");

  if (loading && !data) return <div className="t-meta">{t("common.loading")}</div>;
  if (!data) return null;

  const peak = Math.max(1, ...data.cumulative.series.map((row) => row.cumulative));

  return (
    <>
      <PageHeader
        title={t("tier.resultsFull")}
        subtitle={`${data.scope_label} · ${t("tier.asOf", { when: new Date(data.as_of).toLocaleDateString() })}`}
      />

      <Card>
        <CapsLabel style={{ marginBottom: 10 }}>{t("me.framework")}</CapsLabel>
        <table className="table">
          <thead>
            <tr>
              <th>{t("me.indicator")}</th>
              <th>{t("me.value")}</th>
              <th>{t("me.source")}</th>
            </tr>
          </thead>
          <tbody>
            {data.indicators.map((indicator) => (
              <tr key={indicator.code}>
                <td>
                  <div className="t-body-strong">{indicator.label}</div>
                  {indicator.reason && (
                    <div className="t-meta" style={{ marginTop: 2 }}>
                      {indicator.reason}
                    </div>
                  )}
                </td>
                <td className="tabular" style={{ whiteSpace: "nowrap" }}>
                  {!indicator.available ? (
                    <span style={{ color: "var(--ink-400)" }}>{t("dash.notYet")}</span>
                  ) : indicator.kind === "count" ? (
                    <span style={{ fontWeight: 700 }}>{indicator.value?.toLocaleString()}</span>
                  ) : indicator.rate ? (
                    <>
                      <RateValue rate={indicator.rate} />
                      <div className="t-meta">{t("dash.ofCount", { n: indicator.rate.n, d: indicator.rate.d })}</div>
                      {/* The recorded rate sits beside the verified one, never
                          instead of it: the card used to show recorded under a
                          "verified" label. */}
                      {indicator.recorded && indicator.recorded.percent !== null && (
                        <div className="t-meta" style={{ marginTop: 4 }}>
                          {t("me.recordedBeside", {
                            percent: indicator.recorded.percent,
                            n: indicator.recorded.n,
                            d: indicator.recorded.d,
                          })}
                        </div>
                      )}
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="t-meta">{indicator.framework}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))" }}>
        <Card>
          <CapsLabel>{t("me.cumulative")}</CapsLabel>
          <div className="t-meta" style={{ marginTop: 2 }}>
            {t("me.cumulativeUnit", { unit: data.cumulative.unit })}
            {data.cumulative.opening_balance > 0 &&
              ` · ${t("me.openingBalance", { n: data.cumulative.opening_balance })}`}
          </div>
          <div className="t-meta" style={{ margin: "2px 0 10px" }}>
            {t("me.cumulativeWhy")}
          </div>
          {/* Hand-built bars, one series, counts on one scale. */}
          <div className="stack" style={{ gap: 6 }}>
            {data.cumulative.series.map((row) => (
              <div key={row.month} style={{ display: "grid", gridTemplateColumns: "72px 1fr auto", gap: 8, alignItems: "center" }}>
                <span className="t-meta tabular">{row.month.slice(0, 7)}</span>
                <div className="track" style={{ height: 12 }}>
                  <div
                    className="track__fill"
                    style={{ width: `${barPercent(row.cumulative, peak)}%`, background: "var(--green-500)" }}
                  />
                </div>
                <span className="tabular" style={{ fontWeight: 600, minWidth: 58, textAlign: "end" }}>
                  {row.cumulative}
                  <span className="t-meta" style={{ fontWeight: 400 }}> (+{row.placed})</span>
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CapsLabel>{t("dash.retained")}</CapsLabel>
          <div style={{ marginTop: 8 }}>
            <NotYet reason={data.retention.reason} />
          </div>
        </Card>
      </div>

      <Card>
        <CapsLabel style={{ marginBottom: 10 }}>{t("me.disaggregation")}</CapsLabel>
        <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))" }}>
          {data.disaggregation.map((cut) => (
            <div key={cut.label}>
              <div className="t-body-strong" style={{ marginBottom: 4 }}>
                {cut.label}
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th />
                    <th>{t("me.registered")}</th>
                    <th>{t("me.placed")}</th>
                    <th>{t("pm.rate")}</th>
                  </tr>
                </thead>
                <tbody>
                  {cut.rows.map((row) => (
                    <tr key={row.value}>
                      <td>{row.value}</td>
                      <td className="tabular">{row.registered}</td>
                      <td className="tabular">{row.placed}</td>
                      <td>
                        <RateValue rate={row.rate} bold={false} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
        <div className="t-meta" style={{ marginTop: 10 }}>
          {t("me.noRural")}
        </div>
      </Card>

      {/* ME-5. A sentence beats another chart, and these are the two caveats
          the handoff requires by name. */}
      <Card>
        <CapsLabel>{t("me.caveats")}</CapsLabel>
        <ul style={{ margin: "8px 0 0", paddingInlineStart: 18 }}>
          {data.caveats.map((caveat) => (
            <li key={caveat} style={{ marginBottom: 6 }}>
              {caveat}
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
