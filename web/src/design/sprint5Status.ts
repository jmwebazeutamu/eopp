import type { RetentionStatusCode, TrainingCompletionStatus } from "../api/types";
import type { StatusTone } from "./status";

/**
 * Status presentation for Training Enrolment (§4.5) and Placement (§4.7).
 *
 * Same rule as every other status on the platform: **never colour alone**.
 * Colour, label and a geometric mark, so it survives a monochrome screen, a
 * colour-blind reader and a cheap LCD at half brightness.
 *
 * Two choices worth stating, because both could reasonably have gone the other
 * way:
 *
 * - **A failed assessment is not red.** She attended to the end; the course or
 *   the assessment did not work for her. Red is reserved for genuine failure,
 *   and terracotta — the "stalled" tone — is what this is: something that needs
 *   attention and is not a catastrophe.
 * - **`UNREACHABLE` is grey, not red.** A youth nobody could reach is not a
 *   youth who left. Rendering it as a loss on the screen would teach the
 *   opposite of what the retention figure carefully avoids saying.
 */

export const TRAINING_TONE: Record<TrainingCompletionStatus, StatusTone> = {
  ENROLLED: { fg: "var(--green-ink)", bg: "var(--green-100)", bd: "var(--green-border)", mark: "●" },
  COMPLETED: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "✓" },
  DROPPED_OUT: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
  FAILED_ASSESSMENT: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "◑" },
};

export const RETENTION_TONE: Record<RetentionStatusCode, StatusTone> = {
  // Gold carries waiting. A check that has not been made is not a bad outcome.
  PENDING: { fg: "var(--gold-700)", bg: "var(--gold-100)", bd: "var(--gold-border)", mark: "◔" },
  RETAINED: { fg: "#ffffff", bg: "var(--green-700)", bd: "var(--green-700)", mark: "✓" },
  EXITED: { fg: "var(--terra-700)", bg: "var(--terra-100)", bd: "var(--terra-border)", mark: "▲" },
  UNREACHABLE: { fg: "var(--ink-600)", bg: "var(--fill-muted-2)", bd: "var(--closed-border)", mark: "?" },
};

/**
 * An exit that is a step up reads differently from one that is not — OQ-5's
 * whole purpose. Only the reasons that carry a direction are listed; everything
 * else renders neutral, because "contract ended" is neither.
 */
export const EXIT_DIRECTION: Record<string, "up" | "down"> = {
  BETTER_JOB: "up",
  DISMISSED: "down",
  REDUNDANT: "down",
};
