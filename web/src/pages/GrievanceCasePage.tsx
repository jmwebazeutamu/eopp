import { App, Input, Modal, Select } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Grievance, GrievanceEvent, GrievanceOutcome } from "../api/types";
import { Button, CapsLabel, Card, Field } from "../components/ui";
import { GRIEVANCE_TONE } from "../design/sprint6Status";
import { useLang } from "../i18n/LanguageContext";
import type { StringKey } from "../i18n/strings";
import { clockLabel } from "./grievanceClock";

/** The steps the workflow offers, as one keyed table rather than five dialogs
 *  whose copy would drift apart within a sprint. */
type Step = "acknowledge" | "decide" | "pause" | "close" | "appeal" | "refer";

const STEP_PATH: Record<Step, string> = {
  acknowledge: "acknowledge",
  decide: "decide",
  pause: "pause",
  close: "close",
  appeal: "appeal",
  refer: "refer-out",
};

const STEP_TITLE: Record<Step, StringKey> = {
  acknowledge: "grievances.acknowledge",
  decide: "grievances.decide",
  pause: "grievances.pause",
  close: "grievances.closeWithFeedback",
  appeal: "grievances.appeal",
  refer: "grievances.referOut",
};

const STEP_HELP: Record<Step, StringKey> = {
  acknowledge: "grievances.acknowledgeHelp",
  decide: "grievances.decideHelp",
  pause: "grievances.pauseHelp",
  close: "grievances.closeFeedbackHelp",
  appeal: "grievances.appealHelp",
  refer: "grievances.referHelp",
};

const STEP_FIELD: Record<Step, StringKey> = {
  acknowledge: "grievances.acknowledgeMethod",
  decide: "grievances.outcomeReason",
  pause: "grievances.pauseReason",
  close: "grievances.feedbackMethod",
  appeal: "grievances.appealGround",
  refer: "grievances.referredTo",
};

const STEP_OK: Record<Step, StringKey> = {
  acknowledge: "grievances.acknowledgedOk",
  decide: "grievances.decidedOk",
  pause: "grievances.pausedOk",
  close: "grievances.closed",
  appeal: "grievances.appealedOk",
  refer: "grievances.referredOk",
};

/**
 * One complaint, as a page.
 *
 * It was a modal. A grievance is worked over weeks by several people, and a
 * modal cannot be linked to, cannot be printed for a committee meeting, loses
 * its scroll position, and has nowhere to put a timeline. It also traps the
 * reader: no breadcrumb, no way to the next case.
 *
 * Two columns. The **timeline is the main column**, because the question this
 * page is opened with is "what has happened to this so far" — which the old
 * modal could not answer at all: the status was one word and the notes were one
 * overwritable field.
 *
 * The original statement sits at the top of the timeline and is never editable.
 * A grievance record is evidence, and the complainant's own words are the one
 * thing on it that nobody may improve. Corrections are appended.
 */
