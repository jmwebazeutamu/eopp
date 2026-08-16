import { describe, expect, it } from "vitest";

import { makeReferral } from "../../test/referralFactory";
import {
  assignRows,
  barEnd,
  buildTimelineLayout,
  chooseTickKind,
  durationDays,
  packIntoSlots,
  parseDateOnly,
  periodLabel,
} from "./timelineLayout";

/**
 * The layout rules the rendering depends on: an axis scaled to the real span,
 * bars sized by their own dates, two slots that pack the way §6.3 says, and an
 * exempt stream that never occupies one. None of it needs a DOM.
 */

const TODAY = new Date(2026, 5, 30); // 30 June 2026

describe("parseDateOnly", () => {
  it("reads an API date as local midnight, not UTC", () => {
    const parsed = parseDateOnly("2026-03-05");
    expect([parsed.getFullYear(), parsed.getMonth(), parsed.getDate(), parsed.getHours()]).toEqual([2026, 2, 5, 0]);
  });
});

describe("barEnd", () => {
  it("runs an active referral to today", () => {
    const { end, isOpenEnded } = barEnd(makeReferral({ status: "ACTIVE" }), TODAY);
    expect(end).toEqual(TODAY);
    expect(isOpenEnded).toBe(true);
  });

  it("runs a pending referral to today — it has not closed either", () => {
    expect(barEnd(makeReferral({ status: "PENDING_CONFIRMATION" }), TODAY).isOpenEnded).toBe(true);
  });

  it("closes a completed referral on its outcome date", () => {
    const { end, isOpenEnded } = barEnd(makeReferral({ status: "COMPLETED", outcome_date: "2026-03-10" }), TODAY);
    expect(end).toEqual(new Date(2026, 2, 10));
    expect(isOpenEnded).toBe(false);
  });

  it("closes a failed referral on failure_date, which is the field the API stamps", () => {
    // §6.2 sets failure_date on Failed and outcome_date on Completed; a bar that
    // only read outcome_date would run every failure to today.
    expect(barEnd(makeReferral({ status: "FAILED", failure_date: "2026-02-20" }), TODAY).end).toEqual(
      new Date(2026, 1, 20),
    );
  });

  it("closes a replaced referral on the failure date it inherited", () => {
    expect(barEnd(makeReferral({ status: "REPLACED", failure_date: "2026-02-20" }), TODAY).end).toEqual(
      new Date(2026, 1, 20),
    );
  });

  it("closes a cancelled referral at updated_at, since §6.2 stamps no date for it", () => {
    const { end } = barEnd(makeReferral({ status: "CANCELLED", updated_at: "2026-02-02T14:30:00+03:00" }), TODAY);
    expect([end.getFullYear(), end.getMonth(), end.getDate()]).toEqual([2026, 1, 2]);
  });
});

describe("packIntoSlots", () => {
  const extent = (start: string, end: string) => {
    const from = parseDateOnly(start);
    const to = parseDateOnly(end);
    return {
      referral: makeReferral({ initiated_date: start }),
      start: from,
      end: to,
      isOpenEnded: false,
      // Same rule the layout applies: a zero-length bar still occupies its day.
      packEnd: to > from ? to : new Date(from.getTime() + 86_400_000),
    };
  };

  it("puts sequential referrals back in slot 1 as it frees up", () => {
    const { slot1, slot2 } = packIntoSlots([extent("2026-01-01", "2026-02-01"), extent("2026-03-01", "2026-04-01")]);
    expect(slot1).toHaveLength(2);
    expect(slot2).toHaveLength(0);
  });

  it("puts an overlapping referral in slot 2", () => {
    const { slot1, slot2 } = packIntoSlots([extent("2026-01-01", "2026-04-01"), extent("2026-02-01", "2026-05-01")]);
    expect(slot1).toHaveLength(1);
    expect(slot2).toHaveLength(1);
  });

  it("flags a third overlapping referral rather than dropping it", () => {
    const { slot2, overflow } = packIntoSlots([
      extent("2026-01-01", "2026-06-01"),
      extent("2026-01-05", "2026-06-01"),
      extent("2026-01-10", "2026-06-01"),
    ]);
    expect(overflow).toHaveLength(1);
    expect(slot2).toHaveLength(2);
  });
});

