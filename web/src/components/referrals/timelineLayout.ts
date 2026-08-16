import { timeDay, timeMonth, timeWeek, timeYear, type TimeInterval } from "d3-time";

import type { Referral, ReferralStatusCode } from "../../api/types";

/**
 * Layout arithmetic for the referral stack timeline (spec §6.4).
 *
 * Kept apart from the component and free of any pixel geometry: everything here
 * works in lanes and dates, and the component turns those into coordinates with
 * a d3 time scale. Lane assignment, parallel grouping and dependency arrows are
 * the parts that can be wrong in ways a screenshot will not show, so they are
 * the parts that are unit tested.
 */

/** Statuses where the referral is still running, so its bar has no closing edge yet. */
const OPEN_STATUSES: ReferralStatusCode[] = ["PENDING_CONFIRMATION", "ACTIVE"];

export interface TimelineBar {
  referral: Referral;
  /** 0-based row, top to bottom. */
  lane: number;
  start: Date;
  end: Date;
  /** True when `end` is "now" rather than a recorded outcome — drawn open-ended. */
  isOpenEnded: boolean;
}

export interface ParallelBracket {
  groupId: string;
  firstLane: number;
  lastLane: number;
  referralIds: string[];
}

export interface DependencyArrow {
  /** The referral that produced the other one. */
  fromId: string;
  toId: string;
  kind: "onward" | "replacement";
  fromLane: number;
  toLane: number;
  /** Where the tail leaves the parent bar, and where the head meets the child bar. */
  fromDate: Date;
  toDate: Date;
}

export type TickKind = "day" | "week" | "month" | "quarter" | "year";

export interface TimelineTick {
  date: Date;
  label: string;
}

export interface TimelineLayout {
  bars: TimelineBar[];
  brackets: ParallelBracket[];
  arrows: DependencyArrow[];
  ticks: TimelineTick[];
  tickKind: TickKind;
  /** [earliest initiation, latest close or today] — the time scale's domain. */
  domain: [Date, Date];
  laneCount: number;
}

const MS_PER_DAY = 86_400_000;

/**
 * Parse an API `YYYY-MM-DD` into local midnight.
 *
 * `new Date("2026-03-05")` is parsed as UTC midnight, which in Africa/Addis_Ababa
 * (UTC+3) still renders as the 5th, but west of Greenwich would render as the
 * 4th. Constructing the local date keeps a referral's bar on the day the
 * case manager recorded it, wherever the browser happens to be.
 */
