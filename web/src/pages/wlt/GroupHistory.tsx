import { App } from "antd";
import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../../api/client";
import type { WltGroup, WltHistoryEvent } from "../../api/types";
import { Button, CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The group's audit trail.
 *
 * The record had none, and the question it answers is a real one: "why did
 * three members leave on 20 August". Everything here already existed — phase
 * decisions, linkage status changes, dated memberships and office terms, closed
 * meetings — it just had nowhere to be read.
 *
 * Grouped by day rather than listed flat, because that is how the question is
 * asked. Three exits on one date read as one event with a cause; the same three
 * spread down a flat list read as three unrelated departures.
 */

const PAGE = 40;

/** One dot colour per family. Never the only signal — every row is also
 *  labelled with its type. */
const DOT: Record<WltHistoryEvent["type"], string> = {
  MEETING: "var(--green-500)",
  MEMBERSHIP: "var(--blue-700)",
  LINKAGE: "var(--teal-700)",
  PHASE: "var(--gold-500)",
};

const FILTERS: Array<{ value: string; key: string }> = [
  { value: "", key: "wlt.historyAll" },
  { value: "PHASE", key: "wlt.historyPhase" },
  { value: "MEMBERSHIP", key: "wlt.historyMembership" },
  { value: "MEETING", key: "wlt.historyMeetings" },
  { value: "LINKAGE", key: "wlt.historyLinkages" },
];

export default function GroupHistory({ group }: { group: WltGroup }) {
  const { message } = App.useApp();
  const { t } = useLang();

  const [events, setEvents] = useState<WltHistoryEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [shown, setShown] = useState(PAGE);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<{ total: number; events: WltHistoryEvent[] }>(
        `/wlt/groups/${group.id}/history/`,
        { params: { limit: shown, type: filter || undefined } },
      );
      setEvents(response.data.events);
      setTotal(response.data.total);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.historyLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [group.id, shown, filter, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // Grouped in render order, so a day's events stay in the order the server
  // sorted them rather than being regrouped into a different sequence.
  const days: Array<{ date: string; rows: WltHistoryEvent[] }> = [];
  for (const event of events) {
    const last = days[days.length - 1];
    if (last && last.date === event.at) last.rows.push(event);
    else days.push({ date: event.at, rows: [event] });
  }

  return (
    <Card className="card--tight">
      <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
        <CapsLabel>{t("wlt.historyTitle")}</CapsLabel>
        <span className="t-meta">{t("wlt.historyCount", { count: total })}</span>
      </div>

      <div className="pill-row" role="group" aria-label={t("wlt.historyFilterLabel")} style={{ margin: "10px 0" }}>
        {FILTERS.map((entry) => (
          <button
            key={entry.value || "all"}
            type="button"
            className="pill-filter"
            data-active={entry.value === filter ? "true" : undefined}
            onClick={() => {
              setFilter(entry.value);
              // Back to the first page: keeping the offset across a filter
              // change lands the reader in the middle of a different list.
              setShown(PAGE);
            }}
          >
            {t(entry.key as never)}
          </button>
        ))}
      </div>

      {loading && events.length === 0 && <p className="t-meta">{t("common.loading")}</p>}

      {!loading && events.length === 0 && <p className="t-meta">{t("wlt.historyEmpty")}</p>}

      {days.map((day) => (
        <div key={day.date} className="history-day">
          <div className="history-day__date tabular">{day.date}</div>
          <ul className="history-day__events">
            {day.rows.map((event, index) => (
              <li key={`${event.at}-${event.title}-${index}`} className="history-event">
                <span className="history-event__dot" style={{ background: DOT[event.type] }} aria-hidden />
                <div style={{ minWidth: 0 }}>
                  <div>{event.title}</div>
                  <div className="t-meta">
                    <span className="officer-tag">{t(`wlt.history${titleCase(event.type)}` as never)}</span>
                    {event.detail && ` ${event.detail}`}
                    {event.actor && ` · ${event.actor}`}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}

      {total > events.length && (
        <Button size="sm" onClick={() => setShown(shown + PAGE)}>
          {t("wlt.historyMore")}
        </Button>
      )}
    </Card>
  );
}

/** `MEMBERSHIP` -> `Membership`, so one string key serves both filter and tag. */
function titleCase(type: string): string {
  return type.charAt(0) + type.slice(1).toLowerCase();
}
