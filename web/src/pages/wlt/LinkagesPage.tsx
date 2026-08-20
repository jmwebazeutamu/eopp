import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Paginated, ServiceLinkage, Summary } from "../../api/types";
import ListPage from "../../components/ListPage";
import { Card, CapsLabel } from "../../components/ui";
import { LINKAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The linkage list, and the blocked-gate screen.
 *
 * The handoff calls `BLOCKED` "the single most behaviour-changing screen in the
 * module", and the reason is the reasons: a blocked linkage carries the
 * sentences saying what the subject still needs to reach, each with the actual
 * value beside the threshold. Those same sentences aggregate into the funnel's
 * block reasons, which is the evidence for adjusting a threshold rather than
 * guessing at one.
 *
 * Blocked renders gold, not red. It is a subject that has not got there yet,
 * and most of them will; red is reserved for genuine failure, which here means
 * a defaulted obligation.
 */
export default function LinkagesPage() {
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<ServiceLinkage[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const status = params.get("status") ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, counters] = await Promise.all([
        api.get<Paginated<ServiceLinkage>>("/wlt/linkages/", {
          params: { page_size: 200, search, status: status || undefined },
        }),
        api.get<Summary>("/wlt/linkages/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.linkagesLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setStatus(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("status", next);
    else updated.delete("status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  const filters = [
    { value: "", label: t("wlt.allLinkages"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).filter((counter) => counter.count > 0),
  ].map((counter) => ({
    value: "value" in counter ? String(counter.value) : "",
    label: counter.label,
    count: counter.count,
  }));

  return (
    <ListPage
      title={t("wlt.linkagesTitle")}
      subtitle={t("wlt.linkagesSubtitle", { count: total })}
      searchPlaceholder={t("wlt.linkagesSearch")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("wlt.noLinkages"),
        body: t("wlt.noLinkagesBody"),
      }}
    >
      {() => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
            {filters.map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                className="pill-filter"
                data-active={filter.value === status ? "true" : undefined}
                onClick={() => setStatus(filter.value)}
              >
                {filter.label}
                <span className="pill-filter__count">{filter.count}</span>
              </button>
            ))}
          </div>

          <div className="stack">
            {rows.map((linkage) => {
              const tone = LINKAGE_TONE[linkage.status];
              return (
                <Card key={linkage.id}>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <div>
                      <strong>{linkage.type_label}</strong>
                      <div className="t-meta">
                        {linkage.subject_name ?? "—"} · {linkage.provider_name ?? t("wlt.noProvider")}
                      </div>
                    </div>
                    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                      <span className="chip__mark" aria-hidden>
                        {tone.mark}
                      </span>
                      {linkage.status_display}
                    </span>
                  </div>

                  {linkage.block_reasons.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <CapsLabel>{t("wlt.stillNeeded")}</CapsLabel>
                      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                        {linkage.block_reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </Card>
              );
            })}
          </div>
        </>
      )}
    </ListPage>
  );
}
