import { App } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, ProgrammeRules, Referral, ReferralPrompts } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import ReferralActionModal, { ACTION_LABELS, actionsFor, type ReferralAction } from "../components/ReferralActions";
import ListPage from "../components/ListPage";
import { scopeParam, useScope } from "../components/shell/ScopeContext";
import { referralRef } from "../components/ReferralPanel";
import { Button, CapsLabel, Card, CountBadge, ReferralStatusChip, WaitBadge } from "../components/ui";
import { REFERRAL_TONE, waitLevel } from "../design/status";
import { useLang } from "../i18n/LanguageContext";

/**
 * The referrals queue — the handoff's decision inbox.
 *
 * Three groups in a fixed order: what needs a decision now, what is waiting on
 * a partner, and what is running. The order is the point — this screen exists
 * to be cleared in batches, so the rows that can be acted on come first and
 * each carries its actions inline rather than behind a row click.
 *
 * The waiting-time badge escalates in tone as well as wording, because a queue
 * of thirty rows is scanned, not read.
 */

/** Counters take their colour from the status they filter to. */
/** The chip palette, taken whole — see the note on CASE_COUNTER_TONES. */
const REFERRAL_COUNTER_TONES = REFERRAL_TONE;

interface Group {
  key: string;
  titleKey: "queue.needsDecision" | "queue.awaiting" | "queue.active";
  rows: Referral[];
}

