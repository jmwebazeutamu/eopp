import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Summary, TrainingEnrolment } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, MutedChip } from "../components/ui";
import { TRAINING_TONE } from "../design/sprint5Status";
import { useLang } from "../i18n/LanguageContext";

/**
 * The trainer's screen — spec §10 Sprint 5, "screens for trainers".
 *
 * A trainer sees the enrolments she recorded (§7's LINKED scope, resolved
 * through the entity the role owns). A case manager sees her caseload's; a
 * supervisor her woreda's. The list is the same, the rows differ, and the
 * server decides which — the screen never filters by role.
 *
 * **Overdue leads the sort.** A course past its scheduled end with nobody having
 * said what happened is the one thing on this screen that needs a person today:
 * until somebody records the outcome, the youth is neither in training nor
 * available for a next step, and the onward prompt cannot fire.
 */
export default function TrainingPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<TrainingEnrolment[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const status = params.get("completion_status") ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, counters] = await Promise.all([
        api.get<Paginated<TrainingEnrolment>>("/training/", {
          params: { page_size: 200, search, completion_status: status || undefined },
        }),
        api.get<Summary>("/training/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("training.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setStatus(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("completion_status", next);
    else updated.delete("completion_status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  async function complete(enrolment: TrainingEnrolment) {
    setBusy(enrolment.id);
    try {
      await api.post(`/training/${enrolment.id}/complete/`, {});
      message.success(t("training.completed"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("training.completeFailed")));
    } finally {
      setBusy(null);
    }
  }

  const canWrite = Boolean(user?.access.delivery_write);
  // Overdue first, then by soonest end date. The sort is the screen's argument.
  const sorted = [...rows].sort((left, right) => {
    if (left.is_overdue !== right.is_overdue) return left.is_overdue ? -1 : 1;
    return left.end_date.localeCompare(right.end_date);
  });
  const overdue = rows.filter((row) => row.is_overdue).length;

  const filters = [
    { value: "", label: t("training.all"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).map((counter) => ({
      value: String(counter.value),
      label: counter.label,
      count: counter.count,
    })),
  ];

  return (
    <ListPage
      title={t("training.title")}
      subtitle={t("training.subtitle", { count: total })}
      searchPlaceholder={t("training.search")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("training.empty"),
        body: t("training.emptyBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          {overdue > 0 && (
            <Card style={{ marginBottom: 16 }}>
              {/* Not an alert — a count with a reason. Until somebody records
                  the outcome the youth is neither in training nor available
                  for a next step. */}
              <strong>{t("training.overdueHeading", { count: overdue })}</strong>
              <div className="t-meta">{t("training.overdueBody")}</div>
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

          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">{t("training.youth")}</th>
                    <th scope="col">{t("training.course")}</th>
                    <th scope="col">{t("training.provider")}</th>
                    <th scope="col">{t("training.window")}</th>
                    <th scope="col">{t("training.attendance")}</th>
                    <th scope="col">{t("training.status")}</th>
                    {canWrite && <th scope="col" />}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map((enrolment) => (
                    <tr key={enrolment.id} onClick={() => navigate(`/cases/${enrolment.case}`)}>
                      <td>
                        <Link className="row-link" to={`/cases/${enrolment.case}`} onClick={(event) => event.stopPropagation()}>
                          {enrolment.youth_name}
                        </Link>
                        <div style={{ color: "var(--ink-400)" }}>{enrolment.woreda}</div>
                      </td>
                      <td>
                        {enrolment.training_type_display}
                        {enrolment.trade_or_skill_area && (
                          <div style={{ color: "var(--ink-400)" }}>{enrolment.trade_or_skill_area}</div>
                        )}
                      </td>
                      <td>
                        <div>{enrolment.provider_name}</div>
                        {enrolment.source_referral && (
                          <Link
                            className="row-link"
                            to={`/referrals?q=${encodeURIComponent(enrolment.source_referral)}`}
                            onClick={(event) => event.stopPropagation()}
                          >
                            {t("training.openReferral")}
                          </Link>
                        )}
                      </td>
                      <td>
                        {enrolment.start_date} → {enrolment.end_date}
                        {enrolment.is_overdue && (
                          <div>
                            <MutedChip style={{ fontSize: 12 }}>{t("training.overdue")}</MutedChip>
                          </div>
                        )}
                      </td>
                      <td>{enrolment.attendance_rate === null ? "—" : `${enrolment.attendance_rate}%`}</td>
                      <td>
                        <StatusChip enrolment={enrolment} />
                      </td>
                      {canWrite && (
                        <td>
                          {enrolment.completion_status === "ENROLLED" && (
                            <Button
                              size="compact"
                              variant="secondary"
                              disabled={busy === enrolment.id}
                              onClick={(event) => {
                                event.stopPropagation();
                                void complete(enrolment);
                              }}
                            >
                              {t("training.markComplete")}
                            </Button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="only-phone">
            <div className="stack">
              {sorted.map((enrolment) => (
                <Card key={enrolment.id} onClick={() => navigate(`/cases/${enrolment.case}`)} hasOwnKeyboardTarget>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <Link
                      className="row-link t-body-strong"
                      to={`/cases/${enrolment.case}`}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {enrolment.youth_name}
                    </Link>
                    <StatusChip enrolment={enrolment} />
                  </div>
                  <div className="t-meta">
                    {enrolment.training_type_display}
                    {enrolment.trade_or_skill_area ? ` · ${enrolment.trade_or_skill_area}` : ""} ·{" "}
                    {enrolment.provider_name}
                  </div>
                  {enrolment.source_referral && (
                    <div style={{ marginTop: 4 }}>
                      <Link
                        className="row-link"
                        to={`/referrals?q=${encodeURIComponent(enrolment.source_referral)}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        {t("training.openReferral")}
                      </Link>
                    </div>
                  )}
                  <div className="t-meta">
                    {enrolment.start_date} → {enrolment.end_date}
                    {enrolment.is_overdue ? ` · ${t("training.overdue")}` : ""}
                  </div>
                  {canWrite && enrolment.completion_status === "ENROLLED" && (
                    <div style={{ marginTop: 8 }}>
                      <Button
                        size="compact"
                        variant="secondary"
                        disabled={busy === enrolment.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void complete(enrolment);
                        }}
                      >
                        {t("training.markComplete")}
                      </Button>
                    </div>
                  )}
                </Card>
              ))}
            </div>
          </div>
        </>
      )}
    </ListPage>
  );
}

function StatusChip({ enrolment }: { enrolment: TrainingEnrolment }) {
  const tone = TRAINING_TONE[enrolment.completion_status];
  return (
    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
      <span className="chip__mark" aria-hidden>
        {tone.mark}
      </span>
      {enrolment.completion_status_display}
    </span>
  );
}