export default function GrievanceCasePage() {
  const { grievanceId } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();

  const [grievance, setGrievance] = useState<Grievance | null>(null);
  const [events, setEvents] = useState<GrievanceEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);
  const [method, setMethod] = useState("");
  // The decision, and what was done about it. Kept gated exactly as the modal
  // this page replaces gated it — Resolve and Close stay disabled until
  // somebody has written what happened. That was the single best decision in
  // the old screen and it survives unchanged.
  // One dialog for the whole workflow, keyed by which step is being taken.
  // Five separate modals with five sets of state was the alternative, and four
  // of them would have drifted.
  const [step, setStep] = useState<Step | null>(null);
  const [actionNotes, setActionNotes] = useState("");
  const [outcome, setOutcome] = useState<GrievanceOutcome>("UPHELD");
  const [chaseDate, setChaseDate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const record = await api.get<Grievance>(`/grievances/${grievanceId}/`);
      setGrievance(record.data);
      setFailed(null);
      // The timeline is a second request on purpose: a restricted record
      // answers the first and refuses the second, so the page can show the
      // shape of the case and say plainly why it cannot show the contents.
      try {
        const file = await api.get<{ events: GrievanceEvent[] }>(`/grievances/${grievanceId}/timeline/`);
        setEvents(file.data.events);
      } catch {
        setEvents([]);
      }
    } catch (error) {
      setFailed(errorMessage(error, t("grievances.loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [grievanceId, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function closeStep() {
    setStep(null);
    setActionNotes("");
    setChaseDate("");
  }

  /** What each step will not submit without. The same gates the server holds —
   *  said here first so the reader is not told after a round trip. */
  const canSubmitStep =
    step === "pause" ? Boolean(actionNotes.trim() && chaseDate) : Boolean(actionNotes.trim());

  async function submitStep() {
    if (!step) return;
    const body: Record<string, string> = {};
    if (step === "decide") {
      body.outcome = outcome;
      body.reason = actionNotes.trim();
    } else if (step === "pause") {
      body.reason = actionNotes.trim();
      body.chase_date = chaseDate;
    } else if (step === "close") {
      body.method = actionNotes.trim();
    } else if (step === "appeal") {
      body.ground = actionNotes.trim();
    } else if (step === "refer") {
      body.to = actionNotes.trim();
    }
    const done = await move(STEP_PATH[step], body, STEP_OK[step], "grievances.startFailed");
    closeStep();
    return done;
  }

  async function submitNote() {
    if (!note.trim()) return;
    setSavingNote(true);
    try {
      await api.post(`/grievances/${grievanceId}/notes/`, { body: note.trim() });
      message.success(t("grievances.noteSaved"));
      setNote("");
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.loadFailed")));
    } finally {
      setSavingNote(false);
    }
  }

  async function submitAcknowledgement() {
    setSavingNote(true);
    try {
      await api.post(`/grievances/${grievanceId}/acknowledge/`, { method: method.trim() });
      message.success(t("grievances.acknowledgedOk"));
      setStep(null);
      setMethod("");
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("grievances.loadFailed")));
    } finally {
      setSavingNote(false);
    }
  }

  async function move(path: string, body: Record<string, string>, ok: StringKey, failed: StringKey) {
    setSavingNote(true);
    try {
      await api.post(`/grievances/${grievanceId}/${path}/`, body);
      message.success(t(ok));
      setStep(null);
      setActionNotes("");
      await load();
    } catch (error) {
      message.error(errorMessage(error, t(failed)));
    } finally {
      setSavingNote(false);
    }
  }

  if (loading && !grievance) return <div className="page t-meta">{t("common.loading")}</div>;
  if (failed) {
    return (
      <div className="page stack">
        <Card>
          <strong>{t("grievances.loadFailed")}</strong>
          <p className="t-meta">{failed}</p>
          <Button onClick={() => navigate("/grievances")}>{t("grievances.backToQueue")}</Button>
        </Card>
      </div>
    );
  }
  if (!grievance) return null;

  const tone = GRIEVANCE_TONE[grievance.status];
  const clock = clockLabel(grievance.standing);
  const canWrite = grievance.can_act;

  return (
    <div className="page stack">
      <nav className="t-meta" aria-label={t("grievances.backToQueue")}>
        <button type="button" className="row-link" onClick={() => navigate("/grievances")}>
          {t("grievances.backToQueue")}
        </button>
        <span aria-hidden> › </span>
        <span>{grievance.short_reference}</span>
      </nav>

      <section className="card" aria-labelledby="case-title">
        <div className="chip-row">
          <h1 id="case-title" className="group-title">
            {grievance.short_reference}
            {!grievance.restricted && ` · ${grievance.complaint_type_display}`}
          </h1>
          <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
            <span className="chip__mark" aria-hidden>
              {tone.mark}
            </span>
            {grievance.status_display}
          </span>
          <span className="due-cell" data-tone={clock.tone}>
            {t(clock.key, { days: clock.days })}
          </span>
          <span className="t-meta">{grievance.tier_display}</span>
        </div>

        {/* An appeal is heard on the complainant's own words, so parent and
            child carry the same statement. Without this line the two records
            are indistinguishable on screen. */}
        {grievance.parent_grievance && (
          <p className="t-meta" style={{ margin: "8px 0 0" }}>
            <button
              type="button"
              className="row-link"
              onClick={() => navigate(`/grievances/${grievance.parent_grievance}`)}
            >
              {t("grievances.appealAgainst")}
            </button>
          </p>
        )}
      </section>

      {/* The workflow, as the buttons the state actually allows. Every one of
          these is a POST to its own path, not a PATCH of `status`: a PATCH
          would say what the record should become and skip every gate that says
          whether it may. The server refuses an edge it does not have, and its
          sentence is what the reader sees. */}
      {canWrite && grievance.is_open && !grievance.restricted && (
        <div className="chip-row">
          {grievance.status === "RECEIVED" && (
            <Button variant="primary" onClick={() => setStep("acknowledge")}>
              {t("grievances.acknowledge")}
            </Button>
          )}
          {grievance.status === "ACKNOWLEDGED" && (
            <Button
              variant="primary"
              disabled={savingNote}
              onClick={() => void move("start-review", {}, "grievances.started", "grievances.startFailed")}
            >
              {t("grievances.startReview")}
            </Button>
          )}
          {grievance.status === "UNDER_REVIEW" && (
            <>
              <Button variant="primary" onClick={() => setStep("decide")}>
                {t("grievances.decide")}
              </Button>
              <Button onClick={() => setStep("pause")}>{t("grievances.pause")}</Button>
            </>
          )}
          {grievance.status === "AWAITING_COMPLAINANT" && (
            <Button
              variant="primary"
              disabled={savingNote}
              onClick={() => void move("resume", {}, "grievances.resumed", "grievances.startFailed")}
            >
              {t("grievances.resume")}
            </Button>
          )}
          {grievance.status === "DECIDED" && (
            <Button variant="primary" onClick={() => setStep("close")}>
              {t("grievances.closeWithFeedback")}
            </Button>
          )}
          <Button variant="destructive-soft" onClick={() => setStep("refer")}>
            {t("grievances.referOut")}
          </Button>
        </div>
      )}

      {/* From a closed case, inside the window. Separate from the row above
          because it is the complainant's move, not the programme's. */}
      {canWrite && grievance.status === "CLOSED" && !grievance.restricted && (
        <div className="chip-row">
          <Button onClick={() => setStep("appeal")}>{t("grievances.appeal")}</Button>
        </div>
      )}

      {/* A restricted record renders its shape and says why that is all. The
          page still exists, and still shows a deadline, so the mechanism can be
          held to it without anybody reading a survivor's account. */}
      {grievance.restricted ? (
        <Card>
          <p style={{ margin: 0 }}>{t("grievances.eventRestricted")}</p>
        </Card>
      ) : (
        <div className="record-overview">
          <div className="stack">
            <section className="card" aria-labelledby="timeline-title">
              <CapsLabel id="timeline-title">{t("grievances.timeline")}</CapsLabel>
              <ol className="case-timeline">
                {events.map((event, index) => (
                  <li key={`${event.at}-${index}`} className="case-event" data-kind={event.type}>
                    <div className="case-event__head">
                      <strong>{event.title}</strong>
                      <span className="t-meta tabular">{event.at}</span>
                    </div>
                    {event.body && <p className="case-event__body">{event.body}</p>}
                    <div className="t-meta">
                      {/* No dangling separator when nobody is named: a
                          service-created row has no actor, and "— · The
                          complainant's own words" reads as a missing name
                          rather than as an absent one. */}
                      {[event.actor, event.type === "STATEMENT" ? t("grievances.statementImmutable") : ""]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                  </li>
                ))}
              </ol>

              {canWrite && grievance.is_open && (
                <div className="stack" style={{ marginTop: 16, gap: 8 }}>
                  <CapsLabel>{t("grievances.addNote")}</CapsLabel>
                  <Input.TextArea
                    rows={3}
                    aria-label={t("grievances.addNote")}
                    placeholder={t("grievances.notePlaceholder")}
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                  />
                  <div className="t-meta">{t("grievances.noteHelp")}</div>
                  <div>
                    <Button variant="primary" disabled={!note.trim() || savingNote} onClick={() => void submitNote()}>
                      {t("grievances.addNote")}
                    </Button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <div className="stack">
            <section className="card" aria-labelledby="facts-title">
              <CapsLabel id="facts-title">{t("grievances.facts")}</CapsLabel>
              <div className="stack" style={{ gap: 10, marginTop: 8 }}>
                <Field label={t("grievances.complainant")}>{grievance.complainant_name || t("common.none")}</Field>
                <Field label={t("grievances.col.location")}>{grievance.woreda}</Field>
                {grievance.subject_label && (
                  <Field label={t("grievances.case")}>{grievance.subject_label}</Field>
                )}
                <Field label={t("grievances.severity")}>{grievance.severity_display}</Field>
                <Field label={t("grievances.raisedOn")}>{grievance.date_raised}</Field>
                <Field label={t("grievances.dueOn")}>{grievance.due_on ?? t("common.none")}</Field>
                <Field label={t("grievances.assignedTo")}>{grievance.assigned_staff_name}</Field>
              </div>
            </section>

            {/* The step most likely to be skipped and the one auditors check.
                Its absence is stated, not left as a blank field somebody has to
                notice. */}
            <section className="card" aria-labelledby="ack-title">
              <CapsLabel id="ack-title">{t("grievances.acknowledge")}</CapsLabel>
              {grievance.acknowledged_at ? (
                <p className="t-meta" style={{ margin: "8px 0 0" }}>
                  {t("grievances.acknowledged", {
                    date: grievance.acknowledged_at.slice(0, 10),
                    method: grievance.acknowledgement_method,
                  })}
                </p>
              ) : (
                <>
                  {/* States the absence; does not offer the action. The
                      workflow row above is where things are done, and the same
                      button in two places is two places for it to drift. */}
                  <p className="t-meta" style={{ margin: "8px 0 0" }}>{t("grievances.notAcknowledged")}</p>
                </>
              )}
            </section>
          </div>
        </div>
      )}

      {/* One dialog, five steps. Each names what it needs and refuses to
          submit without it, which is the same gate the server holds — the
          screen just says so before the round trip. */}
      <Modal
        open={step !== null && step !== "acknowledge"}
        title={step ? t(STEP_TITLE[step]) : ""}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={savingNote}
        okButtonProps={{ disabled: !canSubmitStep }}
        onCancel={closeStep}
        onOk={() => void submitStep()}
      >
        {step && <p className="t-meta">{t(STEP_HELP[step])}</p>}

        {step === "decide" && (
          <label style={{ display: "block", marginBottom: 12 }}>
            <span className="t-caps">{t("grievances.outcome")}</span>
            <Select
              value={outcome}
              style={{ width: "100%", marginTop: 6 }}
              onChange={(value) => setOutcome(value)}
              options={[
                { value: "UPHELD", label: t("grievances.outcomeUpheld") },
                { value: "PARTLY_UPHELD", label: t("grievances.outcomePartly") },
                { value: "NOT_UPHELD", label: t("grievances.outcomeNot") },
                { value: "REFERRED", label: t("grievances.outcomeReferred") },
                { value: "WITHDRAWN", label: t("grievances.outcomeWithdrawn") },
              ]}
            />
          </label>
        )}

        {step === "pause" && (
          <label style={{ display: "block", marginBottom: 12 }}>
            <span className="t-caps">{t("grievances.chaseDate")}</span>
            <Input type="date" value={chaseDate} onChange={(event) => setChaseDate(event.target.value)} />
          </label>
        )}

        <label>
          <span className="t-caps">{step ? t(STEP_FIELD[step]) : ""}</span>
          <Input.TextArea
            rows={4}
            aria-label={step ? t(STEP_FIELD[step]) : ""}
            value={actionNotes}
            onChange={(event) => setActionNotes(event.target.value)}
          />
        </label>
      </Modal>

      <Modal
        open={step === "acknowledge"}
        title={t("grievances.acknowledge")}
        okText={t("common.save")}
        cancelText={t("common.cancel")}
        confirmLoading={savingNote}
        okButtonProps={{ disabled: !method.trim() }}
        onCancel={closeStep}
        onOk={() => void submitAcknowledgement()}
      >
        <p className="t-meta">{t("grievances.acknowledgeHelp")}</p>
        <label>
          <span className="t-caps">{t("grievances.acknowledgeMethod")}</span>
          <Input value={method} onChange={(event) => setMethod(event.target.value)} />
        </label>
      </Modal>
    </div>
  );
}