describe("assignRows", () => {
  const extent = (start: string, end: string) => {
    const from = parseDateOnly(start);
    const to = parseDateOnly(end);
    return {
      referral: makeReferral({ initiated_date: start }),
      start: from,
      end: to,
      isOpenEnded: false,
      // Same rule the layout applies: a zero-length bar still occupies its day.
      packEnd: to > from ? to : new Date(from.getTime() + 86_400_000),
    };
  };

  it("keeps sequential bars on one row", () => {
    const rows = assignRows([extent("2026-01-01", "2026-02-01"), extent("2026-03-01", "2026-04-01")]);
    expect(rows.map((r) => r.row)).toEqual([0, 0]);
  });

  it("stacks overlapping bars rather than letting one hide the other", () => {
    // The Exempt track has no cap, so two concurrent Complementary Service
    // referrals genuinely can overlap.
    const rows = assignRows([extent("2026-01-01", "2026-04-01"), extent("2026-02-01", "2026-05-01")]);
    expect(rows.map((r) => r.row)).toEqual([0, 1]);
  });

  it("reuses a row once its bar has ended", () => {
    const rows = assignRows([
      extent("2026-01-01", "2026-04-01"),
      extent("2026-02-01", "2026-03-01"),
      extent("2026-05-01", "2026-06-01"),
    ]);
    expect(rows.map((r) => r.row)).toEqual([0, 1, 0]);
  });
});

describe("chooseTickKind", () => {
  it("scales the axis to the span rather than always showing months", () => {
    // The bug this replaces: a month-only axis on a two-week case showed one
    // label, so nothing could be read relative to anything else.
    expect(chooseTickKind(10)).toBe("day");
    expect(chooseTickKind(60)).toBe("week");
    expect(chooseTickKind(400)).toBe("month");
    expect(chooseTickKind(2000)).toBe("quarter");
  });
});

