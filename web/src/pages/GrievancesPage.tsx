import { App, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { CaseListRow, Grievance, GrievanceQueueCounts, Paginated, Summary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, CapsLabel, MutedChip } from "../components/ui";
import { GRIEVANCE_TONE } from "../design/sprint6Status";
import { useLang } from "../i18n/LanguageContext";
import { byUrgency, clockLabel } from "./grievanceClock";

function QueueCount({ value, label, tone }: { value: number; label: string; tone: "late" | "due" | "calm" }) {
  // Zero is a real answer and worth showing: "0 late" is the sentence a
  // supervisor opens this page hoping to read. It just does not get a colour.
  return (
    <div className="queue-count" data-tone={value > 0 ? tone : "calm"}>
      <strong className="tabular">{value}</strong>
      <span className="t-meta">{label}</span>
    </div>
  );
}

function DueCell({ grievance }: { grievance: Grievance }) {
  const { t } = useLang();
  const label = clockLabel(grievance.standing);
  return (
    <span className="due-cell" data-tone={label.tone}>
      {t(label.key, { days: label.days })}
    </span>
  );
}

/**
 * The grievance screen — §4.10, Sprint 6.
 *
 * **Overdue leads**, because a complaints channel is judged on whether anybody
 * answers: one that collects the complaint, creates the expectation and then
 * does nothing is worse than none at all.
 *
 * Resolving asks what was done, and the field is mandatory both here and in the
 * service. A resolution rate computed over status changes nobody described is
 * the kind of figure that survives right up until somebody asks for an example.
 *
 * Nothing on this screen filters by sensitivity — the server does that. A
 * safeguarding complaint is not in the payload at all unless the reader is its
 * assignee or an administrator, because the person complained about may be the
 * supervisor who would otherwise read it.
 */
export default function GrievancesPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<Grievance[]>([]);
  const [counts, setCounts] = useState<GrievanceQueueCounts | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [caseOptions, setCaseOptions] = useState<CaseListRow[]>([]);
  const [createDraft, setCreateDraft] = useState({
    case: "",
    complaint_type: "SERVICE_QUALITY",
    raised_by: "YOUTH",
    summary: "",
    complainant_name: "",
    complainant_contact: "",
  });
  const [busy, setBusy] = useState(false);

  // The server names the parameter a counter toggles (`summary.counters[].param`),
  // so no query-parameter name is spelled here. Every URL parameter other than
  // the page's own `q`/`page` goes to the list as it stands, which also means a
  // filter is applied on the first request, before the summary has answered.
  const filterParam = summary?.counters[0]?.param;
  const status = (filterParam && params.get(filterParam)) || "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const listFilters = Object.fromEntries([...params.entries()].filter(([key]) => key !== "q" && key !== "page"));
      const [list, late, counters] = await Promise.all([
        api.get<Paginated<Grievance>>("/grievances/", {
          params: { page_size: 200, search, ...listFilters },
        }),
        api.get<GrievanceQueueCounts>("/grievances/queue-counts/"),
        api.get<Summary>("/grievances/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setCounts(late.data);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("grievances.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function loadCases(search = "") {
    const response = await api.get<Paginated<CaseListRow>>("/cases/", {
      params: { page_size: 25, search: search || undefined },
    });
    setCaseOptions(response.data.results);
  }

  function setStatus(counter: { param: string; value: string } | null) {
    const updated = new URLSearchParams(params);
    if (filterParam) updated.delete(filterParam);
    if (counter) updated.set(counter.param, counter.value);
    updated.delete("page");
    setParams(updated, { replace: true });
  }





  async function openCreateModal() {
    setCreating(true);
    if (caseOptions.length === 0) {
      try {
        await loadCases();
      } catch (error) {
        message.error(errorMessage(error, t("grievances.caseLoadFailed")));
      }
    }
  }

  async function submitCreate() {
    if (!user?.id) return;
    setBusy(true);
    try {
      const response = await api.post<Grievance>("/grievances/", {
        ...createDraft,
        assigned_staff: user.id,
      });
      message.success(t("grievances.created"));
      setCreating(false);
      // Straight to the file. Filing a complaint and then being returned to a
      // list is the moment the reference number gets lost, and the next thing
      // anybody does is acknowledge it.
      navigate(`/grievances/${response.data.id}`);
      setCreateDraft({
        case: "",
        complaint_type: "SERVICE_QUALITY",
        raised_by: "YOUTH",
        summary: "",
        complainant_name: "",
        complainant_contact: "",
      });
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.createFailed")));
    } finally {
      setBusy(false);
    }
  }

  // Both modules file into this channel, so both may write to it. Gating on
  // `case_write` alone hid the New complaint button from every WLT role —
  // all four carry `case_scope: NONE` by design — so a savings group could not
  // complain about anything and the facilitator who was in the room when the
  // complaint was made could not write it down.
  // From the first row the server sent, not from the role flags: a
  // supervisor has neither `case_write` nor `group_write` and is exactly the
  // person who works a woreda's complaints. An empty queue falls back to the
  // flags so the New complaint button is not hidden from somebody with nothing
  // to look at yet.
  const canWrite = rows.length > 0 ? rows[0].can_act : Boolean(user?.access.case_write || user?.access.group_write);
  const isSafeguarding = createDraft.complaint_type === "SAFEGUARDING";
  // Late first, then due, then the rest — and the most overdue at the very top.
  // The comparator moved into `grievanceClock.ts` when the clock arrived: it
  // used to rank on a separate `/overdue/` fetch, which meant the order the
  // screen showed and the deadline the record carried were two different
  // opinions about the same thing.
  const sorted = [...rows].sort(byUrgency);

  const filters = [
    { value: "", param: "", label: t("grievances.all"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).map((counter) => ({
      value: String(counter.value),
      param: counter.param,
      label: counter.label,
      count: counter.count,
    })),
  ];

  const canSubmitCreate = createDraft.case !== "" && createDraft.summary.trim().length > 0;

  return (
    <ListPage
      title={t("grievances.title")}
      // Not while it loads. "0 grievances" before the response lands reads as a
      // mechanism nobody uses, which is the one thing a complaints channel must
      // never say about itself by accident.
      subtitle={loading ? t("common.loading") : t("grievances.subtitle", { count: total })}
      action={
        canWrite ? (
          <Button variant="primary" onClick={() => void openCreateModal()}>
            {t("grievances.add")}
          </Button>
        ) : undefined
      }
      searchPlaceholder={t("grievances.search")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("grievances.empty"),
        body: t("grievances.emptyBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          {/* The job list, first thing on the page. The banner it replaces said
              only how many were overdue, which answers half the question a
              queue is opened with: what needs me today, and how much of it. */}
          {counts && (
            <div className="queue-counts" role="group" aria-label={t("grievances.title")}>
              <QueueCount value={counts.late} label={t("grievances.countLate")} tone="late" />
              <QueueCount value={counts.due_this_week} label={t("grievances.countDueWeek")} tone="due" />
              <QueueCount
                value={counts.awaiting_acknowledgement}
                label={t("grievances.countUnacknowledged")}
                tone="due"
              />
              <QueueCount value={counts.restricted} label={t("grievances.countRestricted")} tone="calm" />
            </div>
          )}

          <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
            {filters.map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                className="pill-filter"
                data-active={filter.value === status ? "true" : undefined}
                onClick={() => setStatus(filter.value ? filter : null)}
              >
                {filter.label}
                <span className="pill-filter__count">{filter.count}</span>
              </button>
            ))}
          </div>

          {rows.length > 0 && (
            <>
              <div className="only-laptop">
                <Card className="table-card">
                  <table className={`table ${density}`}>
                    <thead>
                      <tr>
                        <th scope="col">{t("grievances.col.issue")}</th>
                        <th scope="col">{t("grievances.col.raisedBy")}</th>
                        <th scope="col">{t("grievances.tier")}</th>
                        <th scope="col">{t("grievances.col.location")}</th>
                        <th scope="col">{t("grievances.col.status")}</th>
                        <th scope="col">{t("grievances.col.due")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((grievance) => {
                        const tone = GRIEVANCE_TONE[grievance.status];
                        return (
                          <tr key={grievance.id} onClick={() => navigate(`/grievances/${grievance.id}`)}>
                            <td>
                              {/* A case file is a page, not a modal: it is
                                  worked over weeks by several people, and it
                                  has to be linkable and printable for a
                                  committee. The row keeps its peek behaviour
                                  nowhere — one destination, not two. */}
                              <button
                                type="button"
                                className="row-link"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  navigate(`/grievances/${grievance.id}`);
                                }}
                              >
                                {grievance.restricted
                                  ? grievance.short_reference
                                  : grievance.complaint_type_display}
                              </button>
                              {/* A restricted row shows its shape and nothing
                                  else: a reference, a date, a woreda. Removing
                                  the row instead would hide the fact that the
                                  mechanism received a disclosure at all. */}
                              <div className="t-meta">
                                {grievance.restricted ? t("grievances.restrictedRow") : grievance.summary}
                              </div>
                            </td>
                            <td>
                              <div>{grievance.restricted ? "—" : grievance.raised_by_display}</div>
                              <div className="t-meta">
                                {grievance.restricted ? "" : grievance.complainant_name || t("common.none")}
                              </div>
                            </td>
                            {/* Without it a woreda appeal and a kebele case
                                are the same row — and after an appeal the two
                                carry the same summary, because the child is
                                heard on the complainant's own words. */}
                            <td>
                              <div>{grievance.tier_display}</div>
                              {grievance.parent_grievance && (
                                <div className="t-meta">{t("grievances.isAppeal")}</div>
                              )}
                            </td>
                            <td>
                              <div>{grievance.woreda}</div>
                              {/* Defence in depth. The server omits the subject
                                  from a restricted payload, so this branch
                                  should never have anything to render — but a
                                  client that renders whatever it happens to
                                  hold is one refactor away from rendering
                                  something it should not. */}
                              <div className="t-meta">
                                {grievance.restricted ? (
                                  "—"
                                ) : grievance.case ? (
                                  <Link
                                    className="row-link"
                                    to={`/cases/${grievance.case}`}
                                    onClick={(event) => event.stopPropagation()}
                                  >
                                    {grievance.youth_name || t("grievances.openCase")}
                                  </Link>
                                ) : (
                                  grievance.partner_name || grievance.youth_name || "—"
                                )}
                                {grievance.related_referral && (
                                  <>
                                    {" · "}
                                    <Link
                                      className="row-link"
                                      to={`/referrals?q=${encodeURIComponent(grievance.related_referral)}`}
                                      onClick={(event) => event.stopPropagation()}
                                    >
                                      {t("grievances.openReferral")}
                                    </Link>
                                  </>
                                )}
                              </div>
                            </td>
                            <td>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                                  <span className="chip__mark" aria-hidden>
                                    {tone.mark}
                                  </span>
                                  {grievance.status_display}
                                </span>

                                {grievance.referral_quality_feedback_flag && (
                                  <MutedChip style={{ fontSize: 12 }}>{t("grievances.referralFeedback")}</MutedChip>
                                )}
                              </div>
                            </td>
                            {/* Time remaining, not age. The column it replaces
                                counted days since the record was created and
                                kept counting after resolution, so every live
                                case looked equally fine until somebody read
                                all of them. */}
                            <td>
                              <DueCell grievance={grievance} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </Card>
              </div>

              <div className="only-phone" style={{ gap: 12 }}>
                {sorted.map((grievance) => {
                  const tone = GRIEVANCE_TONE[grievance.status];
                  return (
                    <Card
                      key={grievance.id}
                      onClick={() => navigate(`/grievances/${grievance.id}`)}
                      style={{ padding: "12px 14px" }}
                      hasOwnKeyboardTarget
                    >
                      <div style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between" }}>
                        <div style={{ minWidth: 0 }}>
                          <button
                            type="button"
                            className="row-link t-body-strong"
                            onClick={(event) => {
                              event.stopPropagation();
                              navigate(`/grievances/${grievance.id}`);
                            }}
                          >
                            {grievance.restricted
                              ? grievance.short_reference
                              : grievance.complaint_type_display}
                          </button>
                          <div className="t-meta">
                            {grievance.restricted
                              ? grievance.woreda
                              : `${t("grievances.raisedBy", { who: grievance.raised_by_display })} · ${grievance.woreda}`}
                          </div>
                        </div>
                        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                          <span className="chip__mark" aria-hidden>
                            {tone.mark}
                          </span>
                          {grievance.status_display}
                        </span>
                      </div>
                      {/* The card said the category and printed the summary
                          while the table beside it showed a reference. Same
                          rule in both, or a phone leaks what a laptop does
                          not. */}
                      <p style={{ marginTop: 8 }}>
                        {grievance.restricted ? t("grievances.restrictedRow") : grievance.summary}
                      </p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        {/* The same clock as the table's Due column. The card
                            printed an age while the table beside it printed a
                            deadline, which is two answers to one question. */}
                        <MutedChip style={{ fontSize: 12 }}>
                          <DueCell grievance={grievance} />
                        </MutedChip>
                        {grievance.referral_quality_feedback_flag && (
                          <MutedChip style={{ fontSize: 12 }}>{t("grievances.referralFeedback")}</MutedChip>
                        )}
                      </div>
                    </Card>
                  );
                })}
              </div>
            </>
          )}

          {/* The detail modal is gone. A grievance is worked over weeks by
              several people, so it needed to be a page — linkable, printable
              for a committee, and with room for a timeline. Its lifecycle
              actions moved with it, including the gate that keeps Resolve and
              Close disabled until somebody has written what happened.
              `/grievances/:id` is now the only destination. */}

          <Modal
            open={creating}
            title={t("grievances.add")}
            okText={t("common.save")}
            cancelText={t("common.cancel")}
            confirmLoading={busy}
            okButtonProps={{ disabled: !canSubmitCreate }}
            onCancel={() => setCreating(false)}
            onOk={() => void submitCreate()}
          >
            <div className="stack" style={{ gap: 14 }}>
              {/* The divert. Choosing safeguarding does not merely tag the
                  record — it changes what this form asks for. Programme staff
                  do not investigate, so the fields that invite an
                  investigation are removed rather than left optional. */}
              {isSafeguarding && (
                <div className="callout callout--warn" role="note">
                  <p style={{ margin: 0 }}>{t("grievances.safeguardingIntro")}</p>
                </div>
              )}

              <div hidden={isSafeguarding}>
                <CapsLabel>{t("grievances.case")}</CapsLabel>
                <Select
                  showSearch
                  filterOption={false}
                  value={createDraft.case || undefined}
                  placeholder={t("grievances.casePlaceholder")}
                  style={{ width: "100%", marginTop: 6 }}
                  onSearch={(value) => void loadCases(value)}
                  onChange={(value) => setCreateDraft((current) => ({ ...current, case: value }))}
                  options={caseOptions.map((row) => ({
                    value: row.id,
                    label: `${row.youth.full_name} · ${row.woreda}`,
                  }))}
                />
              </div>

              <div className="grid-pairs">
                <div>
                  <CapsLabel>{t("grievances.type")}</CapsLabel>
                  <Select
                    value={createDraft.complaint_type}
                    style={{ width: "100%", marginTop: 6 }}
                    onChange={(value) =>
                      setCreateDraft((current) => ({
                        ...current,
                        complaint_type: value,
                        // Choosing safeguarding switches the form to the
                        // restricted path and clears anything already typed.
                        // A narrative written for the ordinary form — who said
                        // what about whom — is exactly what must not be kept
                        // once the category changes under it.
                        ...(value === "SAFEGUARDING"
                          ? { summary: "", complainant_name: "", complainant_contact: "", case: "" }
                          : {}),
                      }))
                    }
                    options={[
                      { value: "SERVICE_QUALITY", label: t("grievances.typeServiceQuality") },
                      { value: "REFERRAL_QUALITY", label: t("grievances.typeReferralQuality") },
                      { value: "REFERRAL_DELAY", label: t("grievances.typeReferralDelay") },
                      { value: "SELECTION", label: t("grievances.typeSelection") },
                      { value: "PAYMENT", label: t("grievances.typePayment") },
                      { value: "WORKPLACE", label: t("grievances.typeWorkplace") },
                      // Both of these existed in the model and in neither
                      // dropdown, so the two most serious categories could only
                      // be filed by mislabelling them as something else.
                      { value: "STAFF_CONDUCT", label: t("grievances.typeStaffConduct") },
                      { value: "SAFEGUARDING", label: t("grievances.typeSafeguarding") },
                      { value: "OTHER", label: t("grievances.typeOther") },
                    ]}
                  />
                </div>
                <div>
                  <CapsLabel>{t("grievances.col.raisedBy")}</CapsLabel>
                  <Select
                    value={createDraft.raised_by}
                    style={{ width: "100%", marginTop: 6 }}
                    onChange={(value) => setCreateDraft((current) => ({ ...current, raised_by: value }))}
                    options={[
                      { value: "YOUTH", label: t("grievances.byYouth") },
                      { value: "EMPLOYER", label: t("grievances.byEmployer") },
                      { value: "TRAINER", label: t("grievances.byTrainer") },
                      { value: "PARTNER", label: t("grievances.byPartner") },
                    ]}
                  />
                </div>
              </div>

              <div>
                <CapsLabel>{t("grievances.summaryLabel")}</CapsLabel>
                <Input.TextArea
                  rows={4}
                  value={createDraft.summary}
                  onChange={(event) => setCreateDraft((current) => ({ ...current, summary: event.target.value }))}
                />
              </div>

              {/* Not asked for on the restricted path. A name typed here is a
                  name in a record that a survivor was told would stay with one
                  person, and "optional" is not the same as absent. */}
              {!isSafeguarding && (
                <div className="grid-pairs">
                  <div>
                    <CapsLabel>{t("grievances.complainant")}</CapsLabel>
                    <Input
                      value={createDraft.complainant_name}
                      onChange={(event) =>
                        setCreateDraft((current) => ({ ...current, complainant_name: event.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <CapsLabel>{t("grievances.contact")}</CapsLabel>
                    <Input
                      value={createDraft.complainant_contact}
                      onChange={(event) =>
                        setCreateDraft((current) => ({ ...current, complainant_contact: event.target.value }))
                      }
                    />
                  </div>
                </div>
              )}

              {isSafeguarding && (
                <p className="t-meta" style={{ margin: 0 }}>{t("grievances.safeguardingLogged")}</p>
              )}
            </div>
          </Modal>
        </>
      )}
    </ListPage>
  );
}
