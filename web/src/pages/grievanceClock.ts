import type { Grievance } from "../api/types";
import type { StringKey } from "../i18n/strings";

/**
 * How a deadline reads on screen.
 *
 * The queue used to print an Age that counted days since the record was created
 * and kept counting after it was resolved, so a concluded row read "30 day(s)
 * open" and every live case looked equally fine until somebody read all of
 * them. Time remaining answers the question the queue is opened with; age
 * answers one nobody asked.
 *
 * Pure, and tested here rather than through the screen — the `timelineLayout.ts`
 * rule. What is worth pinning is which sentence each state produces and how the
 * queue sorts, not what the pixels do.
 */

export type ClockState = Grievance["standing"]["state"];

export interface ClockLabel {
  key: StringKey;
  /** Absolute working days, for the string's `{days}` placeholder. */
  days: number;
  /** Terracotta only for genuine failure — a late answer to a complaint is one. */
  tone: "late" | "due" | "calm";
}

export function clockLabel(standing: Grievance["standing"]): ClockLabel {
  const days = Math.abs(standing.days ?? 0);
  switch (standing.state) {
    case "late":
      return { key: "grievances.clockLate", days, tone: "late" };
    case "due":
      // Zero is "due today", not "due in 0 days". The screen would otherwise
      // say the one thing nobody says out loud.
      return { key: days === 0 ? "grievances.clockToday" : "grievances.clockDue", days, tone: "due" };
    case "closed":
      return { key: "grievances.clockClosed", days, tone: "calm" };
    case "unscheduled":
      return { key: "grievances.clockNone", days: 0, tone: "calm" };
    default:
      return { key: "grievances.clockDue", days, tone: "calm" };
  }
}

/**
 * Queue order: what needs somebody today, first.
 *
 * Late before due before everything else, and inside each band the closest
 * deadline first. Sorting by date of receipt — what the screen did — buries a
 * case four days late under three that arrived this morning.
 *
 * Concluded cases sink whatever their dates, because a queue is a list of work
 * and they are not work.
 */
const BAND: Record<ClockState, number> = {
  late: 0,
  due: 1,
  on_time: 2,
  unscheduled: 3,
  closed: 4,
};

export function byUrgency(left: Grievance, right: Grievance): number {
  const band = BAND[left.standing.state] - BAND[right.standing.state];
  if (band !== 0) return band;
  // Within a band, the nearer deadline first. `days` is signed, so the most
  // overdue sorts to the top of the late band without a second comparator.
  return (left.standing.days ?? 0) - (right.standing.days ?? 0);
}
