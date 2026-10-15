/**
 * Which links fit on one row, and which go behind "More".
 *
 * Pure arithmetic, apart from the component, for the reason `timelineLayout.ts`
 * is: jsdom applies no stylesheet and measures nothing, so the part worth testing
 * is the decision, not the pixels.
 */

export interface OverflowSplit {
  visible: number[];
  overflow: number[];
}

/**
 * @param widths   rendered width of each item, in order
 * @param available width of the row
 * @param moreWidth width of the "More" button, reserved only when something overflows
 * @param gap      space between neighbours
 * @param pinned   an index that must stay on the row (the current page) — an
 *                 active destination hidden in a menu is a reader who has lost
 *                 their place
 */
export function splitOverflow(
  widths: number[],
  available: number,
  moreWidth: number,
  gap: number,
  pinned: number | null,
): OverflowSplit {
  const all = widths.map((_, i) => i);
  const total = widths.reduce((sum, w) => sum + w, 0) + gap * Math.max(0, widths.length - 1);
  if (total <= available) return { visible: all, overflow: [] };

  const room = available - moreWidth - gap;
  const visible: number[] = [];
  let used = 0;
  for (const i of all) {
    const next = used + (visible.length ? gap : 0) + widths[i];
    if (next > room) break;
    visible.push(i);
    used = next;
  }

  if (pinned !== null && !visible.includes(pinned)) {
    // Make space for the pinned item by dropping from the end until it fits.
    while (visible.length > 0) {
      const sum = visible.reduce((s, i) => s + widths[i], 0) + gap * visible.length + widths[pinned];
      if (sum <= room) break;
      visible.pop();
    }
    visible.push(pinned);
    visible.sort((a, b) => a - b);
  }
  return { visible, overflow: all.filter((i) => !visible.includes(i)) };
}
