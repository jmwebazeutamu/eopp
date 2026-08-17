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
  return Math.min(100, (standard / scale) * 100);
}

/**
 * The gender split bar.
 *
 * Rounding each share independently can total 99 or 101 and leave a hairline
 * gap or an overflow in a two-segment bar that must read as one whole. The
 * second segment takes the remainder so the bar always closes.
 */
export function splitSegments(female: number, male: number): { female: number; male: number } {
  const left = Math.max(0, Math.min(100, Math.round(female)));
  const right = Math.max(0, 100 - left);
  // `male` is the server's own figure; it is only used to decide whether the
  // split is meaningful at all, not to size the bar.
  return { female: left, male: male > 0 || left < 100 ? right : 0 };
}
