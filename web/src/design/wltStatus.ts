import type {
  JourneyStageState,
  LinkageStatus,
  WltGroupStatus,
  WltPhase,
  WltVerificationStatus,
} from "../api/types";
import type { StatusTone } from "./status";

/**
 * Status presentation for the WLT group module.
 *
 * Same rule as the youth side and for the same reasons: **never colour alone**.
 * Every status is a colour, a label and a geometric mark, so it survives a
 * monochrome screen, a colour-blind reader and a cheap LCD at half brightness
 * in sunlight — which is the condition most of these screens will be read in.
 *
 * Two constraints carried over from the handoff's palette rules:
 *
 * - **Red is genuine failure only.** A blocked linkage is not a failure — it is
 *   a subject that has not reached a threshold yet, and most of them will reach
 *   it — so `BLOCKED` takes gold, the waiting tone. `DEFAULTED` takes red,
 *   because money has been lost.
 * - **Gold is fill only, never behind text.** Every gold row here sets ink on a
 *   pale gold ground, never white on `--gold-500`.
 */

export const WLT_GROUP_TONE: Record<WltGroupStatus, StatusTone> = {
  DRAFT: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "○" },
  CONSTITUTED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "◐" },
  ACTIVE: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  AT_RISK: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
  DORMANT: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  SPLIT: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "⋔" },
  MERGED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "⋈" },
  DISSOLVED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "■" },
  ABANDONED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "□" },
};

/**
 * Phase is maturity, not health, so it does not take a status colour at all —
 * a P1 group is not "worse" than a P3 one, it is younger. It renders as a
 * neutral chip with the phase number as its own mark.
 */
export const PHASE_LABEL: Record<Exclude<WltPhase, "">, string> = {
  P1: "Phase 1",
  P2: "Phase 2",
  P3: "Phase 3",
  P4: "Phase 4",
};

export const LINKAGE_TONE: Record<LinkageStatus, StatusTone> = {
  PROPOSED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "○" },
  SCREENED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "◐" },
  // Gold, not red. A blocked linkage is a subject that has not got there yet.
  BLOCKED: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  PENDING_APPROVAL: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  RETURNED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "↩" },
  APPROVED: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "◑" },
  REJECTED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "✕" },
  LAPSED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "□" },
  ACTIVE: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "●" },
  DISTRESSED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
  // Red, because money has been lost.
  DEFAULTED: { fg: "var(--red-700)", bg: "var(--red-100)", bd: "var(--red-border)", mark: "✕" },
  CLOSED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "■" },
};

/** Met, unmet, or not measurable yet — three states, three marks. */
export const CONDITION_TONE = {
  met: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "✓" },
  unmet: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  unmeasurable: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "—" },
} satisfies Record<string, StatusTone>;

/**
 * How a woman entered the register, and whether she has been verified.
 *
 * The route is not a status and takes no colour — "imported" is not better than
 * "added by a facilitator", it is a different provenance, and colouring it
 * would read as a judgement on the facilitator. Only verification is a state.
 */
export const VERIFICATION_TONE: Record<WltVerificationStatus, StatusTone> = {
  VERIFIED: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  // Gold, not red. Pending is the exception route working as designed — she is
  // waiting for a woreda officer, not failing anything.
  PENDING: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  // Terracotta rather than red: a refused registration is a decision about
  // eligibility, not money lost or a safeguarding failure.
  REJECTED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "✕" },
};

/**
 * The four states a journey stage can be in.
 *
 * `waiting` is distinct from `blocked` on purpose and shares gold with every
 * other "somebody has to act" tone in the module: a facilitator reading it
 * should recognise it as the same kind of thing as an overdue confirmation,
 * not as a fault in the record.
 */
export const STAGE_TONE = {
  done: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "✓" },
  ready: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "→" },
  waiting: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  blocked: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
} satisfies Record<JourneyStageState, StatusTone>;
