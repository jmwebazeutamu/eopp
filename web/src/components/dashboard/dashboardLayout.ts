/**
 * The dashboard's bar arithmetic — no pixels, no JSX, no tokens applied.
 *
 * Same split as `timelineLayout.ts`: the part worth unit testing is how a number
 * becomes a width and a colour, not how a `<div>` renders. jsdom applies no
 * stylesheet, so a test that asserted on rendered geometry would be asserting on
 * nothing.
 */

/** A bar narrower than this is invisible; a non-zero value must never look like zero. */
export const MIN_VISIBLE_PERCENT = 1.5;

/**
 * A value's share of the track, in percent.
 *
 * Two rules the design brief forces:
 *  - a non-zero value always gets a visible sliver, because "too small to draw"
 *    and "none" are different findings and must not render identically;
 *  - a true zero draws nothing at all, so an empty woreda is visibly empty.
 */
export function barPercent(value: number, max: number): number {
  if (!Number.isFinite(value) || value <= 0 || max <= 0) return 0;
  const share = (value / max) * 100;
  return Math.min(100, Math.max(MIN_VISIBLE_PERCENT, share));
}

/**
 * The funnel's colour ramp: green-900 at the top, stepping to gold at the last
 * stage the data can fill. The handoff specifies the ends, so those are pinned
 * and the middle is interpolated — which keeps the ramp correct when the funnel
 * grows a stage (Placement lands in Sprint 5 and unlocks the sixth row).
 */
const FUNNEL_MIDDLE = ["var(--green-700)", "var(--green-500)"];

export function funnelFill(index: number, total: number): string {
  if (total <= 1 || index <= 0) return "var(--green-900)";
  if (index >= total - 1) return "var(--gold-500)";
  const position = (index - 1) / Math.max(1, total - 2);
  // `ceil`, so the ramp reaches the lightest green before it turns gold rather
  // than spending two adjacent stages on the same dark step. The darkest values
  // belong at the top of the funnel, where the counts are largest.
  const step = Math.ceil(position * (FUNNEL_MIDDLE.length - 1));
  return FUNNEL_MIDDLE[Math.min(FUNNEL_MIDDLE.length - 1, step)];
}

/**
 * The confirmation-lag axis.
 *
 * The programme standard is always inside the range, so the 14-day reference
 * mark is drawable even when every partner is faster than it. Without this the
 * mark would sit off the end of the track on a healthy programme — the case
 * where a supervisor most needs to see that everyone is inside the line.
 */
export function lagScale(days: number[], standard: number): number {
  const worst = days.length ? Math.max(...days) : 0;
  return Math.max(worst, standard) || 1;
}

/** Where the standard's reference mark sits along the track, in percent. */
export function standardMarkPercent(standard: number, scale: number): number {
  if (scale <= 0) return 0;
  // Capped below 100, not at it. The track clips its overflow, so a mark
  // positioned at exactly 100% is drawn entirely outside the box — which is
  // what happened whenever every partner median was withheld and `lagScale`
  // fell back to the standard itself.
  return Math.min(MARK_MAX_PERCENT, (standard / scale) * 100);
}

/** Leaves room for the mark's own width inside the track. */
export const MARK_MAX_PERCENT = 98;

/**
 * Segments of a composition bar, sized from the values the server actually sent.
 *
 * The gender bar used to render women from the API and derive men as
 * `100 - women`, which silently absorbed every other category into "men": 13 of
 * 63 placements whose sex is "Other" or unrecorded disappeared into the male
 * segment, and "Other" is a real category holding 122 of 614 registered youth.
 *
 * Nothing is derived by subtraction here. Anything the server did not account
 * for surfaces as its own remainder segment rather than being folded into a
 * neighbour, so a bar that does not add up looks like one.
 */
export interface Segment {
  key: string;
  label: string;
  n: number;
}

export function compositionSegments(
  segments: Segment[],
  total: number,
): { key: string; label: string; n: number; percent: number }[] {
  if (total <= 0) return [];
  const accounted = segments.reduce((sum, segment) => sum + segment.n, 0);
  const rows = segments
    .filter((segment) => segment.n > 0)
    .map((segment) => ({ ...segment, percent: Math.round((segment.n / total) * 100) }));

  const unaccounted = total - accounted;
  if (unaccounted > 0) {
    rows.push({
      key: "unaccounted",
      label: "Not recorded",
      n: unaccounted,
      percent: Math.round((unaccounted / total) * 100),
    });
  }
  return rows;
}
