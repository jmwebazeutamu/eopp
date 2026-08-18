import { App } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, errorMessage } from "../api/client";
import type { ProgrammeRules, Referral, ReferralStackNode } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { REFERRAL_TONE, waitLevel } from "../design/status";
import { useLang } from "../i18n/LanguageContext";
import ReferralActionModal, { ACTION_LABELS, actionsFor, type ReferralAction } from "./ReferralActions";
import ReferralStackTimeline from "./referrals/ReferralStackTimeline";
import { Button, CapsLabel, Card, MutedChip, ReferralStatusChip, WaitBadge } from "./ui";

/**
 * The referral stack for one case — spec §6.4, as the design handoff draws it.
 *
 * Three parts: the parallel slots, the timeline, then the stack itself. The
 * §6.3 cap is stated three ways rather than in a paragraph — the slot cards,
 * the "2 of 2 in use" chip, and the Exempt track on the timeline — because it
 * is the rule case managers most often argue with.
 *
 * The stack is not a stored object; the API rebuilds it by query from the
 * parent links every call, so this renders the tree it is given and cannot
 * drift from the data.
 */

interface Props {
  caseId: string;
  woreda: string;
  onChanged: () => void;
}

/** Statuses that are over and done — kept in the stack, but on a muted card. */
const CLOSED_STATUSES = ["FAILED", "REPLACED", "CANCELLED"];

