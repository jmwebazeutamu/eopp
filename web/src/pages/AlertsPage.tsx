import { App, Input, Modal } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Alert, AlertSummary, AlertTypeCode, Paginated } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import Paginator from "../components/Paginator";
import { scopeParam, useScope } from "../components/shell/ScopeContext";
import { Button, CapsLabel, Card, PageHeader } from "../components/ui";
import { ALERT_TONE } from "../design/status";
import { useLang } from "../i18n/LanguageContext";

const PAGE_SIZE = 25;

type ResolveKind = "action" | "dismiss";

export default function AlertsPage() {
  const scope = useScope();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const page = Math.max(1, Number(params.get("page") ?? 1));
  const filter = (params.get("alert_type") ?? "") as AlertTypeCode | "";
  const canWrite = user?.access.case_write ?? false;

  const [count, setCount] = useState(0);
  const [rows, setRows] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [resolving, setResolving] = useState<{ ids: string[]; kind: ResolveKind } | null>(null);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const query = params.get("q") || undefined;
      const [list, summaryResponse] = await Promise.all([
        api.get<Paginated<Alert>>("/alerts/", {
          params: {
            status: "OPEN",
            alert_type: filter || undefined,
            search: query,
            page,
            page_size: PAGE_SIZE,
            ...scopeParam(scope.woreda, "case__woreda"),
          },
        }),
        api.get<AlertSummary>("/alerts/summary/", {
          params: {
            search: query,
            ...scopeParam(scope.woreda, "case__woreda"),
          },
        }),
      ]);
      setRows(list.data.results);
      setCount(list.data.count);
      setSummary(summaryResponse.data);
      setSelectedIds((current) => current.filter((id) => list.data.results.some((row) => row.id === id)));
      setOpenId((current) => {
        if (current && list.data.results.some((row) => row.id === current)) return current;
        return list.data.results[0]?.id ?? null;
      });
    } catch (error) {
      message.error(errorMessage(error, "Could not load alerts."));
    } finally {
      setLoading(false);
    }
  }, [filter, page, params, message, scope.woreda]);

  useEffect(() => {
    void load();
  }, [load]);

  const openAlert = useMemo(() => rows.find((row) => row.id === openId) ?? rows[0] ?? null, [rows, openId]);
  const filterOptions = buildFilterOptions(summary, t);

  async function resolve() {
    if (!resolving) return;
    try {
      await Promise.all(resolving.ids.map((id) => api.post(`/alerts/${id}/${resolving.kind}/`, { note })));
      message.success(
        resolving.kind === "action"
          ? t(resolving.ids.length > 1 ? "alerts.bulkActioned" : "alerts.actioned", { count: resolving.ids.length })
          : t(resolving.ids.length > 1 ? "alerts.bulkDismissed" : "alerts.dismissed", { count: resolving.ids.length }),
      );
      setResolving(null);
      setNote("");
      setSelectedIds([]);
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not update the alert."));
    }
  }

  function toggleSelected(id: string) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function setFilter(nextFilter: AlertTypeCode | "") {
    const next = new URLSearchParams(params);
    next.delete("page");
    if (nextFilter) next.set("alert_type", nextFilter);
    else next.delete("alert_type");
    setParams(next, { replace: true });
  }

  return (
    <div className="page stack">
      <PageHeader title={t("alerts.title")} subtitle={t("alerts.subtitle", { count: summary?.open_total ?? 0, scope: scope.label })} />

      <div className="pill-row" role="group" aria-label={t("filters.label")}>
        {filterOptions.map((option) => {
          const active = option.value === filter || (!filter && option.value === "");
          return (
            <button
              key={option.key}
              type="button"
              className="pill-filter"
              data-active={active ? "true" : undefined}
              onClick={() => setFilter(option.value)}
              style={!active && option.value ? { color: option.tone.fg } : undefined}
            >
              {option.mark && <span aria-hidden="true">{option.mark}</span>}
              {option.label}
              <span className="pill-filter__count">{option.count}</span>
            </button>
          );
        })}
      </div>

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {!loading && rows.length === 0 && (
        <EmptyState
          onClear={() => {
            const next = new URLSearchParams(params);
            next.delete("alert_type");
            next.delete("q");
            next.delete("page");
            setParams(next, { replace: true });
          }}
        />
      )}

      {rows.length > 0 && (
        <div className="alerts-inbox">
          <div className="alerts-inbox__list">
            <div style={{ padding: 20, borderBottom: "1px solid var(--line)" }}>
              <Input
                placeholder={t("alerts.search")}
                aria-label={t("alerts.search")}
                defaultValue={params.get("q") ?? ""}
                onChange={(event) => {
                  const next = new URLSearchParams(params);
                  if (event.target.value) next.set("q", event.target.value);
                  else next.delete("q");
                  next.delete("page");
                  setParams(next, { replace: true });
                }}
              />
            </div>

            {selectedIds.length > 0 && canWrite && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 14,
                  padding: "9px 20px",
                  background: "var(--surface-alt)",
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <span className="t-meta">{t("alerts.selected", { count: selectedIds.length })}</span>
                <Button size="compact" variant="primary" onClick={() => setResolving({ ids: selectedIds, kind: "action" })}>
                  {t("alerts.action")}
                </Button>
                <Button size="compact" onClick={() => setResolving({ ids: selectedIds, kind: "dismiss" })}>
                  {t("alerts.dismiss")}
                </Button>
              </div>
            )}

            <div style={{ overflow: "auto" }}>
              {rows.map((alert) => {
                const meta = alertMeta(alert.alert_type);
                const isSelected = selectedIds.includes(alert.id);
                const isOpen = alert.id === openAlert?.id;
                return (
                  <div
                    key={alert.id}
                    className="alerts-table-row"
                    data-selected={isSelected ? "true" : undefined}
                    data-open={isOpen ? "true" : undefined}
                  >
                    <input
                      className="alerts-table-row__check"
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelected(alert.id)}
                      aria-label={alert.youth_name}
                    />
                    <span style={{ color: meta.tone.fg, fontSize: 12 }}>{meta.mark}</span>
                    <button
                      type="button"
                      className="alerts-table-row__button"
                      style={{ fontSize: 13, fontWeight: isOpen ? 700 : 600, color: "var(--ink-900)", textAlign: "left" }}
                      onClick={() => setOpenId(alert.id)}
                    >
                      {alert.youth_name}
                    </button>
                    <button
                      type="button"
                      className="alerts-table-row__button"
                      style={{
                        fontSize: 12.5,
                        color: "var(--ink-600)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        textAlign: "left",
                      }}
                      onClick={() => setOpenId(alert.id)}
                    >
                      {alert.summary}
                    </button>
                    <span className="t-meta">{alert.woreda}</span>
                    <span className="t-meta" style={{ textAlign: "right" }}>
                      {alert.age_days === 0 ? t("alerts.today") : `${alert.age_days}d`}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="alerts-inbox__preview">
            {openAlert ? (
              <>
                <CapsLabel style={{ color: alertMeta(openAlert.alert_type).tone.fg }}>{openAlert.alert_type_display}</CapsLabel>
                <div className="t-title" style={{ fontSize: 18, marginTop: 6 }}>
                  {openAlert.youth_name}
                </div>
                <div className="t-meta" style={{ marginTop: 4 }}>
                  {openAlert.woreda} · {openAlert.age_days === 0 ? t("alerts.today") : `${openAlert.age_days}d`}
                </div>

                <div
                  style={{
                    fontSize: 13.5,
                    lineHeight: 1.6,
                    color: "var(--ink-600)",
                    paddingBottom: 16,
                    borderBottom: "1px solid var(--line)",
                    marginTop: 16,
                    marginBottom: 16,
                  }}
                >
                  {openAlert.summary}
                </div>

                <div className="t-meta" style={{ marginBottom: 16 }}>
                  {openAlert.assigned_to_name || t("common.none")}
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <Button size="compact" onClick={() => navigate(`/cases/${openAlert.case}`)}>{t("registry.goToCase")}</Button>
                  {canWrite && (
                    <>
                      <Button size="compact" variant="primary" onClick={() => setResolving({ ids: [openAlert.id], kind: "action" })}>
                        {t("alerts.action")}
                      </Button>
                      <Button size="compact" onClick={() => setResolving({ ids: [openAlert.id], kind: "dismiss" })}>
                        {t("alerts.dismiss")}
                      </Button>
                    </>
                  )}
                </div>
              </>
            ) : (
              <div className="t-meta">{t("alerts.previewHint")}</div>
            )}
          </div>
        </div>
      )}

      <Paginator total={count} pageSize={PAGE_SIZE} />

      <Modal
        open={Boolean(resolving)}
        title={
          resolving
            ? t(
                resolving.kind === "action"
                  ? resolving.ids.length > 1
                    ? "alerts.resolveActionTitleBulk"
                    : "alerts.resolveActionTitle"
                  : resolving.ids.length > 1
                    ? "alerts.resolveDismissTitleBulk"
                    : "alerts.resolveDismissTitle",
                { count: resolving.ids.length },
              )
            : ""
        }
        okText={resolving?.kind === "action" ? t("alerts.action") : t("alerts.dismiss")}
        onOk={resolve}
        onCancel={() => {
          setResolving(null);
          setNote("");
        }}
        destroyOnHidden
      >
        <p style={{ marginBottom: 8 }}>
          {resolving?.kind === "action" ? t("alerts.resolveActionBody") : t("alerts.resolveDismissBody")}
        </p>
        <Input.TextArea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder={t("alerts.note")} />
      </Modal>
    </div>
  );
}

function buildFilterOptions(
  summary: AlertSummary | null,
  t: (key: string, vars?: Record<string, string | number>) => string,
) {
  const counts = new Map(summary?.by_type.map((row) => [row.alert_type, row.count]) ?? []);
  return [
    {
      key: "all",
      value: "" as const,
      label: t("alerts.filter.all"),
      count: summary?.open_total ?? 0,
      tone: { fg: "var(--ink-900)", bg: "var(--surface)" },
      mark: "",
    },
    { key: "stall", value: "STALL" as const, label: t("alerts.filter.stall"), count: counts.get("STALL") ?? 0, ...alertMeta("STALL") },
    {
      key: "overdue",
      value: "REFERRAL_CONFIRMATION_OVERDUE" as const,
      label: t("alerts.filter.overdue"),
      count: counts.get("REFERRAL_CONFIRMATION_OVERDUE") ?? 0,
      ...alertMeta("REFERRAL_CONFIRMATION_OVERDUE"),
    },
    {
      key: "follow-up",
      value: "FOLLOW_UP_DUE" as const,
      label: t("alerts.filter.followUp"),
      count: counts.get("FOLLOW_UP_DUE") ?? 0,
      ...alertMeta("FOLLOW_UP_DUE"),
    },
    {
      key: "onward",
      value: "ONWARD_REFERRAL_PROMPT" as const,
      label: t("alerts.filter.onward"),
      count: counts.get("ONWARD_REFERRAL_PROMPT") ?? 0,
      ...alertMeta("ONWARD_REFERRAL_PROMPT"),
    },
    {
      key: "replacement",
      value: "REPLACEMENT_REFERRAL_PROMPT" as const,
      label: t("alerts.filter.replacement"),
      count: counts.get("REPLACEMENT_REFERRAL_PROMPT") ?? 0,
      ...alertMeta("REPLACEMENT_REFERRAL_PROMPT"),
    },
    {
      key: "retention",
      value: "RETENTION_CHECK_DUE" as const,
      label: t("alerts.filter.retention"),
      count: counts.get("RETENTION_CHECK_DUE") ?? 0,
      ...alertMeta("RETENTION_CHECK_DUE"),
    },
  ];
}

function alertMeta(type: AlertTypeCode) {
  const tone = ALERT_TONE[type] ?? { fg: "var(--ink-600)", bg: "var(--fill-muted)" };
  const mark = {
    STALL: "▲",
    REFERRAL_CONFIRMATION_OVERDUE: "⟲",
    FOLLOW_UP_DUE: "●",
    ONWARD_REFERRAL_PROMPT: "●",
    REPLACEMENT_REFERRAL_PROMPT: "▲",
    RETENTION_CHECK_DUE: "⟲",
  }[type];
  return { tone, mark };
}

function EmptyState({ onClear }: { onClear: () => void }) {
  const { t } = useLang();
  return (
    <Card style={{ position: "relative", overflow: "hidden", textAlign: "center", padding: "32px 16px" }}>
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          opacity: 0.12,
          pointerEvents: "none",
          backgroundImage:
            "repeating-linear-gradient(45deg, var(--green-700) 0 6px, transparent 6px 12px), repeating-linear-gradient(-45deg, var(--gold-500) 0 6px, transparent 6px 12px)",
        }}
      />
      <div style={{ position: "relative" }}>
        <svg width={44} height={44} viewBox="0 0 24 24" fill="none" stroke="var(--green-700)" strokeWidth={1.6} strokeLinecap="round" aria-hidden>
          <path d="M4 13l5 5L20 7" />
        </svg>
        <div className="t-card-title" style={{ marginTop: 8 }}>
          {t("alerts.emptyTitle")}
        </div>
        <p className="t-meta" style={{ maxWidth: 420, margin: "6px auto 14px" }}>
          {t("alerts.emptyBody")}
        </p>
        <Button size="compact" onClick={onClear}>{t("alerts.showAll")}</Button>
      </div>
    </Card>
  );
}
