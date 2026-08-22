import type { Referral, ReferralStatusCode } from "../../api/types";
import { buildTimelineScale } from "../timeline/TimelinePrimitives";

/**
 * Layout arithmetic for the referral stack timeline (spec §6.4).
 *
 * Three fixed tracks — Slot 1, Slot 2 and Exempt — because §6.3 is about how
 * many referrals may run *at once*: the picture should show two slots filling
 * and emptying over time, with the exempt Complementary Service stream visibly
 * outside them.
 *
 * Everything here is in tracks, rows and fractions of the domain; the component
 * turns those into pixels. Bar extents, track packing and tick spacing are the
 * parts that can be wrong in ways a screenshot will not show, so they are the
 * parts that are unit tested.
 */

/** Statuses where the referral is still running, so its bar has no closing edge. */
const OPEN_STATUSES: ReferralStatusCode[] = ["PENDING_CONFIRMATION", "ACTIVE"];

export type TrackId = "slot-1" | "slot-2" | "exempt";

export interface TimelineBar {
  referral: Referral;
  track: TrackId;
  /** Sub-row within the track, so two overlapping bars cannot hide each other. */
  row: number;
  start: Date;
  end: Date;
  /** True when `end` is "now" rather than a recorded outcome. */
  isOpenEnded: boolean;
  /** Position within the domain, 0–1, ready for a percentage. */
  offset: number;
  width: number;
}

export interface TimelineTrack {
  id: TrackId;
  label: string;
  bars: TimelineBar[];
  /** At least 1, more when bars in this track overlap in time. */
  rowCount: number;
}

export interface DependencyLink {
  fromId: string;
  toId: string;
  kind: "onward" | "replacement";
}

export type TickKind = "day" | "week" | "month" | "quarter";

export interface TimelineTick {
  /** Position within the domain, 0–1. */
  offset: number;
  label: string;
  date: Date;
}

export interface TimelineLayout {
  tracks: TimelineTrack[];
  links: DependencyLink[];
  ticks: TimelineTick[];
  tickKind: TickKind;
  domain: [Date, Date];
  /** For the heading: "2026", or "2025–2026" when the case spans a new year. */
  yearLabel: string;
  isEmpty: boolean;
}

const MS_PER_DAY = 86_400_000;

/**
 * Parse an API `YYYY-MM-DD` into local midnight.
 *
 * `new Date("2026-03-05")` is parsed as UTC midnight, which in
 * Africa/Addis_Ababa (UTC+3) still renders as the 5th, but west of Greenwich
 * would render as the 4th. Constructing the local date keeps a referral's bar
 * on the day the case manager recorded it, wherever the browser is.
 */
