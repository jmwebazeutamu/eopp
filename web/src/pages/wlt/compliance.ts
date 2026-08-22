import type { GateCondition, WltMemberSavingsCompliance } from "../../api/types";

/**
 * Savings-compliance bands, and the summary the follow-up card states in words.
 *
 * **The threshold is not a constant.** `gate.p1.savings_compliance_pct` lives in
 * `PolicyParameter`, is effective-dated and geography-scoped, and currently
 * reads 80 rather than the 90 that appears in some copy. Hard-coding a number
 * here would contradict the module's own rule that thresholds are configuration
 * — and would band members against a bar the group is not actually judged
 * against. So the band reads the threshold off the group's own gate condition,
 * with a fallback only for a group that has no gate at all.
 *
 * Kept apart from the page for the usual reason: this is the part with rules in
 * it, and a test that mounted a card to check a percentage band would be
 * testing antd.
 */

/** Used only when the group has no gate to read a threshold from. */
export const FALLBACK_THRESHOLD = 80;

export type Band = "compliant" | "watch" | "at-risk";

/**
 * Pull the compliance threshold out of the group's readiness conditions.
 *
 * The gate is the authority: a member is "not compliant" against the same bar
 * the group is measured on, so the card and the readiness tile cannot disagree.
 */
export function thresholdFrom(conditions: GateCondition[] | undefined): number {
  const condition = conditions?.find((row) => row.code === "savings_compliance");
  const raw = condition ? Number(condition.threshold) : NaN;
  return Number.isFinite(raw) && raw > 0 ? raw : FALLBACK_THRESHOLD;
}

/**
 * Three bands, not two.
 *
 * "Watch" exists because a member at 78% against an 80% bar and one at 30% call
 * for different conversations, and a single "not compliant" label would send a
 * facilitator to both with the same urgency. The watch floor sits a notch below
 * the threshold rather than at a fixed number, so it moves when the programme
 * moves the bar.
 */
export function bandFor(pct: number | null, threshold: number): Band | null {
  if (pct === null) return null;
  if (pct >= threshold) return "compliant";
  // A tenth below the bar: 72 on an 80 bar, 81 on a 90 bar.
  return pct >= threshold * 0.9 ? "watch" : "at-risk";
}

export function pctOf(member: WltMemberSavingsCompliance): number | null {
  if (member.compliance_pct === null) return null;
  const value = Number(member.compliance_pct);
  return Number.isFinite(value) ? value : null;
}

export interface ComplianceSummary {
  threshold: number;
  /** Current members only — a former member is not somebody to chase. */
  counted: number;
  compliant: number;
  belowThreshold: number;
  atRisk: number;
  /** Members with nothing recorded yet, which is not the same as zero. */
  unmeasured: number;
  /** The lowest performers, worst first, for the follow-up table. */
  lowest: Array<WltMemberSavingsCompliance & { pct: number; band: Band }>;
}

/**
 * What the follow-up card states in words.
 *
 * Sorted ascending on purpose: the whole point of the card is that the members
 * who need chasing are the ones you see, and a roster sorted by name buries
 * them. A member with nothing recorded is counted separately rather than as a
 * zero — "not yet asked" and "asked and saved nothing" are different findings
 * and only one of them is a compliance problem.
 */
export function summarise(
  members: WltMemberSavingsCompliance[],
  threshold: number,
  limit = 4,
): ComplianceSummary {
  const current = members.filter((member) => member.is_current);
  const measured = current
    .map((member) => ({ member, pct: pctOf(member) }))
    .filter((row): row is { member: WltMemberSavingsCompliance; pct: number } => row.pct !== null);

  const ranked = measured
    .map(({ member, pct }) => ({ ...member, pct, band: bandFor(pct, threshold) as Band }))
    .sort((a, b) => a.pct - b.pct);

  return {
    threshold,
    counted: measured.length,
    compliant: ranked.filter((row) => row.band === "compliant").length,
    belowThreshold: ranked.filter((row) => row.band !== "compliant").length,
    atRisk: ranked.filter((row) => row.band === "at-risk").length,
    unmeasured: current.length - measured.length,
    lowest: ranked.filter((row) => row.band !== "compliant").slice(0, limit),
  };
}

/** Colour and label for a band. Never colour alone — the label always travels. */
export const BAND_STYLE: Record<Band, { label: string; fg: string; fill: string }> = {
  compliant: { label: "Compliant", fg: "var(--green-ink)", fill: "var(--green-500)" },
  watch: { label: "Watch", fg: "var(--gold-700)", fill: "var(--gold-500)" },
  "at-risk": { label: "At risk", fg: "var(--terra-700)", fill: "var(--terra-500)" },
};
