import { App } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { ProgrammeDashboard } from "../api/types";
import { MetricCards } from "../components/dashboard/MetricCards";
import { AlertPanel, FunnelPanel, LagPanel, WoredaPanel } from "../components/dashboard/panels";
import { PageHeader } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

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

export default function DashboardPage() {
  const { message } = App.useApp();
  const { t } = useLang();

  const [data, setData] = useState<ProgrammeDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<ProgrammeDashboard>("/dashboard/");
      setData(response.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load the dashboard."));
    } finally {
      setLoading(false);
    }
  }, [message]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page stack">
      <PageHeader
        title={t("dash.title")}
        subtitle={data ? t("dash.subtitle", { period: data.period.label, scope: data.scope_label }) : undefined}
      />

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
        </>
      )}
    </div>
  );
}
