import { App, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Placement, RetentionCheck } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, CapsLabel, MutedChip } from "../components/ui";
import { EXIT_DIRECTION, RETENTION_TONE } from "../design/sprint5Status";
import { useLang } from "../i18n/LanguageContext";

/**
 * The employer liaison's screen — spec §10 Sprint 5, "screens for employer
 * liaison staff", and §4.7's 30/60/90-day checkpoints "including reminders".
 *
 * **The due queue is the screen.** A placement list sorted by date is a record;
 * a list of the checks that have fallen due is a day's work. The queue reads the
 * same condition the alert job materialises, so a check answered here disappears
 * from the inbox too — one definition, two renderings, exactly as the Tier 1
 * dashboard does it.
 *
 * Three answers, not two. "Could not be contacted" is a real finding at 90 days
 * and is recorded as one: filing it as "no longer in the placement" would report
 * a loss the programme has not established.
 */
export default function PlacementsPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<Placement[]>([]);
  const [due, setDue] = useState<RetentionCheck[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [answering, setAnswering] = useState<RetentionCheck | null>(null);
  const [answer, setAnswer] = useState<"RETAINED" | "UNREACHABLE">("RETAINED");
  const [busy, setBusy] = useState(false);

  const view = params.get("view") ?? "due";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, queue] = await Promise.all([
        api.get<Paginated<Placement>>("/placements/", { params: { page_size: 200, search } }),
        api.get<Paginated<RetentionCheck>>("/placements/checks/due/", { params: { page_size: 200 } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setDue(queue.data.results ?? []);
    } catch (error) {
      message.error(errorMessage(error, t("placements.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setView(next: string) {
    const updated = new URLSearchParams(params);
    updated.set("view", next);
    setParams(updated, { replace: true });
  }

  async function submitAnswer() {
    if (!answering) return;
    setBusy(true);
    try {
      await api.post(`/placements/checks/${answering.id}/record/`, { status: answer });
      message.success(t("placements.checkRecorded"));
      setAnswering(null);
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("placements.checkFailed")));
    } finally {
      setBusy(false);
    }
  }

  const canWrite = Boolean(user?.access.delivery_write);
  const byPlacement = new Map(rows.map((placement) => [placement.id, placement]));

  return (
    <ListPage
      title={t("placements.title")}
      subtitle={t("placements.subtitle", { count: total, due: due.length })}
      searchPlaceholder={t("placements.search")}
      empty={{
        when: !loading && rows.length === 0 && due.length === 0,
        title: t("placements.empty"),
        body: t("placements.emptyBody"),
      }}
    >
      {() => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
            <button
              type="button"
              className="pill-filter"
              data-active={view === "due" ? "true" : undefined}
              onClick={() => setView("due")}
            >
              {t("placements.dueNow")}
              <span className="pill-filter__count">{due.length}</span>
            </button>
            <button
              type="button"
              className="pill-filter"
              data-active={view === "all" ? "true" : undefined}
              onClick={() => setView("all")}
            >
              {t("placements.allPlacements")}
              <span className="pill-filter__count">{total}</span>
            </button>
          </div>

          {view === "due" && (
            <div className="stack">
              {due.length === 0 && <Card className="card--muted">{t("placements.queueClear")}</Card>}
              {due.map((check) => {
                const placement = byPlacement.get(check.placement);
                return (
                  <Card
                    key={check.id}
                    onClick={placement ? () => navigate(`/cases/${placement.case}`) : undefined}
                    hasOwnKeyboardTarget
                  >
                    <div
                      style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}
                    >
                      <div>
                        {placement ? (
                          <Link
                            className="row-link t-body-strong"
                            to={`/cases/${placement.case}`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            {placement.youth_name}
                          </Link>
                        ) : (
                          <strong>{t("placements.unknownYouth")}</strong>
                        )}
                        <div className="t-meta">
                          {placement?.employer_name} · {placement?.sector}
                        </div>
                        {placement?.source_referral && (
                          <div style={{ marginTop: 4 }}>
                            <Link
                              className="row-link"
                              to={`/referrals?q=${encodeURIComponent(placement.source_referral)}`}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {t("placements.openReferral")}
                            </Link>
                          </div>
                        )}
                      </div>
                      <MutedChip>{t("placements.checkpointDue", { days: check.checkpoint })}</MutedChip>
                    </div>
                    <div className="t-meta" style={{ marginTop: 6 }}>
                      {t("placements.dueSince", { date: check.due_date })}
                    </div>
                    {canWrite && (
                      <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                        <Button
                          size="compact"
                          variant="primary"
                          onClick={(event) => {
                            event.stopPropagation();
                            setAnswer("RETAINED");
                            setAnswering(check);
                          }}
                        >
                          {t("placements.stillThere")}
                        </Button>
                        <Button
                          size="compact"
                          variant="secondary"
                          onClick={(event) => {
                            event.stopPropagation();
                            setAnswer("UNREACHABLE");
                            setAnswering(check);
                          }}
                        >
                          {t("placements.unreachable")}
                        </Button>
                      </div>
                    )}
                    {/* Leaving is recorded on the placement, not on the check:
                        an exit closes every outstanding checkpoint and carries
                        the reason the report needs. */}
                    <div className="t-meta" style={{ marginTop: 6 }}>
                      {t("placements.exitHint")}
                    </div>
                  </Card>
                );
              })}
            </div>
          )}

          {view === "all" && (
            <div className="stack">
              {rows.map((placement) => (
                <Card key={placement.id} onClick={() => navigate(`/cases/${placement.case}`)} hasOwnKeyboardTarget>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <div>
                      <Link
                        className="row-link t-body-strong"
                        to={`/cases/${placement.case}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {placement.youth_name}
                      </Link>
                      <div className="t-meta">
                        {placement.employer_name} · {placement.sector} · {placement.placement_type_display}
                      </div>
                      {placement.source_referral && (
                        <div style={{ marginTop: 4 }}>
                          <Link
                            className="row-link"
                            to={`/referrals?q=${encodeURIComponent(placement.source_referral)}`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            {t("placements.openReferral")}
                          </Link>
                        </div>
                      )}
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="t-meta">{t("placements.since", { date: placement.placement_date })}</div>
                      {placement.is_subsidised && (
                        <MutedChip style={{ fontSize: 12 }}>{t("placements.subsidised")}</MutedChip>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                    {placement.retention_checks.map((check) => {
                      const tone = RETENTION_TONE[check.status];
                      return (
                        <span
                          key={check.id}
                          className="chip"
                          style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}
                        >
                          <span className="chip__mark" aria-hidden>
                            {tone.mark}
                          </span>
                          {t("placements.checkpointLabel", { days: check.checkpoint })}
                        </span>
                      );
                    })}
                  </div>

                  {placement.exit_date && (
                    <div style={{ marginTop: 10 }}>
                      <CapsLabel>{t("placements.left")}</CapsLabel>
                      <div>
                        {placement.exit_date} · {placement.exit_reason_display}
                        {EXIT_DIRECTION[placement.exit_reason] === "up" && ` — ${t("placements.stepUp")}`}
                      </div>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          )}

          <Modal
            open={answering !== null}
            title={t("placements.recordCheck")}
            okText={t("common.save")}
            cancelText={t("common.cancel")}
            confirmLoading={busy}
            onCancel={() => setAnswering(null)}
            onOk={() => void submitAnswer()}
          >
            <p>{t("placements.recordCheckBody")}</p>
            <Select
              value={answer}
              onChange={(next) => setAnswer(next)}
              style={{ width: "100%" }}
              options={[
                { value: "RETAINED", label: t("placements.stillThere") },
                // "Could not be contacted" is a real finding, not a missing
                // one. It is counted separately from a loss.
                { value: "UNREACHABLE", label: t("placements.unreachable") },
              ]}
            />
          </Modal>
        </>
      )}
    </ListPage>
  );
}
