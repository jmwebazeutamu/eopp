import { App, Input, InputNumber } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { WltAttendanceStatus, WltMeetingRegister } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card, PageHeader } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import MeetingLending from "./MeetingLending";

/**
 * One meeting's register — attendance, savings, and the cash count.
 *
 * This is the operational act of the whole module. Every figure on the
 * readiness card is computed from closed meetings and the ledger, so until a
 * meeting closes there is nothing for them to read. Every service underneath
 * was built and tested at stage 1; what did not exist was any screen, so the
 * numbers a facilitator sees could only be produced by a seeding command.
 *
 * Three decisions shape it:
 *
 * - **It reads before it writes.** The ledger appends and has no update path,
 *   so posting a woman's contribution twice doubles it and the correction is a
 *   reversal with a reason. `GET .../register/` returns what is already
 *   recorded, and a woman with an entry is shown her total rather than offered
 *   the button again.
 * - **Attendance saves per row, not on a submit.** A meeting is registered
 *   while it happens, on a phone, in a room; a form that lost twenty marks
 *   because the connection dropped at the end would be worse than paper.
 * - **The close is the only thing that can fail loudly.** The server refuses an
 *   unbalanced till and says by how much, and that refusal raises a risk flag
 *   that outlives it. The screen passes that message straight through — it is
 *   the product, not an error string.
 */

const ATTENDANCE: WltAttendanceStatus[] = ["PRESENT", "LATE", "ABSENT", "ABSENT_EXCUSED"];

export default function MeetingPage() {
  const { groupId, meetingId } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [data, setData] = useState<WltMeetingRegister | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [counted, setCounted] = useState<number | null>(null);
  const [topic, setTopic] = useState("");
  const [closing, setClosing] = useState(false);

  const canWrite = Boolean(user?.access.group_write);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<WltMeetingRegister>(`/wlt/meetings/${meetingId}/register/`);
      setData(response.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.meetingLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [meetingId, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !data) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!data) return null;

  const isOpen = data.meeting.status === "OPEN";
  const contribution = data.contribution_etb ? Number(data.contribution_etb) : 0;
  const present = data.members.filter((row) => row.attendance === "PRESENT" || row.attendance === "LATE").length;
  const recorded = data.members.filter((row) => row.saved_etb !== null).length;

  async function mark(person: string, status: WltAttendanceStatus) {
    setBusy(`att:${person}`);
    try {
      await api.post(`/wlt/meetings/${meetingId}/attendance/`, { rows: [{ person, status }] });
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.attendanceFailed")));
    } finally {
      setBusy(null);
    }
  }

  async function save(person: string) {
    setBusy(`sav:${person}`);
    try {
      await api.post(`/wlt/meetings/${meetingId}/savings/`, { person, amount_etb: String(contribution) });
      await load();
    } catch (error) {
      message.error(errorMessage(error, t("wlt.savingFailed")));
    } finally {
      setBusy(null);
    }
  }

  async function close() {
    if (counted === null) return;
    setClosing(true);
    try {
      await api.post(`/wlt/meetings/${meetingId}/close/`, {
        counted_cash_etb: String(counted),
        social_topic: topic.trim(),
      });
      message.success(t("wlt.meetingWasClosed"));
      await load();
    } catch (error) {
      // The server's sentence names the difference and which way it runs. It is
      // the whole point of the reconciliation, so it is passed through.
      message.error(errorMessage(error, t("wlt.closeFailed")));
    } finally {
      setClosing(false);
    }
  }

  return (
    <div className="page stack">
      <PageHeader
        title={t("wlt.meetingNo", { no: data.meeting.meeting_no })}
        subtitle={
          <span>
            {data.group_name} · {t("wlt.meetingHeld", { date: data.meeting.held_on })} ·{" "}
            {isOpen ? t("wlt.meetingOpen") : t("wlt.meetingClosed")}
          </span>
        }
        action={<Button onClick={() => navigate(`/wlt/groups/${groupId}`)}>{t("wlt.backToGroup")}</Button>}
      />

      {!isOpen && (
        <Card className="card--tight">
          <p style={{ margin: 0 }}>
            {t("wlt.meetingClosedOn", {
              date: data.meeting.held_on,
              amount: data.meeting.counted_cash_etb ?? "0",
            })}
          </p>
        </Card>
      )}

      <Card className="card--tight">
        <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
          <CapsLabel>{t("wlt.attendanceLabel")}</CapsLabel>
          <span className="t-meta">{t("wlt.presentCount", { present, total: data.members.length })}</span>
        </div>

        <table className="roster-table">
          <tbody>
            {data.members.map((row) => (
              <tr key={row.person}>
                <td style={{ fontWeight: 600 }}>{row.full_name}</td>
                <td style={{ textAlign: "right" }}>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", justifyContent: "flex-end" }}>
                    {ATTENDANCE.map((status) => (
                      <Button
                        key={status}
                        size="sm"
                        variant={row.attendance === status ? "primary" : "secondary"}
                        disabled={!isOpen || !canWrite || busy === `att:${row.person}`}
                        onClick={() => void mark(row.person, status)}
                      >
                        {t(`wlt.att${status}`)}
                      </Button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card className="card--tight">
        <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
          <CapsLabel>{t("wlt.savingsLabel")}</CapsLabel>
          <span className="t-meta">{t("wlt.savedCount", { count: recorded, total: data.members.length })}</span>
        </div>

        <table className="roster-table">
          <tbody>
            {data.members.map((row) => (
              <tr key={row.person}>
                <td style={{ fontWeight: 600 }}>{row.full_name}</td>
                <td style={{ textAlign: "right" }}>
                  {/* Already recorded: her total, not the button. Pressing it
                      again would append a second entry rather than replace the
                      first, and correcting that is a reversal with a reason. */}
                  {row.saved_etb !== null ? (
                    <span className="officer-tag">{t("wlt.savedAlready", { amount: row.saved_etb })}</span>
                  ) : (
                    <Button
                      size="sm"
                      disabled={!isOpen || !canWrite || contribution <= 0 || busy === `sav:${row.person}`}
                      onClick={() => void save(row.person)}
                    >
                      {t("wlt.recordSaving", { amount: contribution })}
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* Above the close, because both halves of it change what should be in
          the box — the count at the end has to balance around them. */}
      <MeetingLending meetingId={meetingId ?? ""} data={data} canWrite={canWrite} onChanged={load} />

      {isOpen && canWrite && (
        <Card className="card--tight">
          <CapsLabel>{t("wlt.closeMeeting")}</CapsLabel>
          <p className="t-meta">{t("wlt.closeMeetingHelp")}</p>

          <div className="indicator-cols" style={{ alignItems: "flex-end" }}>
            <div className="indicator-col">
              <span className="t-meta">{t("wlt.expectedCash")}</span>
              <div className="tabular" style={{ fontWeight: 700 }}>
                {data.expected_cash_etb} ETB
              </div>
            </div>
            <div className="indicator-col">
              <label>
                <span className="t-caps">{t("wlt.countedCash")}</span>
                <InputNumber
                  min={0}
                  step={1}
                  value={counted}
                  onChange={(value) => setCounted(value)}
                  style={{ width: "100%" }}
                />
              </label>
            </div>
            <div className="indicator-col">
              <label>
                <span className="t-caps">{t("wlt.socialTopic")}</span>
                <Input value={topic} onChange={(event) => setTopic(event.target.value)} />
              </label>
            </div>
          </div>

          <div style={{ marginTop: 12 }}>
            <Button variant="primary" disabled={counted === null || closing} onClick={() => void close()}>
              {t("wlt.closeMeeting")}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
