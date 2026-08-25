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
  // Nobody has told the complainant anything yet, which is the state most
  // likely to be sat in and the one nothing used to name. Gold: somebody has
  // to act, and soon.
  RECEIVED: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  ACKNOWLEDGED: { fg: "var(--blue-700)", bg: "var(--blue-100)", bd: "var(--blue-100)", mark: "◇" },
  UNDER_REVIEW: { fg: "var(--teal-700)", bg: "var(--teal-100)", bd: "var(--teal-100)", mark: "▶" },
  // Paused, and the clock with it. Slate rather than gold: the programme is not
  // late, it is waiting on somebody else, and colouring it as overdue would
  // teach people not to pause.
  AWAITING_COMPLAINANT: { fg: "var(--slate-700)", bg: "var(--slate-100)", bd: "var(--slate-100)", mark: "⏸" },
  // Decided is not finished. Green would say it was.
  DECIDED: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◑" },
  CLOSED: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "✓" },
  // Terracotta, not red: an appeal is the mechanism working, not a failure.
  APPEALED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "↑" },
  REFERRED_OUT: { fg: "var(--ink-600)", bg: "var(--fill-muted)", bd: "var(--closed-border)", mark: "→" },
};
