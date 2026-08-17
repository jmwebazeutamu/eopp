import type { CaseStatus, ReferralStatusCode } from "../api/types";

/**
 * Status presentation — the handoff's status system.
 *
 * "Never colour alone": every status is a colour, a label *and* a geometric
 * mark, so it survives a monochrome screen, a colour-blind reader and a cheap
 * LCD at half brightness. The marks are text glyphs rather than icons, which is
 * what lets them sit inside a chip, a timeline bar and a slot card without
 * three different assets.
 *
 * Values are the handoff's, keyed by the API's codes rather than by the
 * prototype's English labels so a display-string change cannot silently drop
 * the styling.
 */

export interface StatusTone {
  /** Chip text colour. */
  fg: string;
  /** Chip background. */
  bg: string;
  /** Chip border. */
  bd: string;
  mark: string;
}

export interface ReferralTone extends StatusTone {
  /** Timeline bar fill — solid, and darker than the chip background. */
  bar: string;
  /** Ink for the label rendered under a timeline lane. */
  ink: string;
}

export const CASE_TONE: Record<CaseStatus, StatusTone> = {
  ACTIVE: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  REFERRAL_PENDING: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  STALLED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
  PLACED: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "✓" },
  // §4.2 calls this Exited; the handoff's chip reads Closed. The API's own
  // display string wins at render time — only the tone is taken from here.
  EXITED: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "■" },
};

export const REFERRAL_TONE: Record<ReferralStatusCode, ReferralTone> = {
  PENDING_CONFIRMATION: {
    fg: "var(--gold-700)",
    bg: "var(--gold-100)",
    bd: "var(--gold-border)",
    bar: "var(--gold-500)",
    ink: "var(--gold-700)",
    mark: "◔",
  },
  ACTIVE: {
    fg: "var(--green-ink)",
    bg: "var(--green-100)",
    bd: "var(--green-border)",
    bar: "var(--green-500)",
    ink: "var(--green-ink)",
    mark: "●",
  },
  COMPLETED: {
    fg: "#ffffff",
    bg: "var(--green-700)",
    bd: "var(--green-700)",
    bar: "var(--green-700)",
    ink: "var(--green-700)",
    mark: "✓",
  },
  FAILED: {
    fg: "var(--red-700)",
    bg: "var(--red-100)",
    bd: "var(--red-border)",
    bar: "var(--red-500)",
    ink: "var(--red-700)",
    mark: "✕",
  },
  REPLACED: {
    fg: "var(--terra-700)",
    bg: "var(--terra-100)",
    bd: "var(--terra-border)",
    bar: "var(--terra-500)",
    ink: "var(--terra-700)",
    mark: "↻",
  },
  CANCELLED: {
    fg: "var(--ink-600)",
    bg: "var(--fill-muted-2)",
    bd: "var(--closed-border)",
    bar: "var(--cancelled-bar)",
    ink: "var(--ink-600)",
    mark: "⊘",
  },
};

/**
 * Spreadsheet-import row outcomes.
 *
 * Only `error` blocks the import, so only `error` is red — a row already on file
 * is a normal result of re-sending a register, not a failure, and colouring it
 * as one would teach staff to ignore the colour that matters. Gold is absent
 * here because nothing in an import is waiting on anyone.
 */
export type ImportOutcome = "new" | "duplicate" | "error";

export const IMPORT_TONE: Record<ImportOutcome, StatusTone> = {
  new: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  duplicate: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "⊘" },
  error: { fg: "var(--red-700)", bg: "var(--red-100)", bd: "var(--red-border)", mark: "✕" },
};

/** Waiting-time badges escalate in tone rather than only in wording. */
export type WaitLevel = "ok" | "warn" | "over";

export const WAIT_TONE: Record<WaitLevel, { fg: string; bg: string }> = {
  ok: { fg: "var(--ink-600)", bg: "var(--fill-muted)" },
  warn: { fg: "var(--gold-700)", bg: "var(--gold-100)" },
  over: { fg: "var(--red-700)", bg: "var(--red-100)" },
};

/**
 * §11 sets the confirmation-overdue threshold at 7 days, a placeholder pending
 * sign-off. Warn at two-thirds of it so a case manager sees a referral going
 * quiet before it is formally late.
 */
export const CONFIRMATION_OVERDUE_DAYS = 7;

export function waitLevel(days: number, threshold = CONFIRMATION_OVERDUE_DAYS): WaitLevel {
  if (days >= threshold) return "over";
  if (days >= Math.ceil((threshold * 2) / 3)) return "warn";
  return "ok";
}

/** Alert tones, per the handoff's counter cards. */
export const ALERT_TONE: Record<string, { fg: string; bg: string }> = {
  STALL: { fg: "var(--terra-700)", bg: "var(--terra-100)" },
  REFERRAL_CONFIRMATION_OVERDUE: { fg: "var(--gold-700)", bg: "var(--gold-100)" },
  FOLLOW_UP_DUE: { fg: "var(--green-700)", bg: "var(--green-100)" },
  ONWARD_REFERRAL_PROMPT: { fg: "var(--green-700)", bg: "var(--green-100)" },
  REPLACEMENT_REFERRAL_PROMPT: { fg: "var(--terra-700)", bg: "var(--terra-100)" },
  RETENTION_CHECK_DUE: { fg: "var(--gold-700)", bg: "var(--gold-100)" },
};

/** The one-line reason under each alert counter — why this alert exists. */
export const ALERT_REASON: Record<string, string> = {
  STALL: "No activity for 30 days",
  REFERRAL_CONFIRMATION_OVERDUE: "Partner silent past 7 days",
  FOLLOW_UP_DUE: "Scheduled check-in reached",
  ONWARD_REFERRAL_PROMPT: "Referral completed, slot free",
  REPLACEMENT_REFERRAL_PROMPT: "Referral failed, youth unplaced",
  RETENTION_CHECK_DUE: "6 months since placement",
};
