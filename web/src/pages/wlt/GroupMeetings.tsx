import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Paginated, WltGroup, WltMeeting } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import FundTrend from "./FundTrend";

/**
 * The group's meetings, and the way into recording one.
 *
 * Sits on the group screen because a meeting belongs to a group and because
 * this is the answer to "how do I change any of these numbers": every figure on
 * the readiness card is computed from closed meetings and the ledger, and until
 * this panel existed there was no route to either outside a shell.
 *
 * An open meeting leads. `open_meeting` always creates — it does **not** return
 * an existing one — so the button only offers to open when the list shows none,
 * and it names the open meeting's date rather than saying a bare "Open".
 *
 * That date matters more than it looks. A meeting left open from months ago
 * silently becomes the one everything is recorded into: savings, attendance and
 * any loan are dated to it, and the register then shows the roster as it stood
 * *then*, which for an old meeting can be empty. A bare "Open" button gave no
 * way to notice.
 */
/**
 * Today, in the reader's own date, as `YYYY-MM-DD`.
 *
 * Not `toISOString()`, which is UTC: the programme runs on Africa/Addis_Ababa
 * (UTC+3), so between midnight and 03:00 local the UTC date is still
 * yesterday — and every meeting opened today was flagged as held on another
 * day. `held_on` is a plain local date, so it has to be compared with one.
 * The false warning was visible in a screenshot at 02:56 local.
 */
function todayLocal(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export default function GroupMeetings({ group, compact = false }: { group: WltGroup; compact?: boolean }) {
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [meetings, setMeetings] = useState<WltMeeting[]>([]);
  const [total, setTotal] = useState(0);
  const [showAll, setShowAll] = useState(false);
  /** "", "CLOSED" or "OPEN". Local, not a route: it narrows a list inside one
   *  tab rather than naming a place worth linking to. */
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);

  /** How many to show before "show all". The money trail has to be reachable.
   *  On Overview it is five and there is no "show all" — the whole list is one
   *  tab away, and a second full list on the summary tab is the scroll the
   *  redesign removed. */
  const PAGE = compact ? 5 : 12;

  const canWrite = Boolean(user?.access.group_write);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The tiebreak matters: two meetings can be held on one date, and a
      // date-only sort then lists 31 above 32.
      const response = await api.get<Paginated<WltMeeting> | WltMeeting[]>("/wlt/meetings/", {
        params: {
          group: group.id,
          // The chart needs the last twelve closed meetings, so a filtered or
          // short list would draw a different picture from the table beneath
          // it. It reads its own window from the unfiltered fetch.
          page_size: showAll ? 500 : Math.max(PAGE, 12),
          ordering: "-held_on,-meeting_no",
          status: status || undefined,
        },
      });
      const rows = Array.isArray(response.data) ? response.data : response.data.results;
      setMeetings(rows);
      setTotal(Array.isArray(response.data) ? rows.length : response.data.count);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.meetingLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [compact, group.id, message, showAll, status, t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function open() {
    setOpening(true);
    try {
      const created = await api.post<WltMeeting>("/wlt/meetings/", { group: group.id });
      message.success(t("wlt.meetingOpened", { no: created.data.meeting_no }));
      navigate(`/wlt/groups/${group.id}/meetings/${created.data.id}`);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.meetingOpenFailed")));
    } finally {
      setOpening(false);
    }
  }

  const openMeeting = meetings.find((meeting) => meeting.status === "OPEN");

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <span style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
          <CapsLabel>{compact ? t("wlt.recentMeetings") : t("wlt.meetingsTitle")}</CapsLabel>
          {/* The true total, not the number of rows drawn. This listed twelve
              of thirty-two with nothing saying so, which put meetings 1 to 20
              out of reach and made the money trail unauditable. */}
          <span className="t-meta">{t("wlt.meetingCount", { count: total })}</span>
        </span>
        {canWrite && (
          <Button
            size="sm"
            variant={openMeeting ? "secondary" : "primary"}
            disabled={opening}
            onClick={() =>
              openMeeting ? navigate(`/wlt/groups/${group.id}/meetings/${openMeeting.id}`) : void open()
            }
          >
            {openMeeting ? t("wlt.resumeMeeting", { date: openMeeting.held_on }) : t("wlt.openMeeting")}
          </Button>
        )}
      </div>

      {/* An open meeting from another day is the trap. Everything recorded goes
          onto it, dated to it, against the roster as it stood then. */}
      {openMeeting && openMeeting.held_on !== todayLocal() && (
        <p className="t-meta" style={{ marginTop: 8 }}>
          {t("wlt.staleOpenMeeting", { date: openMeeting.held_on })}
        </p>
      )}

      {loading && meetings.length === 0 && <p className="t-meta">{t("common.loading")}</p>}

      {!loading && meetings.length === 0 && (
        <>
          <p style={{ marginTop: 8 }}>{t("wlt.noMeetings")}</p>
          <p className="t-meta">{t("wlt.noMeetingsBody")}</p>
        </>
      )}

      {!compact && meetings.length > 0 && (
        <>
          <FundTrend meetings={meetings} />
          <div className="pill-row" role="group" aria-label={t("wlt.meetingFilterLabel")} style={{ margin: "12px 0" }}>
            {[
              { value: "", label: t("filters.all") },
              { value: "CLOSED", label: t("wlt.meetingClosed") },
              { value: "OPEN", label: t("wlt.meetingOpen") },
            ].map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                className="pill-filter"
                data-active={filter.value === status ? "true" : undefined}
                onClick={() => setStatus(filter.value)}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </>
      )}

      {meetings.length > 0 && (
        <>
        <table className="roster-table">
          <tbody>
            {meetings.map((meeting) => (
              <tr
                key={meeting.id}
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/wlt/groups/${group.id}/meetings/${meeting.id}`)}
              >
                <td style={{ fontWeight: 600 }}>{t("wlt.meetingNo", { no: meeting.meeting_no })}</td>
                <td className="t-meta">{t("wlt.meetingHeld", { date: meeting.held_on })}</td>
                <td className="tabular">
                  {meeting.counted_cash_etb !== null ? `${meeting.counted_cash_etb} ETB` : "—"}
                </td>
                <td style={{ textAlign: "right" }}>
                  <span className="officer-tag">
                    {meeting.status === "OPEN" ? t("wlt.meetingOpen") : t("wlt.meetingClosed")}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {compact && total > meetings.length && (
          <div style={{ marginTop: 8 }}>
            <Button size="sm" onClick={() => navigate(`/wlt/groups/${group.id}/meetings`)}>
              {t("wlt.seeAllMeetings")}
            </Button>
          </div>
        )}
        {!compact && !showAll && total > meetings.length && (
          <div style={{ marginTop: 8 }}>
            <Button size="sm" onClick={() => setShowAll(true)}>
              {t("wlt.showAllMeetings", { count: total })}
            </Button>
          </div>
        )}
        </>
      )}
    </Card>
  );
}