export default function ReferralPanel({ caseId, woreda, onChanged }: Props) {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();

  const [stack, setStack] = useState<ReferralStackNode[]>([]);
  const [rules, setRules] = useState<ProgrammeRules | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ReferralAction | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const canWrite = user?.access.referral_write ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // The cap is a programme rule, so it comes from the server rather than
      // being a constant a deployed client could be wrong about.
      const [stackResponse, rulesResponse] = await Promise.all([
        api.get<ReferralStackNode[]>(`/referrals/stack/${caseId}/`),
        api.get<ProgrammeRules>("/referrals/rules/"),
      ]);
      setStack(stackResponse.data);
      setRules(rulesResponse.data);
    } catch (error) {
      message.error(errorMessage(error, "Could not load referrals."));
    } finally {
      setLoading(false);
    }
  }, [caseId, message]);

  useEffect(() => {
    void load();
  }, [load]);

  const flat = useMemo(() => {
    const out: Referral[] = [];
    const walk = (nodes: ReferralStackNode[]) => {
      nodes.forEach((node) => {
        out.push(node.referral);
        walk(node.children);
      });
    };
    walk(stack);
    return out;
  }, [stack]);

  const limit = rules?.parallel_limit ?? 2;
  const occupying = flat.filter((r) => r.status === "ACTIVE" && r.counts_toward_parallel_cap);
  const exemptActive = flat.filter((r) => r.status === "ACTIVE" && !r.counts_toward_parallel_cap);
  const atCap = occupying.length >= limit;

  function select(referralId: string) {
    setSelectedId(referralId);
    cardRefs.current[referralId]?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  /** One node of the §6.4 stack, with its descendants indented beneath it. */
  function renderNode(node: ReferralStackNode, depth = 0) {
    const referral = node.referral;
    return (
      <div key={referral.id} style={{ marginLeft: depth * 24 }}>
        <ReferralCard
          referral={referral}
          rules={rules}
          canWrite={canWrite}
          selected={selectedId === referral.id}
          onAction={setAction}
          cardRef={(element) => {
            cardRefs.current[referral.id] = element;
          }}
        />
        {node.children.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
            {node.children.map((child) => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  }

  function newReferral() {
    if (atCap) {
      // Visible but blocked, and it explains itself rather than vanishing.
      message.warning(t("case.limitReached"));
      return;
    }
    setAction({ kind: "initiate", referral: null });
  }

  if (loading) return <div className="t-meta">{t("common.loading")}</div>;

  return (
    <div className="stack">
      {/* -- Parallel slots ------------------------------------------------ */}
      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginBottom: 12 }}>
          <CapsLabel>{t("case.slots")}</CapsLabel>
          <span
            className="chip"
            style={{
              color: atCap ? "var(--terra-700)" : "var(--ink-600)",
              background: atCap ? "var(--terra-100)" : "var(--fill-muted)",
              borderColor: atCap ? "var(--terra-border)" : "transparent",
            }}
          >
            {t("case.slotsInUse", { used: occupying.length, limit })}
          </span>
        </div>

        <div className="grid-slots">
          {Array.from({ length: limit }, (_, index) => {
            const referral = occupying[index];
            return (
              <div
                key={index}
                className="card"
                style={{ background: "var(--surface-alt)", cursor: referral ? "pointer" : "default" }}
                onClick={referral ? () => select(referral.id) : undefined}
              >
                <CapsLabel>{t("case.slot", { n: index + 1 })}</CapsLabel>
                {referral ? (
                  <>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
                      <Dot colour={REFERRAL_TONE[referral.status].bar} />
                      <span style={{ fontWeight: 600 }}>{referral.status_display}</span>
                    </div>
                    <div className="t-meta">{referral.referral_category_label}</div>
                    <div className="t-meta">{referral.receiving_partner_detail.partner_name}</div>
                  </>
                ) : (
                  <div style={{ marginTop: 4, color: "var(--ink-400)" }}>{t("case.slotFree")}</div>
                )}
              </div>
            );
          })}

          {/* Dashed, because it is outside the two-slot frame entirely. */}
          <div className="card" style={{ borderStyle: "dashed", background: "transparent" }}>
            <CapsLabel>{t("case.exempt")}</CapsLabel>
            {exemptActive.length ? (
              exemptActive.map((referral) => (
                <div key={referral.id} style={{ marginTop: 4 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Dot colour={REFERRAL_TONE[referral.status].bar} />
                    <span style={{ fontWeight: 600 }}>{referral.status_display}</span>
                  </div>
                  <div className="t-meta">{referral.referral_category_label}</div>
                </div>
              ))
            ) : (
              <div style={{ marginTop: 4, color: "var(--ink-400)" }}>{t("case.slotFree")}</div>
            )}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 12,
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: 12,
          }}
        >
          <span className="t-meta">{t("case.exemptNote")}</span>
          {canWrite && (
            <Button variant="primary" blocked={atCap} onClick={newReferral}>
              + {atCap ? t("case.newReferralBlocked") : t("case.newReferral")}
            </Button>
          )}
        </div>
      </Card>

      {/* -- Timeline ------------------------------------------------------ */}
      {flat.length > 0 && (
        <Card>
          {/* The timeline heads itself: only it knows which year(s) the case spans. */}
          <ReferralStackTimeline referrals={flat} onReferralClick={select} selectedReferralId={selectedId} />
        </Card>
      )}

      {/* -- The stack ----------------------------------------------------- */}
      <div>
        <CapsLabel style={{ marginBottom: 10 }}>{t("case.history")}</CapsLabel>

        {stack.length === 0 ? (
          <Card>
            <div className="t-meta">{t("case.noReferrals")}</div>
          </Card>
        ) : (
          // Rendered as the tree the API returns, not as a flat list: the
          // nesting *is* the stack (§6.4). A referral indented under another is
          // the onward or replacement it produced, and flattening that loses
          // the one thing the stack exists to show.
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {stack.map((node) => renderNode(node))}
          </div>
        )}
      </div>

      <ReferralActionModal
        action={action}
        caseId={caseId}
        woreda={woreda}
        onClose={() => setAction(null)}
        onDone={() => {
          void load();
          onChanged();
        }}
      />
    </div>
  );
}

function Dot({ colour }: { colour: string }) {
  return (
    <span
      aria-hidden
      style={{ width: 8, height: 8, borderRadius: "50%", background: colour, display: "inline-block", flexShrink: 0 }}
    />
  );
}

/**
 * A referral's human reference.
 *
 * §4.6 gives a referral a UUID and no programme-facing reference, but staff
 * quote one down a phone line, so this renders the UUID's leading bytes in the
 * handoff's `RF-` shape. It is a display of the real id, not a second
 * identifier — a genuine sequential reference would need a backend field and a
 * spec decision about its format.
 */
export function referralRef(id: string): string {
  return `RF-${id.replace(/-/g, "").slice(0, 6).toUpperCase()}`;
}

function daysSince(date: string): number {
  const then = new Date(date).getTime();
  return Math.max(0, Math.floor((Date.now() - then) / 86_400_000));
}

function ReferralCard({
  referral,
  rules,
  canWrite,
  selected,
  onAction,
  cardRef,
}: {
  referral: Referral;
  rules: ProgrammeRules | null;
  canWrite: boolean;
  selected: boolean;
  onAction: (action: ReferralAction) => void;
  cardRef: (element: HTMLDivElement | null) => void;
}) {
  const { t } = useLang();
  const kinds = actionsFor(referral, canWrite);
  const closed = CLOSED_STATUSES.includes(referral.status);

  // Only a referral still waiting on the partner has a waiting time worth
  // showing; once it is active or closed the clock is no longer the story.
  const waiting = referral.status === "PENDING_CONFIRMATION" ? daysSince(referral.initiated_date) : null;
  // No client-side default: without the server's threshold there is no
  // honest way to say whether a wait is late.
  const overdueDays = rules?.referral_confirmation_overdue_days;
  const level = waiting === null || overdueDays === undefined ? null : waitLevel(waiting, overdueDays);

  return (
    <div ref={cardRef}>
      {/* Flat border, no accent rail. Depth is carried by the indentation and
          by the trigger label ("Onward", "Replacement") the card already
          shows — a coloured rail was a third encoding of the same fact. */}
      <Card muted={closed} style={selected ? { boxShadow: "0 0 0 2px var(--green-500)" } : undefined}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-start" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <CapsLabel>
              {referral.referral_category_label} · {referralRef(referral.id)}
            </CapsLabel>
            <div className="t-card-title">{referral.receiving_partner_detail.partner_name}</div>
          </div>
          <ReferralStatusChip status={referral.status} label={referral.status_display} />
        </div>

        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginTop: 8 }}>
          <MutedChip style={{ fontSize: 12 }}>
            {referral.counts_toward_parallel_cap ? t("case.usesSlot") : t("case.noSlot")}
          </MutedChip>
          <span className="t-meta">
            {referral.trigger_display} · initiated {referral.initiated_date}
            {referral.confirmed_date && ` · confirmed ${referral.confirmed_date}`}
            {referral.outcome_date && ` · outcome ${referral.outcome_date}`}
            {referral.failure_date && ` · failed ${referral.failure_date}`}
          </span>
          {waiting !== null && level !== null && (
            <WaitBadge level={level}>{t("case.waiting", { days: waiting })}</WaitBadge>
          )}
        </div>

        {(referral.outcome_type_label || referral.failure_reason_label || referral.notes) && (
          <div style={{ marginTop: 8, fontSize: 14 }}>
            {referral.outcome_type_label && <div>Outcome: {referral.outcome_type_label}</div>}
            {referral.failure_reason_label && (
              <div style={{ color: "var(--red-700)" }}>Failed: {referral.failure_reason_label}</div>
            )}
            {referral.notes && <div className="t-meta">{referral.notes}</div>}
          </div>
        )}

        {kinds.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
            {kinds.map((kind) => (
              <Button
                key={kind}
                style={{ flex: "1 1 180px" }}
                variant={
                  kind === "confirm" ? "primary" : kind === "decline" || kind === "fail" ? "destructive-soft" : "secondary"
                }
                onClick={() => onAction({ kind, referral })}
              >
                {ACTION_LABELS[kind]}
              </Button>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
