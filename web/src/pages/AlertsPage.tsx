import { App, Input, Modal } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Alert, AlertSummary, Paginated } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import FilterChips from "../components/FilterChips";
import { scopeParam, useScope } from "../components/shell/ScopeContext";
import { Button, CapsLabel, Card, PageHeader } from "../components/ui";
import { ALERT_TONE } from "../design/status";

/**
 * The chip palette for each alert type.
 *
 * `ALERT_TONE` gives a background and a foreground; the counter cards took the
 * foreground alone, which is the fault that rendered the Cases screen's Placed
 * count white on white. A mark is added so a selected chip is never colour
 * alone — a triangle for the two that mean something has gone wrong, a quarter
 * circle for the two that mean waiting, a dot for the two that are prompts.
 */
const ALERT_CHIP_TONES: Record<string, { fg: string; bg: string; mark: string }> = {
  STALL: { ...ALERT_TONE.STALL, mark: "\u25b2" },
  REFERRAL_CONFIRMATION_OVERDUE: { ...ALERT_TONE.REFERRAL_CONFIRMATION_OVERDUE, mark: "\u25d4" },
  FOLLOW_UP_DUE: { ...ALERT_TONE.FOLLOW_UP_DUE, mark: "\u25cf" },
  ONWARD_REFERRAL_PROMPT: { ...ALERT_TONE.ONWARD_REFERRAL_PROMPT, mark: "\u25cf" },
  REPLACEMENT_REFERRAL_PROMPT: { ...ALERT_TONE.REPLACEMENT_REFERRAL_PROMPT, mark: "\u25b2" },
  RETENTION_CHECK_DUE: { ...ALERT_TONE.RETENTION_CHECK_DUE, mark: "\u25d4" },
};
import { useLang } from "../i18n/LanguageContext";

/**
 * Alerts — the handoff's counter grid over a filtered list.
 *
 * Each counter is a filter: tapping one narrows the list, tapping it again
 * clears it, and the choice lives in the URL so it survives a back button. The
 * counters carry a one-line reason because "Stall Alert · 14" says nothing
 * about why the system raised them.
 */

export default function AlertsPage() {
  const scope = useScope();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<Alert[]>([]);
  const [summary, setSummary] = useState<AlertSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [resolving, setResolving] = useState<{ alert: Alert; kind: "action" | "dismiss" } | null>(null);
  const [note, setNote] = useState("");

  // Named by the server through the counters, not chosen here.
  const filter = params.get("alert_type__in") ?? "";
  const canWrite = user?.access.case_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, summaryResponse] = await Promise.all([
        api.get<Paginated<Alert>>("/alerts/", {
          params: {
            status: "OPEN",
            alert_type__in: filter || undefined,
            page_size: 100,
            ...scopeParam(scope.woreda, "case__woreda"),
          },
        }),
        api.get<AlertSummary>("/alerts/summary/", { params: scopeParam(scope.woreda, "case__woreda") }),
      ]);
      setRows(list.data.results);
      setSummary(summaryResponse.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load alerts."));
    } finally {
      setLoading(false);
    }
  }, [filter, message, scope.woreda]);

  useEffect(() => {
    void load();
  }, [load]);


  async function resolve() {
    if (!resolving) return;
    try {
      await api.post(`/alerts/${resolving.alert.id}/${resolving.kind}/`, { note });
      message.success(resolving.kind === "action" ? "Alert actioned." : "Alert dismissed.");
      setResolving(null);
      setNote("");
      void load();
    } catch (error) {
      message.error(errorMessage(error, "Could not update the alert."));
    }
  }

  return (
    <div className="page stack">
      <PageHeader
        title={t("alerts.title")}
        subtitle={t("alerts.subtitle", { count: summary?.open_total ?? 0, scope: scope.label })}
      />

      <FilterChips
        resource="/alerts"
        params={scopeParam(scope.woreda, "case__woreda")}
        tones={ALERT_CHIP_TONES}
      />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {!loading && rows.length === 0 && <EmptyState onClear={() => setParams({}, { replace: true })} />}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {rows.map((alert) => {
          const tone = ALERT_TONE[alert.alert_type] ?? { fg: "var(--ink-600)", bg: "var(--fill-muted)" };
          return (
            <Card key={alert.id}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <CapsLabel style={{ color: tone.fg }}>{alert.alert_type_display}</CapsLabel>
                  <div
                    className="t-body-strong"
                    style={{ cursor: "pointer" }}
                    onClick={() => navigate(`/cases/${alert.case}`)}
                  >
                    {alert.youth_name}
                  </div>
                  <div className="t-meta">
                    {alert.summary} · {alert.woreda}
                  </div>
                </div>

                <span
                  className="chip"
                  style={{ color: tone.fg, background: tone.bg, borderColor: "transparent", fontSize: 12 }}
                >
                  {alert.age_days === 0 ? t("alerts.today") : t("alerts.days", { days: alert.age_days })}
                </span>
              </div>

              {canWrite && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                  <Button variant="primary" onClick={() => setResolving({ alert, kind: "action" })}>
                    {t("alerts.action")}
                  </Button>
                  <Button onClick={() => setResolving({ alert, kind: "dismiss" })}>{t("alerts.dismiss")}</Button>
                </div>
              )}
            </Card>
          );
        })}
      </div>

      <Modal
        open={Boolean(resolving)}
        title={resolving?.kind === "action" ? "Mark this alert actioned?" : "Dismiss this alert?"}
        okText={resolving?.kind === "action" ? "Mark actioned" : "Dismiss"}
        onOk={resolve}
        onCancel={() => {
          setResolving(null);
          setNote("");
        }}
        destroyOnHidden
      >
        {/* §9 wants the rationale on the record, not only the fact of the click. */}
        <p style={{ marginBottom: 8 }}>
          {resolving?.kind === "action"
            ? "Recorded against the alert with your name and the date."
            : "Dismissing closes the alert without recording an action on the case."}
        </p>
        <Input.TextArea rows={3} value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note" />
      </Modal>
    </div>
  );
}

/**
 * The empty state.
 *
 * The habesha-border-derived pattern appears here and nowhere else — at 12%
 * opacity behind an empty card it reads as a considered pause, and behind data
 * it would just be noise competing with the status colours.
 */
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
        <Button onClick={onClear}>{t("alerts.showAll")}</Button>
      </div>
    </Card>
  );
}
