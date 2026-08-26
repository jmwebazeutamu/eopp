import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { FacilitatorCard, FacilitatorHome } from "../../api/types";
import { CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import WltTierTabs from "./WltTierTabs";

/**
 * Tier 1 of `docs/dashboard_handoff_wlt` — the facilitator's home screen.
 *
 * Six queue cards, and one rule shapes all of them: **every count is a list**.
 * The handoff deletes any figure that cannot be tapped to produce the named
 * groups, meetings or members behind it, so nothing here renders a bare number
 * with nowhere to go.
 *
 * One request, per acceptance criterion 1. Six round trips on a 3G connection
 * in a woreda office is the difference between a screen that opens and one that
 * does not.
 *
 * No chart library and no percentages: this tier answers "what do I record, and
 * which group is slipping", and every answer is a row somebody acts on.
 */
export default function FacilitatorHomePage() {
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();

  const [home, setHome] = useState<FacilitatorHome | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<FacilitatorHome>("/wlt/groups/facilitator-home/");
      setHome(response.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.homeLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !home) return <div className="page t-meta">{t("common.loading")}</div>;
  if (!home) return null;

  const card = (id: FacilitatorCard["id"]) => home.cards.find((entry) => entry.id === id);

  return (
    <div className="page stack">
      <div>
        <h1 className="group-title">{t("wlt.homeTitle")}</h1>
        <p className="t-meta" style={{ margin: "4px 0 0" }}>
          {t("wlt.homeSubtitle", { count: home.groups_in_scope })}
          {" · "}
          {/* Freshness on the page, always. A screen that does not say how
              stale it is invites the reader to assume it is live — and this one
              is read in places where it will not be. */}
          {home.last_sync_at
            ? t("wlt.lastSync", { when: home.last_sync_at.slice(0, 16).replace("T", " ") })
            : t("wlt.neverSynced")}
        </p>
      </div>

      {/* The tab strip belongs here too, and its absence made this tier a dead
          end: `/wlt/dashboard` lands an administrator on My work, and with no
          tabs on the page there was no way from here to the woreda, programme
          or results views at all. Renders nothing for a facilitator, who has
          only this one. */}
      <WltTierTabs />

      <div className="record-overview">
        <div className="stack">
          <QueueCard card={card("FC-1")} title={t("wlt.fc1")}>
            {(row) => (
              <Row
                key={String(row.meeting)}
                onOpen={() => navigate(`/wlt/groups/${row.group}/meetings/${row.meeting}`)}
                title={String(row.group_name)}
                meta={String(row.scheduled_for)}
                right={
                  Number(row.days_late) > 0
                    ? { text: t("wlt.daysLate", { days: Number(row.days_late) }), tone: "late" }
                    : { text: t("wlt.dueToday"), tone: "due" }
                }
                flag={row.unsynced ? t("wlt.unsynced") : undefined}
              />
            )}
          </QueueCard>

          <QueueCard card={card("FC-3")} title={t("wlt.fc3")}>
            {(block) => (
              <div key={String(block.class)} style={{ marginBottom: 12 }}>
                {/* Two labelled blocks, never one "overdue" count. One is a
                    conversation at the next meeting; the other is a PAR30 event
                    that blocks a gate. */}
                <CapsLabel>
                  {block.class === "DEFAULT"
                    ? t("wlt.default", { days: Number(block.threshold_days) })
                    : t("wlt.delinquent", { days: Number(block.threshold_days) })}
                </CapsLabel>
                {(block.loans as Record<string, unknown>[]).length === 0 ? (
                  <p className="t-meta" style={{ margin: "4px 0 0" }}>{t("wlt.nothingHere")}</p>
                ) : (
                  (block.loans as Record<string, unknown>[]).map((loan) => (
                    <Row
                      key={String(loan.loan)}
                      onOpen={() => navigate(`/wlt/groups/${loan.group}/loans`)}
                      title={String(loan.borrower)}
                      meta={`${loan.group_name} · ${loan.outstanding_etb} ETB`}
                      right={{
                        text: t("wlt.daysPastDue", { days: Number(loan.days_past_due) }),
                        tone: block.class === "DEFAULT" ? "late" : "due",
                      }}
                    />
                  ))
                )}
              </div>
            )}
          </QueueCard>

          <QueueCard card={card("FC-4")} title={t("wlt.fc4")}>
            {(row) => (
              <Row
                key={String(row.flag)}
                onOpen={() => navigate(`/wlt/groups/${row.group}`)}
                title={String(row.group_name)}
                // The reason in words with the value that raised it. Six codes
                // exist and they are not collapsed into a count: "no treasurer"
                // and "attendance 54%" are different problems.
                meta={reasonWithValue(String(row.reason), row.detail as Record<string, unknown>)}
                // At risk is a warning, not a demotion. Gold, never red.
                right={{ text: t("wlt.daysOpen", { days: Number(row.days_open) }), tone: "due" }}
              />
            )}
          </QueueCard>
        </div>

        <div className="stack">
          <QueueCard card={card("FC-5")} title={t("wlt.fc5")}>
            {(row) => (
              <Row
                key={String(row.group)}
                onOpen={() => navigate(`/wlt/groups/${row.group}`)}
                title={String(row.group_name)}
                meta={String(row.status)}
                right={{
                  text: row.expired
                    ? t("wlt.expired")
                    : t("wlt.daysRemaining", { days: Number(row.days_remaining) }),
                  tone: row.expired ? "late" : row.expiring_soon ? "due" : "calm",
                }}
              />
            )}
          </QueueCard>

          <QueueCard card={card("FC-6")} title={t("wlt.fc6")}>
            {(row) => (
              <Row
                key={String(row.conflict)}
                onOpen={() => navigate(`/wlt/groups/${row.group}`)}
                title={String(row.group_name)}
                meta={`${row.entity} · ${row.natural_key}`}
                right={{ text: String(row.device_id || "—"), tone: "calm" }}
              />
            )}
          </QueueCard>

          <QueueCard card={card("FC-2")} title={t("wlt.fc2")} />
        </div>
      </div>
    </div>
  );
}

/**
 * One card: a heading with its count, then the rows behind it.
 *
 * **`available: false` is not zero.** A zero is a finding — every till
 * balanced, nothing overdue — and an unavailable card is an absence of
 * evidence. Rendering them alike is the lie the youth dashboard's `Maybe<T>`
 * exists to prevent, and FC-2 is exactly that case here.
 */
function QueueCard({
  card,
  title,
  children,
}: {
  card?: FacilitatorCard;
  title: string;
  children?: (row: Record<string, unknown>) => React.ReactNode;
}) {
  const { t } = useLang();
  if (!card) return null;

  return (
    <Card>
      <div className="chip-row">
        <CapsLabel>{title}</CapsLabel>
        {card.available && <strong className="tabular">{card.total}</strong>}
      </div>

      {!card.available ? (
        <p className="t-meta" style={{ margin: "8px 0 0" }}>
          <strong>{t("wlt.notAvailable")}</strong> — {card.note}
        </p>
      ) : card.total === 0 && !children ? (
        <p className="t-meta" style={{ margin: "8px 0 0" }}>{t("wlt.nothingHere")}</p>
      ) : (
        <>
          <div style={{ marginTop: 8 }}>
            {card.rows.length === 0 ? (
              <p className="t-meta" style={{ margin: 0 }}>{t("wlt.nothingHere")}</p>
            ) : (
              card.rows.map((row) => children?.(row))
            )}
          </div>
          {card.note && (
            <p className="t-meta" style={{ margin: "10px 0 0" }}>{card.note}</p>
          )}
        </>
      )}
    </Card>
  );
}

/** A row that is also the way into the work behind it. */
function Row({
  title,
  meta,
  right,
  flag,
  onOpen,
}: {
  title: string;
  meta: string;
  right: { text: string; tone: "late" | "due" | "calm" };
  flag?: string;
  onOpen: () => void;
}) {
  return (
    <button type="button" className="queue-row" onClick={onOpen}>
      <span style={{ minWidth: 0 }}>
        <span className="t-body-strong" style={{ display: "block" }}>{title}</span>
        <span className="t-meta" style={{ display: "block" }}>{meta}</span>
        {flag && <span className="t-meta" style={{ display: "block", color: "var(--gold-700)" }}>{flag}</span>}
      </span>
      <span className="due-cell" data-tone={right.tone}>{right.text}</span>
    </button>
  );
}

/**
 * "Attendance 54% (floor 60%)" rather than "Attendance below floor".
 *
 * The actual value beside the threshold is most of this module's value — a
 * facilitator who reads the number knows what to do next week, and one who
 * reads a condition name does not.
 */
function reasonWithValue(reason: string, detail: Record<string, unknown>) {
  const actual = detail?.actual;
  const threshold = detail?.threshold;
  if (actual === undefined) return reason;
  return threshold === undefined ? `${reason} — ${actual}` : `${reason} — ${actual} (need ${threshold})`;
}