describe("buildTimelineLayout", () => {
  it("returns an empty layout for a case with no referrals", () => {
    const layout = buildTimelineLayout([], { today: TODAY });
    expect(layout.isEmpty).toBe(true);
    expect(layout.tracks).toEqual([]);
  });

  it("always renders the three tracks in slot order", () => {
    const layout = buildTimelineLayout([makeReferral({ id: "r1" })], { today: TODAY });
    expect(layout.tracks.map((track) => track.label)).toEqual(["Slot 1", "Slot 2", "Exempt"]);
  });

  it("gives a short case a day-by-day axis with more than one label", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2026-03-02", outcome_date: "2026-03-06" })],
      { today: new Date(2026, 2, 6) },
    );
    expect(layout.tickKind).toBe("day");
    expect(layout.ticks.length).toBeGreaterThan(3);
  });

  it("sizes bars by duration, so a long referral is wider than a short one", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "short", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-01-06" }),
        makeReferral({ id: "long", status: "COMPLETED", initiated_date: "2026-02-01", outcome_date: "2026-05-01" }),
      ],
      { today: new Date(2026, 4, 1) },
    );
    const bars = layout.tracks.flatMap((t) => t.bars);
    const short = bars.find((b) => b.referral.id === "short")!;
    const long = bars.find((b) => b.referral.id === "long")!;
    expect(long.width).toBeGreaterThan(short.width * 10);
  });

  it("runs an open referral's bar to today and marks it open-ended", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ id: "r1", status: "ACTIVE", initiated_date: "2026-06-15" })],
      { today: TODAY },
    );
    const bar = layout.tracks[0].bars[0];
    expect(bar.isOpenEnded).toBe(true);
    expect(bar.end).toEqual(TODAY);
    expect(bar.width).toBeGreaterThan(0);
  });

  it("pads the domain by days rather than to whole months", () => {
    // Whole-month padding made a five-day case occupy a twentieth of the width,
    // which is what collapsed every bar to its minimum.
    const layout = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2026-03-10", outcome_date: "2026-03-15" })],
      { today: new Date(2026, 2, 15) },
    );
    const spanDays = (layout.domain[1].getTime() - layout.domain[0].getTime()) / 86_400_000;
    expect(spanDays).toBeLessThan(10);
  });

  it("keeps an exempt referral out of the slots entirely", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "training", status: "ACTIVE", initiated_date: "2026-01-05" }),
        makeReferral({
          id: "health",
          status: "ACTIVE",
          initiated_date: "2026-01-06",
          counts_toward_parallel_cap: false,
        }),
      ],
      { today: TODAY },
    );
    const [slot1, slot2, exempt] = layout.tracks;
    expect(slot1.bars.map((b) => b.referral.id)).toEqual(["training"]);
    expect(slot2.bars).toEqual([]);
    expect(exempt.bars.map((b) => b.referral.id)).toEqual(["health"]);
  });

  it("does not pile same-day referrals on top of each other", () => {
    // Zero-length intervals do not overlap by date arithmetic, but every one is
    // drawn at the same position and floored to the same minimum width, so all
    // but the last would be invisible on one row.
    const sameDay = ["a", "b", "c"].map((id) =>
      makeReferral({ id, status: "COMPLETED", initiated_date: "2026-08-16", outcome_date: "2026-08-16" }),
    );
    const layout = buildTimelineLayout(sameDay, { today: new Date(2026, 7, 16) });

    const seats = layout.tracks.flatMap((track) => track.bars.map((bar) => `${bar.track}:${bar.row}`));
    expect(new Set(seats).size).toBe(3);
  });

  it("reports how many rows a track needs when its bars overlap", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "a", status: "ACTIVE", initiated_date: "2026-01-05", counts_toward_parallel_cap: false }),
        makeReferral({ id: "b", status: "ACTIVE", initiated_date: "2026-02-05", counts_toward_parallel_cap: false }),
      ],
      { today: TODAY },
    );
    const exempt = layout.tracks[2];
    expect(exempt.rowCount).toBe(2);
    expect(exempt.bars.map((b) => b.row)).toEqual([0, 1]);
  });

  it("links a referral to the one it replaced", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "r1", status: "REPLACED", initiated_date: "2026-01-05", failure_date: "2026-02-01" }),
        makeReferral({
          id: "r2",
          initiated_date: "2026-02-03",
          parent_referral: "r1",
          referral_trigger: "REPLACEMENT",
        }),
      ],
      { today: TODAY },
    );
    expect(layout.links).toEqual([{ fromId: "r1", toId: "r2", kind: "replacement" }]);
  });

  it("links every hop of an onward chain", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-01" }),
        makeReferral({
          id: "r2",
          status: "COMPLETED",
          initiated_date: "2026-02-05",
          outcome_date: "2026-03-01",
          parent_referral: "r1",
          referral_trigger: "ONWARD",
        }),
        makeReferral({
          id: "r3",
          status: "ACTIVE",
          initiated_date: "2026-03-05",
          parent_referral: "r2",
          referral_trigger: "ONWARD",
        }),
      ],
      { today: TODAY },
    );
    expect(layout.links.map((l) => [l.fromId, l.toId, l.kind])).toEqual([
      ["r1", "r2", "onward"],
      ["r2", "r3", "onward"],
    ]);
  });

  it("skips a link whose parent is not in the set handed to the component", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ id: "r2", parent_referral: "missing", referral_trigger: "ONWARD" })],
      { today: TODAY },
    );
    expect(layout.links).toEqual([]);
  });

  it("skips a link for a manual referral that somehow carries a parent", () => {
    const layout = buildTimelineLayout(
      [
        makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-01" }),
        makeReferral({ id: "r2", initiated_date: "2026-02-05", parent_referral: "r1", referral_trigger: "MANUAL" }),
      ],
      { today: TODAY },
    );
    expect(layout.links).toEqual([]);
  });

  it("never draws a bar backwards when an outcome date precedes initiation", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2026-03-01", outcome_date: "2026-02-01" })],
      { today: TODAY },
    );
    const bar = layout.tracks[0].bars[0];
    expect(bar.end.getTime()).toBeGreaterThanOrEqual(bar.start.getTime());
  });

  it("names the year, and both years when the case crosses one", () => {
    expect(buildTimelineLayout([makeReferral({ initiated_date: "2026-02-01" })], { today: TODAY }).yearLabel).toBe(
      "2026",
    );
    const across = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2025-11-01", outcome_date: "2026-02-01" })],
      { today: new Date(2026, 1, 1) },
    );
    expect(across.yearLabel).toBe("2025–2026");
  });
});

describe("labels", () => {
  it("names both ends of a closed referral", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2026-01-12", outcome_date: "2026-04-30" })],
      { today: TODAY },
    );
    expect(periodLabel(layout.tracks[0].bars[0])).toBe("12 Jan 2026 – 30 Apr 2026");
  });

  it("says ongoing rather than inventing an end date", () => {
    const layout = buildTimelineLayout([makeReferral({ status: "ACTIVE", initiated_date: "2026-01-12" })], {
      today: TODAY,
    });
    expect(periodLabel(layout.tracks[0].bars[0])).toBe("12 Jan 2026 – ongoing");
  });

  it("counts a same-day referral as one day, not zero", () => {
    const layout = buildTimelineLayout(
      [makeReferral({ status: "COMPLETED", initiated_date: "2026-01-12", outcome_date: "2026-01-12" })],
      { today: new Date(2026, 0, 12) },
    );
    expect(durationDays(layout.tracks[0].bars[0])).toBe(1);
  });
});