export function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Timestamps (`updated_at`) carry an offset, so they parse unambiguously. */
function parseTimestamp(value: string): Date {
  return new Date(value);
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * Where a referral's bar stops.
 *
 * The spec stamps different fields per terminal status: `transition_to` sets
 * `outcome_date` on Completed and `failure_date` on Failed, and Replaced is only
 * reachable from Failed so it inherits that date. Cancelled records no date at
 * all — §6.2 gives it no System Action — so the bar closes at `updated_at`,
 * which is when the withdrawal was written. Falling back to today instead would
 * draw a referral cancelled months ago as though it were still running.
 */
export function barEnd(referral: Referral, today: Date): { end: Date; isOpenEnded: boolean } {
  if (OPEN_STATUSES.includes(referral.status)) {
    return { end: today, isOpenEnded: true };
  }
  const recorded = referral.outcome_date ?? referral.failure_date;
  if (recorded) {
    return { end: parseDateOnly(recorded), isOpenEnded: false };
  }
  return { end: startOfDay(parseTimestamp(referral.updated_at)), isOpenEnded: false };
}

/** Initiation order, with ties broken on id so the layout is stable across renders. */
function byInitiation(a: Referral, b: Referral): number {
  if (a.initiated_date !== b.initiated_date) return a.initiated_date < b.initiated_date ? -1 : 1;
  return a.id < b.id ? -1 : 1;
}

/**
 * Order referrals into lanes: by initiation date, except that referrals sharing a
 * `parallel_group_id` are kept adjacent.
 *
 * Adjacency is what lets concurrency be shown as a bracket down the left edge
 * rather than as its own colour — the correction this component exists to make
 * to the Concept Note's Figure 4, whose legend mixed status with structure and
 * so could not describe a parallel referral that had also failed.
 */
export function assignLanes(referrals: Referral[]): Referral[] {
  const ordered = [...referrals].sort(byInitiation);
  const placed = new Set<string>();
  const lanes: Referral[] = [];

  ordered.forEach((referral) => {
    if (placed.has(referral.id)) return;
    lanes.push(referral);
    placed.add(referral.id);

    if (!referral.parallel_group_id) return;
    // Pull the rest of the group up next to it, keeping their relative order.
    ordered.forEach((sibling) => {
      if (placed.has(sibling.id)) return;
      if (sibling.parallel_group_id !== referral.parallel_group_id) return;
      lanes.push(sibling);
      placed.add(sibling.id);
    });
  });

  return lanes;
}

/**
 * Tick spacing from the real span, so a two-week case does not get the same axis
 * as a two-year one. The mockup's fixed "Month 1..6" bands are exactly what this
 * replaces.
 */
export function chooseTickKind(spanDays: number): TickKind {
  if (spanDays <= 21) return "day";
  if (spanDays <= 120) return "week";
  if (spanDays <= 730) return "month";
  if (spanDays <= 2190) return "quarter";
  return "year";
}

const INTERVALS: Record<TickKind, TimeInterval> = {
  day: timeDay,
  week: timeWeek,
  month: timeMonth,
  // `every` returns null only for a non-positive step, which 3 is not.
  quarter: timeMonth.every(3) as TimeInterval,
  year: timeYear,
};

// en-GB rather than the runtime locale: the axis should not silently reformat
// itself on a machine set to another locale, and tests would drift with it.
const DAY_MONTH = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short" });
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short" });
const MONTH_YEAR = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric" });

export function formatTick(date: Date, kind: TickKind, isFirst: boolean): string {
  switch (kind) {
    case "day":
    case "week":
      return DAY_MONTH.format(date);
    case "month":
      // The year is only worth repeating where it changes, or on the first tick
      // so the axis is never undated.
      return date.getMonth() === 0 || isFirst ? MONTH_YEAR.format(date) : MONTH.format(date);
    case "quarter":
      return MONTH_YEAR.format(date);
    case "year":
      return String(date.getFullYear());
  }
}

export function buildTicks(domain: [Date, Date], kind: TickKind): TimelineTick[] {
  const [start, end] = domain;
  return INTERVALS[kind]
    .range(start, end)
    .map((date, index) => ({ date, label: formatTick(date, kind, index === 0) }));
}

export interface LayoutOptions {
  /** Injectable so tests are not tied to the day they run. */
  today?: Date;
}

export function buildTimelineLayout(referrals: Referral[], options: LayoutOptions = {}): TimelineLayout {
  const today = startOfDay(options.today ?? new Date());
  const ordered = assignLanes(referrals);

  const bars: TimelineBar[] = ordered.map((referral, lane) => {
    const { end, isOpenEnded } = barEnd(referral, today);
    const start = parseDateOnly(referral.initiated_date);
    return {
      referral,
      lane,
      start,
      // A bar never runs backwards, whatever the recorded dates say. Outcome
      // dates are entered by hand and can land before the initiation date.
      end: end < start ? start : end,
      isOpenEnded,
    };
  });

  if (!bars.length) {
    return { bars, brackets: [], arrows: [], ticks: [], tickKind: "week", domain: [today, today], laneCount: 0 };
  }

  const domainStart = new Date(Math.min(...bars.map((bar) => bar.start.getTime())));
  let domainEnd = new Date(Math.max(...bars.map((bar) => bar.end.getTime())));
  // A single same-day referral would give a zero-width domain and a scale that
  // divides by zero, so give it a day to occupy.
  if (domainEnd.getTime() - domainStart.getTime() < MS_PER_DAY) {
    domainEnd = new Date(domainStart.getTime() + MS_PER_DAY);
  }
  const domain: [Date, Date] = [domainStart, domainEnd];

  const spanDays = (domainEnd.getTime() - domainStart.getTime()) / MS_PER_DAY;
  const tickKind = chooseTickKind(spanDays);

  const laneOf = new Map(bars.map((bar) => [bar.referral.id, bar]));

  const groups = new Map<string, string[]>();
  bars.forEach((bar) => {
    const groupId = bar.referral.parallel_group_id;
    if (!groupId) return;
    groups.set(groupId, [...(groups.get(groupId) ?? []), bar.referral.id]);
  });

  const brackets: ParallelBracket[] = [...groups.entries()]
    // A group of one is not concurrency. It happens when the sibling is on
    // another page of results or was hard-deleted; bracketing a lone bar would
    // claim a relationship that is not on screen.
    .filter(([, ids]) => ids.length > 1)
    .map(([groupId, ids]) => {
      const lanes = ids.map((id) => laneOf.get(id)!.lane);
      return { groupId, firstLane: Math.min(...lanes), lastLane: Math.max(...lanes), referralIds: ids };
    })
    .sort((a, b) => a.firstLane - b.firstLane);

  const arrows: DependencyArrow[] = [];
  bars.forEach((bar) => {
    const parentId = bar.referral.parent_referral;
    if (!parentId) return;
    const parent = laneOf.get(parentId);
    // The parent may be outside the set handed to this component — a filtered
    // view, or a case whose earlier referrals are not loaded. Draw nothing
    // rather than an arrow from nowhere.
    if (!parent) return;
    const trigger = bar.referral.referral_trigger;
    // Only Onward and Replacement carry a parent (§5.2); a Manual referral with
    // one would be a data fault, and there is no honest label for that arrow.
    if (trigger !== "ONWARD" && trigger !== "REPLACEMENT") return;
    arrows.push({
      fromId: parent.referral.id,
      toId: bar.referral.id,
      kind: trigger === "ONWARD" ? "onward" : "replacement",
      fromLane: parent.lane,
      toLane: bar.lane,
      fromDate: parent.end,
      toDate: bar.start,
    });
  });

  return { bars, brackets, arrows, ticks: buildTicks(domain, tickKind), tickKind, domain, laneCount: bars.length };
}