export default function ReferralsPage() {
  const scope = useScope();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [pending, setPending] = useState<Referral[]>([]);
  const [active, setActive] = useState<Referral[]>([]);
  const [prompts, setPrompts] = useState<ReferralPrompts>({ onward: [], replacement: [] });
  const [rules, setRules] = useState<ProgrammeRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ReferralAction | null>(null);

  const canWrite = user?.access.referral_write ?? false;
  // §7 scopes case records separately from referrals: a LINKED-scope role sees
  // referrals but no case rows, so a link to the case screen would 404.
  const canOpenCases = user ? !["NONE", "LINKED"].includes(user.access.case_scope) : false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The counters filter by status, so a chosen status narrows both lists
      // to it and empties the other — which is what "show me only the failed
      // ones" should do to a queue grouped by urgency.
      // `status__in` is what the chip row writes — the parameter the server
      // names on its own counters — and it carries a comma-separated list
      // because the chips multi-select.
      const chosen = (params.get("status__in") ?? "").split(",").filter(Boolean);
      const wants = (status: string) => chosen.length === 0 || chosen.includes(status);
      const search = params.get("q") || undefined;
      const [pendingResponse, activeResponse, promptsResponse, rulesResponse] = await Promise.all([
        wants("PENDING_CONFIRMATION")
          ? api.get<Paginated<Referral>>("/referrals/", {
              params: { status: "PENDING_CONFIRMATION", page_size: 100, search },
            })
          : Promise.resolve({ data: { results: [] as Referral[] } }),
        wants("ACTIVE")
          ? api.get<Paginated<Referral>>("/referrals/", { params: { status: "ACTIVE", page_size: 100, search } })
          : Promise.resolve({ data: { results: [] as Referral[] } }),
        // The prompt conditions are querysets on the server (§6.2); asking for
        // them rather than recomputing "completed with no child" here keeps one
        // definition, the same one the Sprint 4 alert jobs materialise.
        api.get<ReferralPrompts>("/referrals/prompts/"),
        api.get<ProgrammeRules>("/referrals/rules/"),
      ]);
      setPending(pendingResponse.data.results);
      setActive(activeResponse.data.results);
      setPrompts(promptsResponse.data);
      setRules(rulesResponse.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load referrals."));
    } finally {
      setLoading(false);
    }
  }, [params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const overdueDays = rules?.referral_confirmation_overdue_days ?? 7;

  const groups: Group[] = useMemo(() => {
    const promptRows = [...prompts.onward, ...prompts.replacement];
    const promptIds = new Set(promptRows.map((row) => row.id));

    // "Needs a decision" is anything the case manager owns a next move on: a
    // referral past the confirmation threshold, and every open prompt.
    const overdue = pending.filter((row) => daysSince(row.initiated_date) >= overdueDays);
    const overdueIds = new Set(overdue.map((row) => row.id));

    return [
      { key: "decide", titleKey: "queue.needsDecision", rows: [...overdue, ...promptRows] },
      {
        key: "awaiting",
        titleKey: "queue.awaiting",
        rows: pending.filter((row) => !overdueIds.has(row.id)),
      },
      { key: "active", titleKey: "queue.active", rows: active.filter((row) => !promptIds.has(row.id)) },
    ];
  }, [pending, active, prompts, overdueDays]);

  const total = groups.reduce((sum, group) => sum + group.rows.length, 0);

  return (
    <ListPage
      title={t("queue.title")}
      subtitle={t("queue.subtitle", { scope: scope.label })}
      searchPlaceholder={t("queue.search")}
      resource="/referrals"
      chipParams={scopeParam(scope.woreda, "case__woreda")}
      chipTones={REFERRAL_COUNTER_TONES}
      empty={{
        when: !loading && total === 0,
        title: t("empty.referrals"),
        body: t("empty.referralsBody"),
      }}
    >
      {(density) => (
        <>

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {groups
        .filter((group) => group.rows.length > 0)
        .map((group) => (
          <section key={group.key} className="stack" style={{ gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <CapsLabel>{t(group.titleKey)}</CapsLabel>
              <CountBadge>{group.rows.length}</CountBadge>
            </div>

            {/* Laptop: a table, same shape as the caseload. Phone: cards —
                a six-column table on a 360px screen is unreadable. */}
            <div className="only-laptop">
              <Card className="table-card">
                <table className={`table ${density}`}>
                  <thead>
                    <tr>
                      <th scope="col">{t("queue.col.youth")}</th>
                      <th scope="col">{t("queue.col.referral")}</th>
                      <th scope="col">{t("cases.col.woreda")}</th>
                      <th scope="col">{t("cases.col.status")}</th>
                      <th scope="col">{t("queue.col.waiting")}</th>
                      <th scope="col">{t("queue.col.decision")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.rows.map((referral) => {
                      const waiting = daysSince(referral.initiated_date);
                      return (
                        <tr
                          key={referral.id}
                          onClick={canOpenCases ? () => navigate(`/cases/${referral.case}`) : undefined}
                          style={{ cursor: canOpenCases ? "pointer" : "default" }}
                        >
                          <td>
                            {canOpenCases ? (
                              <Link
                                className="row-link"
                                to={`/cases/${referral.case}`}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {referral.youth_name}
                              </Link>
                            ) : (
                              <div style={{ fontSize: 14, fontWeight: 600 }}>{referral.youth_name}</div>
                            )}
                            <div style={{ color: "var(--ink-400)" }}>{referralRef(referral.id)}</div>
                          </td>
                          <td>
                            <div>{referral.referral_category_label}</div>
                            <div style={{ color: "var(--ink-400)" }}>
                              → {referral.receiving_partner_detail.partner_name}
                            </div>
                          </td>
                          <td>{referral.woreda}</td>
                          <td>
                            <ReferralStatusChip status={referral.status} label={referral.status_display} />
                          </td>
                          <td>
                            {referral.status === "PENDING_CONFIRMATION" ? (
                              <WaitBadge level={waitLevel(waiting, overdueDays)}>
                                {t("case.waiting", { days: waiting })}
                              </WaitBadge>
                            ) : (
                              <span style={{ color: "var(--ink-400)" }}>—</span>
                            )}
                          </td>
                          {/* The actions stay on the row: this screen exists to
                              be cleared in batches, and a decision behind a
                              click-through is a decision not taken today. */}
                          <td onClick={(event) => event.stopPropagation()}>
                            <Actions referral={referral} canWrite={canWrite} onAction={setAction} compact />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </Card>
            </div>

            <div className="only-phone">
              {group.rows.map((referral) => {
                const waiting = daysSince(referral.initiated_date);
                return (
                  <Card key={referral.id}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-start" }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          className="t-body-strong"
                          style={{ cursor: canOpenCases ? "pointer" : "default" }}
                          onClick={canOpenCases ? () => navigate(`/cases/${referral.case}`) : undefined}
                        >
                          {referral.youth_name}
                        </div>
                        <div style={{ fontSize: 14 }}>
                          {referral.referral_category_label} → {referral.receiving_partner_detail.partner_name}
                        </div>
                        <div className="t-meta">
                          {referralRef(referral.id)} · {referral.woreda}
                        </div>
                      </div>

                      <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
                        <ReferralStatusChip status={referral.status} label={referral.status_display} />
                        {referral.status === "PENDING_CONFIRMATION" && (
                          <WaitBadge level={waitLevel(waiting, overdueDays)}>
                            {t("case.waiting", { days: waiting })}
                          </WaitBadge>
                        )}
                      </div>
                    </div>

                    <Actions referral={referral} canWrite={canWrite} onAction={setAction} />
                  </Card>
                );
              })}
            </div>
          </section>
        ))}

      <ReferralActionModal
        action={action}
        caseId={action?.referral?.case ?? ""}
        woreda={action?.referral?.woreda ?? ""}
        onClose={() => setAction(null)}
        onDone={() => void load()}
      />
        </>
      )}
    </ListPage>
  );
}

/** The §6.2 moves this row offers, laid out the same way in both breakpoints. */
function Actions({
  referral,
  canWrite,
  onAction,
  compact,
}: {
  referral: Referral;
  canWrite: boolean;
  onAction: (action: ReferralAction) => void;
  compact?: boolean;
}) {
  const kinds = actionsFor(referral, canWrite);
  if (!kinds.length) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: compact ? 0 : 12 }}>
      {kinds.map((kind) => (
        <Button
          key={kind}
          size={compact ? "sm" : "md"}
          style={compact ? undefined : { flex: "1 1 180px" }}
          variant={
            kind === "confirm" ? "primary" : kind === "decline" || kind === "fail" ? "destructive-soft" : "secondary"
          }
          onClick={() => onAction({ kind, referral })}
        >
          {ACTION_LABELS[kind]}
        </Button>
      ))}
    </div>
  );
}

function daysSince(date: string): number {
  return Math.max(0, Math.floor((Date.now() - new Date(date).getTime()) / 86_400_000));
}