export function parseDateOnly(value: string): Date {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/**
 * Where a referral's bar stops.
 *
 * `transition_to` sets `outcome_date` on Completed and `failure_date` on
 * Failed, and Replaced is only reachable from Failed so it inherits that date.
 * Cancelled records no date at all — §6.2 gives it no System Action — so the
 * bar closes at `updated_at`, when the withdrawal was written. Falling back to
 * today would draw a referral cancelled months ago as though it still ran.
 */
export function barEnd(
  referral: Referral,
  today: Date,
): { end: Date; isOpenEnded: boolean } {
  if (OPEN_STATUSES.includes(referral.status)) {
    return { end: today, isOpenEnded: true };
  }
  const recorded = referral.outcome_date ?? referral.failure_date;
  if (recorded) {
    return { end: parseDateOnly(recorded), isOpenEnded: false };
  }
  return { end: startOfDay(new Date(referral.updated_at)), isOpenEnded: false };
}

/** Initiation order, ties broken on id so the layout is stable across renders. */
function byInitiation(a: Referral, b: Referral): number {
  if (a.initiated_date !== b.initiated_date)
    return a.initiated_date < b.initiated_date ? -1 : 1;
  return a.id < b.id ? -1 : 1;
}

interface Extent {
  referral: Referral;
  start: Date;
  end: Date;
  isOpenEnded: boolean;
  /**
   * The end used for packing and row assignment, never for drawing.
   *
   * A same-day referral is a zero-length interval, so by date arithmetic two of
   * them do not overlap — but both are drawn at the same position and floored to
   * the same minimum width, so on screen they sit exactly on top of each other.
   * Treating a zero-length bar as occupying its whole day makes the collision
   * visible to the packer, which then stacks them instead of hiding all but one.
   */
  packEnd: Date;
}

/**
 * Pack the cap-counting referrals into the two slots.
 *
 * A referral takes the lowest-numbered slot free when it starts — the same rule
 * a case manager applies at the desk. §6.3 permits two at a time, so anything
 * needing a third slot has overlapped in a way the cap should have prevented;
 * it goes to slot 2 rather than being dropped, because a referral missing from
 * the picture is worse than a crowded lane, and the lane stacks it onto its own
 * row rather than hiding it.
 */
export function packIntoSlots(extents: Extent[]): {
  slot1: Extent[];
  slot2: Extent[];
  overflow: Extent[];
} {
  const slot1: Extent[] = [];
  const slot2: Extent[] = [];
  const overflow: Extent[] = [];

  extents.forEach((extent) => {
    const freeIn = (slot: Extent[]) =>
      !slot.length || slot[slot.length - 1].packEnd <= extent.start;
    if (freeIn(slot1)) slot1.push(extent);
    else if (freeIn(slot2)) slot2.push(extent);
    else {
      slot2.push(extent);
      overflow.push(extent);
    }
  });

  return { slot1, slot2, overflow };
}

/**
 * Give each bar in a track a row, so overlapping bars stack instead of hiding
 * each other.
 *
 * Within a slot this should never be needed — the cap is what stops two running
 * at once — but the Exempt track has no cap at all, and two concurrent
 * Complementary Service referrals drawn on one row would silently cover one
 * another. Whichever started first keeps the top row.
 */
export function assignRows(
  extents: Extent[],
): { extent: Extent; row: number }[] {
  const rowEnds: Date[] = [];

  return extents.map((extent) => {
    let row = rowEnds.findIndex((end) => end <= extent.start);
    if (row === -1) {
      row = rowEnds.length;
      rowEnds.push(extent.packEnd);
    } else {
      rowEnds[row] = extent.packEnd;
    }
    return { extent, row };
  });
}

/**
 * Tick spacing from the real span, so a two-week case does not get the same
 * axis as a two-year one. A single month label — which is what a month-only
 * axis degrades to on a short case — tells the reader nothing about when
 * anything happened relative to anything else.
 */
export function chooseTickKind(spanDays: number): TickKind {
  if (spanDays <= 21) return "day";
  if (spanDays <= 120) return "week";
  if (spanDays <= 730) return "month";
  return "quarter";
}

// en-GB rather than the runtime locale: the axis should not reformat itself on
// a machine set to another locale, and tests would drift with it.
const DAY_MONTH = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
});
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short" });
const MONTH_YEAR = new Intl.DateTimeFormat("en-GB", {
  month: "short",
  year: "numeric",
});
const FULL_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatTick(
  date: Date,
  kind: TickKind,
  isFirst: boolean,
): string {
  switch (kind) {
    case "day":
    case "week":
      return DAY_MONTH.format(date);
    case "month":
      // The year is worth repeating only where it changes, or on the first tick
      // so the axis is never undated.
      return date.getMonth() === 0 || isFirst
        ? MONTH_YEAR.format(date)
        : MONTH.format(date);
    case "quarter":
      return MONTH_YEAR.format(date);
  }
}

export interface LayoutOptions {
  /** Injectable so tests are not tied to the day they run. */
  today?: Date;
}

