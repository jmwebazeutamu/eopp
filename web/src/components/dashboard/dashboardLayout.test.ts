import { describe, expect, it } from "vitest";

import {
  MIN_VISIBLE_PERCENT,
  barPercent,
  funnelFill,
  lagScale,
  splitSegments,
  standardMarkPercent,
} from "./dashboardLayout";

/**
 * The bar arithmetic, tested as a pure module.
 *
 * jsdom applies no stylesheet, so asserting on a rendered bar's width would
 * assert on nothing. What matters here is that a small number is still visible,
 * a zero is still zero, and the two ends of the funnel ramp stay pinned.
 */

describe("barPercent", () => {
  it("scales a value against the track's maximum", () => {
    expect(barPercent(50, 200)).toBe(25);
    expect(barPercent(200, 200)).toBe(100);
  });

  it("keeps a tiny non-zero value visible", () => {
    // 1 of 4,812 is 0.02% — a sliver, but "one youth placed" and "none placed"
    // must not render identically.
    expect(barPercent(1, 4812)).toBe(MIN_VISIBLE_PERCENT);
  });

  it("draws nothing at all for a true zero", () => {
    expect(barPercent(0, 100)).toBe(0);
  });

  it("never overflows its track", () => {
    expect(barPercent(300, 200)).toBe(100);
  });

  it("survives an empty programme rather than dividing by zero", () => {
    expect(barPercent(0, 0)).toBe(0);
    expect(barPercent(5, 0)).toBe(0);
    expect(barPercent(Number.NaN, 100)).toBe(0);
  });
});

describe("funnelFill", () => {
  it("pins the handoff's two ends: green-900 at the top, gold at the last stage", () => {
    expect(funnelFill(0, 5)).toBe("var(--green-900)");
    expect(funnelFill(4, 5)).toBe("var(--gold-500)");
  });

  it("steps through green in between, reaching the lightest step before the gold", () => {
    const middle = [1, 2, 3].map((index) => funnelFill(index, 5));
    expect(middle).toEqual(["var(--green-700)", "var(--green-500)", "var(--green-500)"]);
    // The dark steps belong at the top, where the counts are largest.
    expect(funnelFill(1, 5)).not.toBe(funnelFill(3, 5));
  });

  it("still ends on gold when Sprint 5 adds the sixth stage", () => {
    expect(funnelFill(5, 6)).toBe("var(--gold-500)");
    expect(funnelFill(0, 6)).toBe("var(--green-900)");
  });

  it("handles a one-stage funnel without indexing off the end", () => {
    expect(funnelFill(0, 1)).toBe("var(--green-900)");
  });
});

describe("lagScale", () => {
  it("keeps the programme standard inside the range when every partner beats it", () => {
    // Otherwise the 14-day mark sits off the end of the track exactly when a
    // supervisor most wants to see that everyone is inside it.
    expect(lagScale([2, 4, 6], 14)).toBe(14);
    expect(standardMarkPercent(14, lagScale([2, 4, 6], 14))).toBe(100);
  });

  it("stretches to the worst partner when one is over the standard", () => {
    expect(lagScale([2, 20], 14)).toBe(20);
    expect(standardMarkPercent(14, 20)).toBe(70);
  });

  it("never returns zero, so no bar divides by it", () => {
    expect(lagScale([], 0)).toBe(1);
  });
});

describe("splitSegments", () => {
  it("closes the bar even when the two rounded shares do not total 100", () => {
    // 46.4 and 53.6 both round down; drawn independently they leave a hairline.
    const segments = splitSegments(46, 53);
    expect(segments.female + segments.male).toBe(100);
  });

  it("clamps a share that arrives out of range", () => {
    expect(splitSegments(140, 0).female).toBe(100);
    expect(splitSegments(-5, 100).female).toBe(0);
  });

  it("gives the whole bar to one side when every placement is one sex", () => {
    expect(splitSegments(100, 0)).toEqual({ female: 100, male: 0 });
  });
});
