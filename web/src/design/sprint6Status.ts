import type { BusinessPlanStatus, GrievanceStatus, MilestoneStatusCode } from "../api/types";
import type { StatusTone } from "./status";

/**
 * Status presentation for the Sprint 6 entities.
 *
 * The same rule as everywhere else — colour plus label plus a geometric mark —
 * and two judgements worth writing down:
 *
 * - **`REVISION_REQUESTED` is gold, not red.** Most first business plans come
 *   back for revision. Rendering it as a failure would teach an officer that her
 *   normal week is going badly.
 * - **`CLOSED` (unresolved) is not `RESOLVED`.** They are the two ways a
 *   grievance ends and §4.10 keeps them apart; showing both in green would make
 *   a channel that closes everything unanswered look like one that works.
 */

export const PLAN_TONE: Record<BusinessPlanStatus, StatusTone> = {
  NOT_STARTED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "○" },
  DRAFTED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "◐" },
  UNDER_REVIEW: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  REVISION_REQUESTED: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "↩" },
  APPROVED: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "✓" },
  REJECTED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "✕" },
};

/**
 * Milestone tones carry an `ink` as well as a chip `fg`.
 *
 * The milestone list draws its mark as a bare glyph on the card ground rather
 * than inside a chip — a plan with six milestones would otherwise be six chips
 * in a column. `fg` is the chip's text colour and for `ACHIEVED` that is white,
 * which is invisible on paper; `ink` is the same status in a colour that reads
 * on the card. Using `fg` for the glyph is exactly how a "never colour alone"
 * status loses its mark and becomes colour alone.
 */
export interface MilestoneTone extends StatusTone {
  ink: string;
}

export const MILESTONE_TONE: Record<MilestoneStatusCode, MilestoneTone> = {
  PENDING: {
    fg: "var(--gold-700)",
    bg: "var(--gold-100)",
    bd: "var(--gold-border)",
    ink: "var(--gold-700)",
    mark: "◔",
  },
  ACHIEVED: {
    fg: "#ffffff",
    bg: "var(--green-700)",
    bd: "var(--green-700)",
    ink: "var(--green-700)",
    mark: "✓",
  },
  MISSED: {
    fg: "var(--terra-700)",
    bg: "var(--terra-100)",
    bd: "var(--terra-border)",
    ink: "var(--terra-700)",
    mark: "▲",
  },
  CANCELLED: {
    fg: "var(--ink-600)",
    bg: "var(--fill-muted-2)",
    bd: "var(--closed-border)",
    ink: "var(--ink-600)",
    mark: "■",
  },
};

export const GRIEVANCE_TONE: Record<GrievanceStatus, StatusTone> = {
  OPEN: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  IN_PROGRESS: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  RESOLVED: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "✓" },
  // Ended, not answered. A different fact from resolved, and it must not read
  // like one.
  CLOSED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "■" },
};