export function buildTimelineLayout(
  referrals: Referral[],
  options: LayoutOptions = {},
): TimelineLayout {
  const today = startOfDay(options.today ?? new Date());
  if (!referrals.length) {
    return {
      tracks: [],
      links: [],
      ticks: [],
      tickKind: "week",
      domain: [today, today],
      yearLabel: String(today.getFullYear()),
      isEmpty: true,
    };
  }

  const extents: Extent[] = [...referrals]
    .sort(byInitiation)
    .map((referral) => {
      const { end, isOpenEnded } = barEnd(referral, today);
      const start = parseDateOnly(referral.initiated_date);
      // A bar never runs backwards, whatever the recorded dates say — both are
      // hand-entered and an outcome can land before the initiation date.
      const safeEnd = end < start ? start : end;
      return {
        referral,
        start,
        end: safeEnd,
        isOpenEnded,
        packEnd:
          safeEnd > start ? safeEnd : new Date(start.getTime() + MS_PER_DAY),
      };
    });

  // Earliest initiation to the later of today and the last outcome: an open
  // referral has to reach the right-hand edge, and a case closed months ago
  // should not stretch the axis to today for no reason.
  const first = new Date(Math.min(...extents.map((e) => e.start.getTime())));
  const lastEnd = new Date(Math.max(...extents.map((e) => e.end.getTime())));
  const scale = buildTimelineScale([first, lastEnd], today);
  const [domainStart, domainEnd] = scale.domain;
  const position = scale.position;

  const exempt = extents.filter((e) => !e.referral.counts_toward_parallel_cap);
  const counting = extents.filter((e) => e.referral.counts_toward_parallel_cap);
  const { slot1, slot2 } = packIntoSlots(counting);

  const buildTrack = (
    id: TrackId,
    label: string,
    members: Extent[],
  ): TimelineTrack => {
    const placed = assignRows(members);
    const bars = placed.map(({ extent, row }) => {
      const offset = position(extent.start);
      return {
        referral: extent.referral,
        track: id,
        row,
        start: extent.start,
        end: extent.end,
        isOpenEnded: extent.isOpenEnded,
        offset,
        // Real duration; the component applies the minimum *pixel* width, which
        // cannot be expressed here without knowing how wide the chart is.
        width: Math.max(position(extent.end) - offset, 0),
      };
    });
    return {
      id,
      label,
      bars,
      rowCount: Math.max(1, ...placed.map((p) => p.row + 1)),
    };
  };

  const tracks: TimelineTrack[] = [
    buildTrack("slot-1", "Slot 1", slot1),
    buildTrack("slot-2", "Slot 2", slot2),
    buildTrack("exempt", "Exempt", exempt),
  ];

  const present = new Set(referrals.map((r) => r.id));
  const links: DependencyLink[] = referrals
    .filter((r) => r.parent_referral && present.has(r.parent_referral))
    // Only Onward and Replacement carry a parent (§5.2); a Manual referral with
    // one is a data fault, and there is no honest label for that link.
    .filter(
      (r) =>
        r.referral_trigger === "ONWARD" || r.referral_trigger === "REPLACEMENT",
    )
    .map((r) => ({
      fromId: r.parent_referral!,
      toId: r.id,
      kind:
        r.referral_trigger === "ONWARD"
          ? ("onward" as const)
          : ("replacement" as const),
    }));

  const tickKind = scale.tickKind;
  const ticks: TimelineTick[] = scale.ticks;

  return {
    tracks,
    links,
    ticks,
    tickKind,
    domain: [domainStart, domainEnd],
    yearLabel: scale.yearLabel,
    isEmpty: false,
  };
}

/** The period sentence for a bar's label and tooltip. */
export function periodLabel(bar: TimelineBar): string {
  const from = FULL_DATE.format(bar.start);
  return bar.isOpenEnded
    ? `${from} – ongoing`
    : `${from} – ${FULL_DATE.format(bar.end)}`;
}

/** How many days a bar covers, for the tooltip's "ran for N days". */
export function durationDays(bar: TimelineBar): number {
  return Math.max(
    1,
    Math.round((bar.end.getTime() - bar.start.getTime()) / MS_PER_DAY) + 1,
  );
}
