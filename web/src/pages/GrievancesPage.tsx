import { App, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { CaseListRow, Grievance, Paginated, Summary } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ListPage from "../components/ListPage";
import { Button, Card, CapsLabel, Field, MutedChip } from "../components/ui";
import { GRIEVANCE_TONE } from "../design/sprint6Status";
import { useLang } from "../i18n/LanguageContext";

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
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<Grievance[]>([]);
  const [overdue, setOverdue] = useState<Grievance[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Grievance | null>(null);
  const [creating, setCreating] = useState(false);
  const [caseOptions, setCaseOptions] = useState<CaseListRow[]>([]);
  const [draft, setDraft] = useState({ summary: "", complainant_name: "", complainant_contact: "" });
  const [createDraft, setCreateDraft] = useState({
    case: "",
    complaint_type: "SERVICE_QUALITY",
    raised_by: "YOUTH",
    summary: "",
    complainant_name: "",
    complainant_contact: "",
  });
  const [actionNotes, setActionNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const status = params.get("resolution_status") ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, late, counters] = await Promise.all([
        api.get<Paginated<Grievance>>("/grievances/", {
          params: { page_size: 200, search, resolution_status: status || undefined },
        }),
        api.get<{ threshold_days: number; results: Grievance[] }>("/grievances/overdue/"),
        api.get<Summary>("/grievances/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setOverdue(late.data.results ?? []);
      setSummary(counters.data);
      setSelected((current) => {
        if (!current) return null;
        return list.data.results.find((row) => row.id === current.id) ?? current;
      });
    } catch (error) {
      message.error(errorMessage(error, t("grievances.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selected) return;
    setDraft({
      summary: selected.summary,
      complainant_name: selected.complainant_name,
      complainant_contact: selected.complainant_contact,
    });
    setActionNotes(
      selected.resolution_status === "RESOLVED" || selected.resolution_status === "CLOSED" ? selected.resolution_notes : "",
    );
  }, [selected]);

  async function loadCases(search = "") {
    const response = await api.get<Paginated<CaseListRow>>("/cases/", {
      params: { page_size: 25, search: search || undefined },
    });
    setCaseOptions(response.data.results);
  }

  function setStatus(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("resolution_status", next);
    else updated.delete("resolution_status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  async function saveUpdate() {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await api.patch<Grievance>(`/grievances/${selected.id}/`, draft);
      setSelected(response.data);
      message.success(t("grievances.updated"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.updateFailed")));
    } finally {
      setBusy(false);
    }
  }

  async function startWork() {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await api.post<Grievance>(`/grievances/${selected.id}/start/`);
      setSelected(response.data);
      message.success(t("grievances.started"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.startFailed")));
    } finally {
      setBusy(false);
    }
  }

  async function submitResolution() {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await api.post<Grievance>(`/grievances/${selected.id}/resolve/`, { notes: actionNotes });
      setSelected(response.data);
      message.success(t("grievances.resolved"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.resolveFailed")));
    } finally {
      setBusy(false);
    }
  }

  async function submitClose() {
    if (!selected) return;
    setBusy(true);
    try {
      const response = await api.post<Grievance>(`/grievances/${selected.id}/close/`, { reason: actionNotes });
      setSelected(response.data);
      message.success(t("grievances.closed"));
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.closeFailed")));
    } finally {
      setBusy(false);
    }
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
      setSelected(response.data);
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

  const canWrite = Boolean(user?.access.case_write);
  const overdueIds = new Set(overdue.map((row) => row.id));
  // Overdue first: the delay is the programme's, not the complainant's.
  const sorted = [...rows].sort((left, right) => {
    const lateLeft = overdueIds.has(left.id) ? 0 : 1;
    const lateRight = overdueIds.has(right.id) ? 0 : 1;
    if (lateLeft !== lateRight) return lateLeft - lateRight;
    return right.date_raised.localeCompare(left.date_raised);
  });

  const filters = [
    { value: "", label: t("grievances.all"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).map((counter) => ({
      value: String(counter.value),
      label: counter.label,
      count: counter.count,
    })),
  ];

  const hasDraftChanges =
    selected !== null &&
    (draft.summary !== selected.summary ||
      draft.complainant_name !== selected.complainant_name ||
      draft.complainant_contact !== selected.complainant_contact);
  const canSubmitTerminalAction = actionNotes.trim().length > 0;
  const canCreate = Boolean(user?.access.case_write);
  const canSubmitCreate = createDraft.case !== "" && createDraft.summary.trim().length > 0;

  return (
    <ListPage
      title={t("grievances.title")}
      subtitle={t("grievances.subtitle", { count: total })}
      action={
        canCreate ? (
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

          {overdue.length > 0 && (
            <Card style={{ marginBottom: 16 }}>
              <strong>{t("grievances.overdueHeading", { count: overdue.length })}</strong>
              <div className="t-meta">{t("grievances.overdueBody")}</div>
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

          {rows.length > 0 && (
            <>
              <div className="only-laptop">
                <Card className="table-card">
                  <table className={`table ${density}`}>
                    <thead>
                      <tr>
                        <th scope="col">{t("grievances.col.issue")}</th>
                        <th scope="col">{t("grievances.col.raisedBy")}</th>
                        <th scope="col">{t("grievances.col.location")}</th>
                        <th scope="col">{t("grievances.col.status")}</th>
                        <th scope="col">{t("grievances.col.age")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((grievance) => {
                        const tone = GRIEVANCE_TONE[grievance.resolution_status];
                        return (
                          <tr key={grievance.id} onClick={() => setSelected(grievance)}>
                            <td>
                              <button
                                type="button"
                                className="row-link"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelected(grievance);
                                }}
                              >
                                {grievance.complaint_type_display}
                              </button>
                              <div className="t-meta">{grievance.summary}</div>
                            </td>
                            <td>
                              <div>{grievance.raised_by_display}</div>
                              <div className="t-meta">{grievance.complainant_name || t("common.none")}</div>
                            </td>
                            <td>
                              <div>{grievance.woreda}</div>
                              <div className="t-meta">
                                {grievance.case ? (
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
                                {overdueIds.has(grievance.id) && (
                                  <MutedChip style={{ fontSize: 12 }}>{t("grievances.overdueChip")}</MutedChip>
                                )}
                                {grievance.referral_quality_feedback_flag && (
                                  <MutedChip style={{ fontSize: 12 }}>{t("grievances.referralFeedback")}</MutedChip>
                                )}
                              </div>
                            </td>
                            <td>{t("grievances.openDays", { days: grievance.days_open })}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </Card>
              </div>

              <div className="only-phone" style={{ gap: 12 }}>
                {sorted.map((grievance) => {
                  const tone = GRIEVANCE_TONE[grievance.resolution_status];
                  return (
                    <Card
                      key={grievance.id}
                      onClick={() => setSelected(grievance)}
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
                              setSelected(grievance);
                            }}
                          >
                            {grievance.complaint_type_display}
                          </button>
                          <div className="t-meta">
                            {t("grievances.raisedBy", { who: grievance.raised_by_display })} · {grievance.woreda}
                          </div>
                        </div>
                        <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
                          <span className="chip__mark" aria-hidden>
                            {tone.mark}
                          </span>
                          {grievance.status_display}
                        </span>
                      </div>
                      <p style={{ marginTop: 8 }}>{grievance.summary}</p>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <MutedChip style={{ fontSize: 12 }}>
                          {t("grievances.openDays", { days: grievance.days_open })}
                        </MutedChip>
                        {overdueIds.has(grievance.id) && (
                          <MutedChip style={{ fontSize: 12 }}>{t("grievances.overdueChip")}</MutedChip>
                        )}
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

          <Modal
            open={selected !== null}
            title={selected?.complaint_type_display}
            onCancel={() => setSelected(null)}
            width={720}
            footer={
              selected ? (
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: 8 }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {canWrite && selected.resolution_status === "OPEN" && (
                      <Button onClick={() => void startWork()} disabled={busy}>
                        {t("grievances.start")}
                      </Button>
                    )}
                    {canWrite && selected.is_open && (
                      <Button variant="destructive-soft" onClick={() => void submitClose()} disabled={busy || !canSubmitTerminalAction}>
                        {t("grievances.close")}
                      </Button>
                    )}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                    {canWrite && (
                      <Button onClick={() => void saveUpdate()} disabled={busy || !hasDraftChanges}>
                        {t("grievances.update")}
                      </Button>
                    )}
                    {canWrite && selected.is_open && (
                      <Button variant="primary" onClick={() => void submitResolution()} disabled={busy || !canSubmitTerminalAction}>
                        {t("grievances.resolve")}
                      </Button>
                    )}
                  </div>
                </div>
              ) : null
            }
          >
            {selected && (
              <div className="stack" style={{ gap: 14 }}>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <MutedChip>{selected.status_display}</MutedChip>
                  <MutedChip>{t("grievances.openDays", { days: selected.days_open })}</MutedChip>
                  {selected.is_sensitive && <MutedChip>{t("grievances.sensitive")}</MutedChip>}
                  {selected.referral_quality_feedback_flag && <MutedChip>{t("grievances.referralFeedback")}</MutedChip>}
                </div>

                <div className="grid-pairs">
                  <Field label={t("grievances.col.raisedBy")}>{selected.raised_by_display}</Field>
                  <Field label={t("grievances.col.location")}>{selected.woreda}</Field>
                  <Field label={t("grievances.complainant")}>{selected.complainant_name || t("common.none")}</Field>
                  <Field label={t("grievances.contact")}>{selected.complainant_contact || t("common.none")}</Field>
                  <Field label={t("grievances.assignedTo")}>{selected.assigned_staff_name}</Field>
                  <Field label={t("grievances.relatedTo")}>
                    {selected.case ? (
                      <Link className="row-link" to={`/cases/${selected.case}`}>
                        {selected.youth_name || t("grievances.openCase")}
                      </Link>
                    ) : (
                      selected.partner_name || selected.youth_name || "—"
                    )}
                    {selected.related_referral && (
                      <div style={{ marginTop: 4 }}>
                        <Link className="row-link" to={`/referrals?q=${encodeURIComponent(selected.related_referral)}`}>
                          {t("grievances.openReferral")}
                        </Link>
                      </div>
                    )}
                  </Field>
                </div>

                <div>
                  <CapsLabel>{t("grievances.summaryLabel")}</CapsLabel>
                  {canWrite ? (
                    <Input.TextArea
                      rows={4}
                      aria-label={t("grievances.summaryLabel")}
                      value={draft.summary}
                      onChange={(event) => setDraft((current) => ({ ...current, summary: event.target.value }))}
                    />
                  ) : (
                    <div style={{ marginTop: 6 }}>{selected.summary}</div>
                  )}
                </div>

                {canWrite && (
                  <div className="grid-pairs">
                    <div>
                      <CapsLabel>{t("grievances.complainant")}</CapsLabel>
                      <Input
                        aria-label={t("grievances.complainant")}
                        value={draft.complainant_name}
                        onChange={(event) => setDraft((current) => ({ ...current, complainant_name: event.target.value }))}
                      />
                    </div>
                    <div>
                      <CapsLabel>{t("grievances.contact")}</CapsLabel>
                      <Input
                        aria-label={t("grievances.contact")}
                        value={draft.complainant_contact}
                        onChange={(event) => setDraft((current) => ({ ...current, complainant_contact: event.target.value }))}
                      />
                    </div>
                  </div>
                )}

                <div>
                  <CapsLabel>
                    {selected.is_open ? t("grievances.actionNotes") : t("grievances.whatWasDone")}
                  </CapsLabel>
                  {selected.is_open && canWrite ? (
                    <>
                      <p style={{ margin: "6px 0 8px" }}>{t("grievances.resolveBody")}</p>
                      <Input.TextArea
                        rows={4}
                        aria-label={t("grievances.actionNotes")}
                        value={actionNotes}
                        onChange={(event) => setActionNotes(event.target.value)}
                      />
                    </>
                  ) : (
                    <div style={{ marginTop: 6 }}>{selected.resolution_notes || t("common.none")}</div>
                  )}
                </div>
              </div>
            )}
          </Modal>

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
              <div>
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
                    onChange={(value) => setCreateDraft((current) => ({ ...current, complaint_type: value }))}
                    options={[
                      { value: "SERVICE_QUALITY", label: t("grievances.typeServiceQuality") },
                      { value: "REFERRAL_QUALITY", label: t("grievances.typeReferralQuality") },
                      { value: "REFERRAL_DELAY", label: t("grievances.typeReferralDelay") },
                      { value: "SELECTION", label: t("grievances.typeSelection") },
                      { value: "PAYMENT", label: t("grievances.typePayment") },
                      { value: "WORKPLACE", label: t("grievances.typeWorkplace") },
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
            </div>
          </Modal>
        </>
      )}
    </ListPage>
  );
}
