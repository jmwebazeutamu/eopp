import { describe, expect, it } from "vitest";

import type { WltMeeting } from "../../api/types";
import { buildFundSeries, polylinePoints } from "./fundSeries";

function meeting(over: Partial<WltMeeting> = {}): WltMeeting {
  return {
    id: `m${over.meeting_no ?? 1}`,
    group: "g1",
    meeting_no: 1,
    scheduled_for: null,
    held_on: "2026-01-05",
    opening_cash_etb: "0",
    closing_cash_etb: "100",
    counted_cash_etb: "100",
    social_time_minutes: null,
    social_topic: "",
    status: "CLOSED",
    closed_at: "2026-01-05",
    device_id: "",
    synced_at: null,
    ...over,
  };
}

const rising = [
  meeting({ meeting_no: 1, counted_cash_etb: "100" }),
  meeting({ meeting_no: 2, counted_cash_etb: "200" }),
  meeting({ meeting_no: 3, counted_cash_etb: "300" }),
];

describe("buildFundSeries", () => {
  it("plots oldest to newest whatever order it is given", () => {
    const series = buildFundSeries([...rising].reverse());
    expect(series.points.map((p) => p.meetingNo)).toEqual([1, 2, 3]);
  });

  it("anchors the axis at zero rather than at the smallest value", () => {
    // A fund that moved 11,800 -> 11,860 is a flat line. A self-scaling axis
    // would draw that 0.5% wobble as a climb across the whole card.
    const series = buildFundSeries([
      meeting({ meeting_no: 1, counted_cash_etb: "11800" }),
      meeting({ meeting_no: 2, counted_cash_etb: "11860" }),
    ]);
    expect(series.min).toBe(0);
    const rise = series.points[0].y - series.points[1].y;
    expect(rise).toBeLessThan(series.height * 0.02);
  });

  it("excludes an open meeting, whose cash is not counted yet", () => {
    // Plotting it at zero would draw a cliff that closing it would undo.
    const series = buildFundSeries([...rising, meeting({ meeting_no: 4, status: "OPEN", counted_cash_etb: null })]);
    expect(series.points.map((p) => p.meetingNo)).toEqual([1, 2, 3]);
  });

  it("leaves out a meeting with no counted figure rather than plotting zero", () => {
    const series = buildFundSeries([...rising, meeting({ meeting_no: 4, counted_cash_etb: null })]);
    expect(series.points).toHaveLength(3);
  });

  it("keeps the most recent window, not the first", () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      meeting({ meeting_no: i + 1, counted_cash_etb: String((i + 1) * 10) }),
    );
    const series = buildFundSeries(many, { limit: 12 });
    expect(series.points).toHaveLength(12);
    expect(series.points[0].meetingNo).toBe(9);
    expect(series.points[11].meetingNo).toBe(20);
  });

  it("marks a large move against the previous point", () => {
    // The 11,860 -> 1,860 drop on the demo data: an 84% fall, worth a mark.
    const series = buildFundSeries([
      meeting({ meeting_no: 1, counted_cash_etb: "11860" }),
      meeting({ meeting_no: 2, counted_cash_etb: "1860" }),
    ]);
    expect(series.points[0].notable).toBe(false);
    expect(series.points[1].notable).toBe(true);
  });

  it("does not mark growth, however steep", () => {
    // A savings group's fund routinely doubles early on — 100 to 200 ETB is two
    // members paying in. A symmetric rule marks that and teaches the reader to
    // ignore the mark.
    const series = buildFundSeries(rising);
    expect(series.points.every((p) => p.notable === false)).toBe(true);
  });

  it("survives a single meeting without dividing by zero", () => {
    const series = buildFundSeries([meeting({ meeting_no: 1, counted_cash_etb: "500" })]);
    expect(series.points).toHaveLength(1);
    expect(Number.isFinite(series.points[0].x)).toBe(true);
    expect(Number.isFinite(series.points[0].y)).toBe(true);
  });

  it("returns an empty series rather than throwing when there is nothing to draw", () => {
    const series = buildFundSeries([]);
    expect(series.points).toEqual([]);
    expect(polylinePoints(series)).toBe("");
  });

  it("keeps every point inside the box", () => {
    const series = buildFundSeries(rising, { width: 760, height: 120 });
    for (const point of series.points) {
      expect(point.x).toBeGreaterThanOrEqual(0);
      expect(point.x).toBeLessThanOrEqual(760);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(120);
    }
  });
});

describe("polylinePoints", () => {
  it("emits one pair per point", () => {
    expect(polylinePoints(buildFundSeries(rising)).split(" ")).toHaveLength(3);
  });
});
