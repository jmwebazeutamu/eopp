import { describe, expect, it } from "vitest";

import {
  MARK_MAX_PERCENT,
  MIN_VISIBLE_PERCENT,
  barPercent,
  funnelFill,
  lagScale,
  compositionSegments,
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
    // Inside the track, not at its edge. This asserted 100 — which is where
    // the mark was drawn, and where the track's `overflow: hidden` clipped it
    // away entirely. On the programme dashboard every partner median was
    // withheld, `lagScale` fell back to the standard, and the panel promised a
    // reference mark it never drew.
    expect(standardMarkPercent(14, lagScale([2, 4, 6], 14))).toBe(MARK_MAX_PERCENT);
    expect(MARK_MAX_PERCENT).toBeLessThan(100);
  });

  it("stretches to the worst partner when one is over the standard", () => {
    expect(lagScale([2, 20], 14)).toBe(20);
    expect(standardMarkPercent(14, 20)).toBe(70);
  });

  it("never returns zero, so no bar divides by it", () => {
    expect(lagScale([], 0)).toBe(1);
  });
});

describe("compositionSegments", () => {
  it("never derives a segment by subtraction", () => {
    // The gender bar drew women from the API and computed men as 100 - women,
    // which absorbed every "Other" and unrecorded youth into the male segment.
    const segments = compositionSegments(
      [
        { key: "FEMALE", label: "Women", n: 26 },
        { key: "MALE", label: "Men", n: 24 },
        { key: "OTHER", label: "Other", n: 8 },
      ],
      63,
    );
    expect(segments.map((s) => s.key)).toEqual(["FEMALE", "MALE", "OTHER", "unaccounted"]);
    expect(segments.find((s) => s.key === "MALE")?.n).toBe(24);
  });

  it("surfaces whatever the server did not account for", () => {
    // 26 + 24 of 63 leaves 13 unaccounted. A bar that does not add up should
    // look like one rather than quietly balancing itself.
    const segments = compositionSegments(
      [
        { key: "FEMALE", label: "Women", n: 26 },
        { key: "MALE", label: "Men", n: 24 },
      ],
      63,
    );
    const remainder = segments.find((s) => s.key === "unaccounted");
    expect(remainder?.n).toBe(13);
    expect(remainder?.percent).toBe(21);
  });

  it("adds no remainder when the categories account for the total", () => {
    const segments = compositionSegments(
      [
        { key: "FEMALE", label: "Women", n: 30 },
        { key: "MALE", label: "Men", n: 30 },
      ],
      60,
    );
    expect(segments.map((s) => s.key)).toEqual(["FEMALE", "MALE"]);
  });

  it("drops empty categories rather than drawing zero-width slivers", () => {
    const segments = compositionSegments(
      [
        { key: "FEMALE", label: "Women", n: 10 },
        { key: "OTHER", label: "Other", n: 0 },
      ],
      10,
    );
    expect(segments.map((s) => s.key)).toEqual(["FEMALE"]);
  });

  it("returns nothing at all for an empty total", () => {
    expect(compositionSegments([{ key: "FEMALE", label: "Women", n: 0 }], 0)).toEqual([]);
  });
});
