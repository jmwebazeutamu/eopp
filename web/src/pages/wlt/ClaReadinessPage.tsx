import { App } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { ClaReadinessRow } from "../../api/types";
import { Card, CapsLabel, PageHeader, ProgressTrack } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * CLA readiness by kebele.
 *
 * "This screen drives facilitator behaviour more than any report. Make it
 * prominent" — the handoff, backlog S8.3. The number that does the work is
 * `groups_short`: "two more groups at Phase 2 and this kebele can form a CLA"
 * is something a facilitator can act on this quarter, where a phase
 * distribution is something she can only read.
 *
 * Sorted by how close each kebele is, so the ones within reach are at the top.
 * Bars are hand-built divs — no chart library, per the brief's 3G constraint.
 */
export default function ClaReadinessPage() {
  const { message } = App.useApp();
  const { t } = useLang();

  const [rows, setRows] = useState<ClaReadinessRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<{ rows: ClaReadinessRow[] }>("/wlt/reports/cla-readiness/");
      setRows(response.data.rows);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.claLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const ready = rows.filter((row) => row.groups_short === 0);

  return (
    <div className="page stack">
      <PageHeader title={t("wlt.claTitle")} subtitle={t("wlt.claSubtitle")} />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {!loading && rows.length === 0 && <Card>{t("wlt.claEmpty")}</Card>}

      {ready.length > 0 && (
        <Card>
          <CapsLabel>{t("wlt.claReadyNow")}</CapsLabel>
          <p>{t("wlt.claReadyBody", { count: ready.length })}</p>
        </Card>
      )}

      <div className="stack">
        {rows.map((row) => {
          const progress = row.threshold ? Math.min(1, row.eligible_groups / row.threshold) : 0;
          return (
            <Card key={row.kebele_id}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                <strong>{row.kebele}</strong>
                <span className="t-meta">
                  {/* Actual next to threshold, the same rule as the readiness
                      card. "3 of 8" says more than "38%". */}
                  {t("wlt.ofThreshold", { actual: row.eligible_groups, threshold: row.threshold })}
                </span>
              </div>
              <ProgressTrack value={progress} />
              <div className="t-meta" style={{ marginTop: 6 }}>
                {row.groups_short === 0
                  ? t("wlt.claCanForm")
                  : t("wlt.claShort", { count: row.groups_short })}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
