import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Enterprise, Paginated, Summary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, CapsLabel, MutedChip } from "../components/ui";
import { MILESTONE_TONE, PLAN_TONE } from "../design/sprint6Status";
import { useLang } from "../i18n/LanguageContext";

/**
 * The enterprise development officer's screen — §10 Sprint 6, §4.8.
 *
 * **Awaiting disbursement leads.** A youth with an approved plan and no money
 * against it is waiting on the programme, not on herself, and that is the only
 * queue on this screen where the delay belongs to us.
 *
 * The card keeps three facts apart that a summary would merge: a plan approved,
 * money disbursed, and a business trading. Each is a different claim, and only
 * the third is an outcome.
 */
export default function EnterprisesPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<Enterprise[]>([]);
  const [waiting, setWaiting] = useState<Enterprise[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const status = params.get("business_plan_status") ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, queue, counters] = await Promise.all([
        api.get<Paginated<Enterprise>>("/enterprises/", {
          params: { page_size: 200, search, business_plan_status: status || undefined },
        }),
        api.get<Enterprise[]>("/enterprises/awaiting-disbursement/"),
        api.get<Summary>("/enterprises/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setWaiting(queue.data ?? []);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("enterprises.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setStatus(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("business_plan_status", next);
    else updated.delete("business_plan_status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  async function markTrading(enterprise: Enterprise) {
    setBusy(enterprise.id);
    try {
      await api.post(`/enterprises/${enterprise.id}/trading/`, {});
      message.success(t("enterprises.tradingRecorded"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("enterprises.tradingFailed")));
    } finally {
      setBusy(null);
    }
  }

  const canWrite = Boolean(user?.access.delivery_write);
  const filters = [
    { value: "", label: t("enterprises.all"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? [])
      .filter((counter) => counter.count > 0)
      .map((counter) => ({ value: String(counter.value), label: counter.label, count: counter.count })),
  ];

  return (
    <ListPage
      title={t("enterprises.title")}
      subtitle={t("enterprises.subtitle", { count: total })}
      searchPlaceholder={t("enterprises.search")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("enterprises.empty"),
        body: t("enterprises.emptyBody"),
      }}
    >
      {() => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          {waiting.length > 0 && (
            <Card style={{ marginBottom: 16 }}>
              <strong>{t("enterprises.waitingHeading", { count: waiting.length })}</strong>
              <div className="t-meta">{t("enterprises.waitingBody")}</div>
            </Card>
          )}

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
            {rows.map((enterprise) => {
              const tone = PLAN_TONE[enterprise.business_plan_status];
              return (
                <Card key={enterprise.id} onClick={() => navigate(`/cases/${enterprise.case}`)} hasOwnKeyboardTarget>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <div>
                      <Link
                        className="row-link t-body-strong"
                        to={`/cases/${enterprise.case}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {enterprise.business_name || enterprise.youth_name}
                      </Link>
                      <div className="t-meta">
                        {enterprise.youth_name} · {enterprise.sector || t("enterprises.noSector")} ·{" "}
                        {enterprise.woreda}
                      </div>
                      {enterprise.source_referral && (
                        <div style={{ marginTop: 4 }}>
                          <Link
                            className="row-link"
                            to={`/referrals?q=${encodeURIComponent(enterprise.source_referral)}`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            {t("enterprises.openReferral")}
                          </Link>
                        </div>
                      )}
                    </div>
                    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                      <span className="chip__mark" aria-hidden>
                        {tone.mark}
                      </span>
                      {enterprise.plan_status_display}
                    </span>
                  </div>

                  {/* Three facts, kept apart. A summary that merged them would
                      report the programme's transfer as the youth's result. */}
                  <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                    <MutedChip style={{ fontSize: 12 }}>
                      {enterprise.has_support
                        ? t("enterprises.supported", {
                            amount: enterprise.grant_or_loan_amount ?? "—",
                            kind: enterprise.support_type_display,
                          })
                        : t("enterprises.noSupport")}
                    </MutedChip>
                    <MutedChip style={{ fontSize: 12 }}>
                      {enterprise.started_trading_on
                        ? t("enterprises.tradingSince", { date: enterprise.started_trading_on })
                        : t("enterprises.notTrading")}
                    </MutedChip>
                    {enterprise.milestones_overdue > 0 && (
                      <MutedChip style={{ fontSize: 12 }}>
                        {t("enterprises.milestonesOverdue", { count: enterprise.milestones_overdue })}
                      </MutedChip>
                    )}
                  </div>

                  {enterprise.milestones.length > 0 && (
                    <div style={{ marginTop: 12 }}>
                      <CapsLabel>{t("enterprises.milestones")}</CapsLabel>
                      <ul style={{ margin: "6px 0 0", paddingLeft: 0, listStyle: "none" }}>
                        {enterprise.milestones.map((milestone) => {
                          const milestoneTone = MILESTONE_TONE[milestone.status];
                          return (
                            <li
                              key={milestone.id}
                              style={{ display: "flex", gap: 8, alignItems: "baseline", marginBottom: 4 }}
                            >
                              <span aria-hidden style={{ color: milestoneTone.ink }}>
                                {milestoneTone.mark}
                              </span>
                              <span>{milestone.milestone_name}</span>
                              <span className="t-meta">
                                {milestone.status_display} ·{" "}
                                {milestone.completion_date ?? milestone.target_date}
                                {milestone.is_overdue ? ` · ${t("enterprises.overdue")}` : ""}
                              </span>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}

                  {canWrite && enterprise.has_support && !enterprise.started_trading_on && (
                    <div style={{ marginTop: 12 }}>
                      <Button
                        size="compact"
                        variant="secondary"
                        disabled={busy === enterprise.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void markTrading(enterprise);
                        }}
                      >
                        {t("enterprises.markTrading")}
                      </Button>
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
