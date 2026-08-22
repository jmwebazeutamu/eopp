import { App } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { FederationReadinessRow } from "../../api/types";
import { Card, CapsLabel, PageHeader, ProgressTrack } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * Federation readiness by woreda — the CLA screen one level up.
 *
 * That screen counts groups in a kebele against the CLA threshold; this counts
 * CLAs in a woreda against the federation threshold. Deliberately the same
 * shape, because a facilitator who has learned to read one should not have to
 * learn the other: actual beside threshold, a bar, and the shortfall written
 * out as the thing to do next.
 *
 * Maturity is shown beside membership because the gate has two conditions. Ten
 * CLAs formed last month is not the readiness that ten established ones are,
 * and a screen reporting only the count would say a woreda was ready when the
 * gate would refuse it.
 *
 * Sorted by how close each woreda is, so anything within reach leads.
 */
export default function FederationReadinessPage() {
  const { message } = App.useApp();
  const { t } = useLang();

  const [rows, setRows] = useState<FederationReadinessRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<{ rows: FederationReadinessRow[] }>("/wlt/reports/federation-readiness/");
      setRows(response.data.rows);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.federationLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const ready = rows.filter((row) => row.clas_short === 0);

  return (
    <div className="page stack">
      <PageHeader title={t("wlt.federationTitle")} subtitle={t("wlt.federationSubtitle")} />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {!loading && rows.length === 0 && <Card>{t("wlt.federationEmpty")}</Card>}

      {ready.length > 0 && (
        <Card>
          <CapsLabel>{t("wlt.federationReadyNow")}</CapsLabel>
          <p>{t("wlt.federationReadyBody", { count: ready.length })}</p>
        </Card>
      )}

      {/* Said once, at the top, rather than on every row. The arithmetic is
          the point: the gate needs more groups in one woreda than the largest
          regional allocation holds, so a woreda short of the threshold is the
          expected reading rather than a failure. */}
      {!loading && rows.length > 0 && ready.length === 0 && (
        <Card className="card--muted">
          <p style={{ margin: 0 }}>{t("wlt.federationNotYet")}</p>
        </Card>
      )}

      <div className="stack">
        {rows.map((row) => {
          const progress = row.threshold ? Math.min(1, row.active_clas / row.threshold) : 0;
          return (
            <Card key={row.woreda_id}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                <strong>{row.woreda}</strong>
                <span className="t-meta">
                  {/* Actual next to threshold, the same rule as the readiness
                      card and the CLA screen. "3 of 10" says more than "30%". */}
                  {t("wlt.ofThreshold", { actual: row.active_clas, threshold: row.threshold })}
                </span>
              </div>
              <ProgressTrack value={progress} />
              <div className="t-meta" style={{ marginTop: 6 }}>
                {row.clas_short === 0 ? t("wlt.federationCanForm") : t("wlt.federationShort", { count: row.clas_short })}
                {row.active_clas > 0 && ` · ${t("wlt.federationMature", { count: row.mature_clas })}`}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
