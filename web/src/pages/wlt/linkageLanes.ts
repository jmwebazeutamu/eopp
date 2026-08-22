import type { ServiceLinkage } from "../../api/types";

/**
 * Labelled lanes for a group's service linkages.
 *
 * Replaces a timeline whose lanes were unlabelled, whose axis covered three
 * days, and whose labels ran past the right edge. Each linkage gets a row: its
 * type and partner in a fixed label column, and one marker on the day something
 * last happened to it.
 *
 * Arithmetic only. The `timelineLayout.ts` rule applies — this is the part
 * worth testing, and a test asserting on rendered pixels would assert on
 * nothing, because jsdom applies no stylesheet.
 *
 * Two faults from `timelineLayout.ts` are guarded here because the same shapes
 * produce them: **a marker that does not fit must not escape** the plotting
 * area, and **two events on one day must not collide** — a linkage opened and
 * approved on the same date is ordinary, not an edge case.
 */

export interface Lane {
  id: string;
  label: string;
  partner: string | null;
  status: ServiceLinkage["status"];
  statusLabel: string;
  /** The day this lane's marker sits on. */
  date: string;
  /** 0..1 across the plotting area. */
  position: number;
  /**
   * How to anchor the marker so it stays inside the area.
   *
   * A marker centred on a point near either edge hangs off it. Anchoring
   * start/end at the extremes keeps the whole label inside without moving the
   * point it refers to.
   */
  anchor: "start" | "middle" | "end";
  blocked: boolean;
}

export interface LaneAxis {
  /** Tick labels, evenly spaced, oldest first. */
  ticks: Array<{ date: string; position: number }>;
  from: string;
  to: string;
  /** True when every linkage falls on one day and the axis is nominal. */
  singleDay: boolean;
}

export interface LaneLayout {
  lanes: Lane[];
  axis: LaneAxis;
}

/** Beyond this share of the width a marker anchors to the edge instead. */
const EDGE = 0.08;

const DAY = 24 * 60 * 60 * 1000;

function toDay(value: string): number {
  return Math.floor(new Date(`${value}T00:00:00Z`).getTime() / DAY);
}

function fromDay(day: number): string {
  return new Date(day * DAY).toISOString().slice(0, 10);
}

/**
 * The date a lane is drawn at: the most recent thing that actually happened.
 *
 * Not `opened_on` alone. A linkage opened in March and activated in August sits
 * in August, because the lane answers "where is this now", and a row parked at
 * its opening date reads as stale work nobody has touched.
 */
export function eventDate(linkage: ServiceLinkage): string {
  return linkage.closed_on ?? linkage.activated_on ?? linkage.approved_on ?? linkage.opened_on;
}

/**
 * Lay out one lane per linkage, plus an axis.
 *
 * `ticks` defaults to five, the handoff's figure. A range shorter than the tick
 * count collapses to one tick per day rather than repeating a date, because a
 * five-tick axis over three days prints the same day twice and reads as a
 * rendering fault.
 */
export function buildLanes(linkages: ServiceLinkage[], { ticks = 5 }: { ticks?: number } = {}): LaneLayout {
  if (linkages.length === 0) {
    const today = fromDay(Math.floor(Date.now() / DAY));
    return { lanes: [], axis: { ticks: [], from: today, to: today, singleDay: true } };
  }

  const days = linkages.map((linkage) => toDay(eventDate(linkage)));
  const first = Math.min(...days);
  const last = Math.max(...days);
  // One day of padding either side, so a marker on the first or last day is not
  // pinned against the frame.
  const from = first === last ? first - 1 : first;
  const to = first === last ? last + 1 : last;
  const span = to - from || 1;

  const tickCount = Math.max(2, Math.min(ticks, span + 1));
  const axisTicks = Array.from({ length: tickCount }, (_, index) => {
    const day = Math.round(from + (span * index) / (tickCount - 1));
    return { date: fromDay(day), position: (day - from) / span };
  });

  const lanes: Lane[] = linkages.map((linkage) => {
    const date = eventDate(linkage);
    const position = (toDay(date) - from) / span;
    return {
      id: linkage.id,
      label: linkage.type_label,
      partner: linkage.provider_name,
      status: linkage.status,
      statusLabel: linkage.status_display,
      date,
      position,
      anchor: position <= EDGE ? "start" : position >= 1 - EDGE ? "end" : "middle",
      blocked: linkage.block_reasons.length > 0,
    };
  });

  return {
    lanes,
    axis: {
      ticks: axisTicks,
      from: fromDay(from),
      to: fromDay(to),
      singleDay: first === last,
    },
  };
}
