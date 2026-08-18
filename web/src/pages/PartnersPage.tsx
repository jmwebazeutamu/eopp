import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Partner, Summary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import PartnerDetailModal, { MOU_TONE } from "../components/PartnerDetailModal";
import PartnerFormModal from "../components/PartnerFormModal";
import { Button, Card, MutedChip } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

type PartnerFilter = "all" | "accepting" | "paused" | "no-mou" | "draft" | "signed";

export default function PartnersPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const [total, setTotal] = useState(0);
  const [rows, setRows] = useState<Partner[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<Partner | null>(null);
  const [editing, setEditing] = useState<Partner | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const canWrite = user?.role === "SYSTEM_ADMIN" || user?.role === "PROGRAMME_MANAGER";
  const activeFilter = currentFilter(params);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [response, summaryResponse] = await Promise.all([
        api.get<Paginated<Partner>>("/partners/", {
          params: {
            page_size: 200,
            search,
            active_status: params.get("active_status") ?? undefined,
            mou_status: params.get("mou_status") ?? undefined,
          },
        }),
        api.get<Summary>("/partners/summary/", { params: { search } }),
      ]);
      setRows(response.data.results);
      setTotal(response.data.count);
      setSummary(summaryResponse.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load partners."));
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = new Map(summary?.counters.map((counter) => [`${counter.param}:${counter.value}`, counter.count]) ?? []);

  const filters: { key: PartnerFilter; label: string; count: number }[] = [
    { key: "all", label: "All", count: summary?.total ?? 0 },
    { key: "accepting", label: t("partners.accepting"), count: counts.get("active_status:true") ?? 0 },
    { key: "paused", label: t("partners.paused"), count: counts.get("active_status:false") ?? 0 },
    { key: "no-mou", label: "No MOU", count: counts.get("mou_status:NONE") ?? 0 },
    { key: "draft", label: "Draft", count: counts.get("mou_status:DRAFT") ?? 0 },
    { key: "signed", label: "Signed", count: counts.get("mou_status:SIGNED") ?? 0 },
  ];

  function setFilter(nextFilter: PartnerFilter) {
    const next = new URLSearchParams(params);
    next.delete("active_status");
    next.delete("mou_status");
    if (nextFilter === "accepting") next.set("active_status", "true");
    if (nextFilter === "paused") next.set("active_status", "false");
    if (nextFilter === "no-mou") next.set("mou_status", "NONE");
    if (nextFilter === "draft") next.set("mou_status", "DRAFT");
    if (nextFilter === "signed") next.set("mou_status", "SIGNED");
    setParams(next, { replace: true });
  }

  return (
    <ListPage
      title={t("partners.title")}
      subtitle={t("partners.subtitle", { count: total })}
      action={
        canWrite ? (
          <Button
            size="compact"
            variant="primary"
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            {t("partners.add")}
          </Button>
        ) : undefined
      }
      searchPlaceholder={t("partners.search")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("empty.partners"),
        body: t("empty.partnersBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          {summary && (
            <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
              {filters.map((filter) => (
                <button
                  key={filter.key}
                  type="button"
                  className="pill-filter"
                  data-active={filter.key === activeFilter ? "true" : undefined}
                  onClick={() => setFilter(filter.key)}
                >
                  {filter.label}
                  <span className="pill-filter__count">{filter.count}</span>
                </button>
              ))}
            </div>
          )}

          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">{t("partners.one")}</th>
                    <th scope="col">{t("partners.coverage")}</th>
                    <th scope="col">{t("partners.contact")}</th>
                    <th scope="col">{t("partners.status")}</th>
                    <th scope="col">MOU</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((partner) => {
                    const tone = MOU_TONE[partner.mou_status];
                    return (
                      <tr key={partner.id} onClick={() => setViewing(partner)}>
                        <td>
                          <button
                            type="button"
                            className="row-link"
                            onClick={(event) => {
                              event.stopPropagation();
                              setViewing(partner);
                            }}
                          >
                            {partner.partner_name}
                          </button>
                          <div style={{ color: "var(--ink-400)" }}>{partner.partner_type_display}</div>
                        </td>
                        <td>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                            {partner.woreda_coverage.length ? (
                              partner.woreda_coverage.map((woreda) => (
                                <MutedChip key={woreda} style={{ fontSize: 12 }}>
                                  {woreda}
                                </MutedChip>
                              ))
                            ) : (
                              <span className="t-meta">{t("partners.noCoverage")}</span>
                            )}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontSize: 13.5, fontWeight: 600 }}>{partner.contact_name || t("common.none")}</div>
                          <div className="t-meta tabular">{partner.phone}</div>
                        </td>
                        <td>
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: 6,
                              color: partner.can_receive_referrals ? "var(--green-ink)" : "var(--ink-400)",
                              fontWeight: 600,
                              fontSize: 13,
                            }}
                          >
                            <span
                              aria-hidden="true"
                              style={{
                                width: 6,
                                height: 6,
                                borderRadius: "50%",
                                background: partner.can_receive_referrals ? "var(--green-500)" : "var(--ink-400)",
                              }}
                            />
                            {partner.can_receive_referrals ? t("partners.accepting") : t("partners.paused")}
                          </span>
                        </td>
                        <td>
                          <span
                            className="chip"
                            style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}
                            title={partner.mou_date ? `MOU dated ${partner.mou_date}` : undefined}
                          >
                            {partner.mou_status_display}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>
          </div>

          {/* `.only-phone` owns `display` and `flex-direction` in base.css. Setting
              `display` here beats the media query, so the table and these cards
              both rendered at 1440 and every partner appeared twice. */}
          <div className="only-phone" style={{ gap: 12 }}>
            {rows.map((partner) => {
              const tone = MOU_TONE[partner.mou_status];
              return (
                <Card key={partner.id} onClick={() => setViewing(partner)} style={{ padding: "12px 14px" }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between" }}>
                    <div style={{ minWidth: 0 }}>
                      <div className="t-body-strong">{partner.partner_name}</div>
                      <div className="t-meta">{partner.partner_type_display}</div>
                    </div>
                    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                      {partner.mou_status_display}
                    </span>
                  </div>
                  <div className="card__rule" />
                  <div className="t-meta">{partner.contact_name || t("common.none")} · {partner.phone}</div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
                    {partner.woreda_coverage.length ? (
                      partner.woreda_coverage.map((woreda) => (
                        <MutedChip key={woreda} style={{ fontSize: 12 }}>
                          {woreda}
                        </MutedChip>
                      ))
                    ) : (
                      <span className="t-meta">{t("partners.noCoverage")}</span>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>

          <PartnerDetailModal
            partner={viewing}
            canEdit={canWrite}
            onClose={() => setViewing(null)}
            onEdit={(partner) => {
              setViewing(null);
              setEditing(partner);
              setFormOpen(true);
            }}
          />

          <PartnerFormModal
            open={formOpen}
            partner={editing}
            onClose={() => setFormOpen(false)}
            onSaved={() => {
              setFormOpen(false);
              void load();
            }}
          />
        </>
      )}
    </ListPage>
  );
}

function currentFilter(params: URLSearchParams): PartnerFilter {
  if (params.get("active_status") === "true") return "accepting";
  if (params.get("active_status") === "false") return "paused";
  if (params.get("mou_status") === "NONE") return "no-mou";
  if (params.get("mou_status") === "DRAFT") return "draft";
  if (params.get("mou_status") === "SIGNED") return "signed";
  return "all";
}
