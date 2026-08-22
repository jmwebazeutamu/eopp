import type { WltMeeting } from "../../api/types";

/**
 * The fund trend on the Meetings tab.
 *
 * Arithmetic only, no pixels of its own beyond the box it is given — the
 * `timelineLayout.ts` pattern. A polyline is easy to draw and easy to draw
 * *wrong*: an unbaselined y-axis exaggerates a 2% wobble into a cliff, and a
 * series that silently drops the meetings with no recorded cash draws a line
 * through a gap as though it were flat.
 *
 * No chart library — the brief's 3G constraint. This is a handful of points
 * and a `<polyline>`.
 */

export interface FundPoint {
  meetingNo: number;
  heldOn: string;
  /** Cash counted at the close, in ETB. */
  value: number;
  x: number;
  y: number;
  /** A move worth drawing attention to, against the previous point. */
  notable: boolean;
}

export interface FundSeries {
  points: FundPoint[];
  min: number;
  max: number;
  /** y of the zero line, or null when zero is off the drawn range. */
  baselineY: number | null;
  midY: number;
  width: number;
  height: number;
}

/**
 * A **fall** of this share against the previous point is marked.
 *
 * Falls only, deliberately. The handoff proposes marking any move over 50%,
 * but a savings group's fund routinely doubles week to week early on — 100 to
 * 200 ETB is two members paying in, not an event — so a symmetric rule marks
 * ordinary growth and teaches the reader to ignore the mark.
 *
 * A fall is different: it is money leaving the box, which is either a loan
 * disbursement or a problem. The mark says "look at this", not "something is
 * wrong", because from the meeting list alone the two are indistinguishable —
 * the demo group's 11,860 to 1,860 drop is a single 10,000 ETB loan.
 */
export const NOTABLE_FALL = 0.5;

/**
 * Build the series from closed meetings, oldest to newest.
 *
 * Open meetings are excluded: their cash is not counted yet, and plotting an
 * in-progress meeting at zero would draw a cliff that closing it would undo.
 * Meetings with no counted figure are excluded for the same reason — a gap is
 * honest, a zero is not.
 */
export function buildFundSeries(
  meetings: WltMeeting[],
  { width = 760, height = 120, limit = 12 }: { width?: number; height?: number; limit?: number } = {},
): FundSeries {
  const usable = meetings
    .filter((meeting) => meeting.status === "CLOSED" && meeting.counted_cash_etb !== null)
    .map((meeting) => ({
      meetingNo: meeting.meeting_no,
      heldOn: meeting.held_on,
      value: Number(meeting.counted_cash_etb),
    }))
    .filter((row) => Number.isFinite(row.value))
    // Oldest first for drawing; `slice(-limit)` keeps the most recent window.
    .sort((a, b) => a.meetingNo - b.meetingNo)
    .slice(-limit);

  if (usable.length === 0) {
    return { points: [], min: 0, max: 0, baselineY: null, midY: height / 2, width, height };
  }

  const values = usable.map((row) => row.value);
  const max = Math.max(...values);
  // Anchored at zero rather than at the smallest value. A fund that moved from
  // 11,800 to 11,860 is a flat line, and a self-scaling axis would draw it as a
  // climb across the whole card.
  const min = Math.min(0, ...values);
  const span = max - min || 1;

  const scaleY = (value: number) => height - ((value - min) / span) * height;
  const step = usable.length > 1 ? width / (usable.length - 1) : 0;

  const points: FundPoint[] = usable.map((row, index) => {
    const previous = index > 0 ? usable[index - 1].value : null;
    return {
      ...row,
      x: usable.length > 1 ? index * step : width / 2,
      y: scaleY(row.value),
      notable:
        previous !== null && previous > 0 && (previous - row.value) / previous >= NOTABLE_FALL,
    };
  });

  return {
    points,
    min,
    max,
    baselineY: min <= 0 && max >= 0 ? scaleY(0) : null,
    midY: scaleY((max + min) / 2),
    width,
    height,
  };
}

/** The `points` attribute for a `<polyline>`. */
export function polylinePoints(series: FundSeries): string {
  return series.points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
}
