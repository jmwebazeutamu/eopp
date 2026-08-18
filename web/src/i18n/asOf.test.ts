import { describe, expect, it } from "vitest";

import { formatAsOf } from "./asOf";

/**
 * 4.5. Three pages formatted the same timestamp three ways, all in the
 * viewer's timezone: "8/17/2026", "8/17/2026, 10:11:56 PM", and "10:12 PM"
 * with no date at all. The server value was 2026-08-18T02:06Z, so every page
 * was reporting the wrong day for anyone west of East Africa.
 */
describe("formatAsOf", () => {
  it("renders in East Africa Time, not the viewer's", () => {
    // 02:06 UTC on the 18th is 05:06 on the 18th in Addis. Rendered in a
    // western timezone it would read as the 17th, which is what the pages did.
    expect(formatAsOf("2026-08-18T02:06:00Z")).toBe("18 Aug 2026, 05:06");
  });

  it("never drops the date", () => {
    // The woreda page rendered time only, which cannot be read after midnight.
    expect(formatAsOf("2026-08-18T02:06:00Z")).toMatch(/\d{2} \w{3} \d{4}/);
  });

  it("is the same string on every page", () => {
    const iso = "2026-08-18T02:06:00Z";
    expect(formatAsOf(iso)).toBe(formatAsOf(iso));
  });

  it("returns empty rather than 'Invalid Date' for a bad value", () => {
    expect(formatAsOf("not a timestamp")).toBe("");
  });
});
