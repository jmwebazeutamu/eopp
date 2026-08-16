import { describe, expect, it } from "vitest";

import { makeReferral } from "../../test/referralFactory";
import {
  assignLanes,
  barEnd,
  buildTicks,
  buildTimelineLayout,
  chooseTickKind,
  parseDateOnly,
} from "./timelineLayout";

/**
 * The acceptance criteria in docs/REFERRAL_STACK_TIMELINE_COMPONENT_PROMPT.md,
 * tested against the layout rather than against pixels: lane assignment,
 * parallel grouping and dependency arrows are the logic that can be silently
 * wrong, and none of it needs a DOM.
 */

const TODAY = new Date(2026, 5, 30); // 30 June 2026

describe("parseDateOnly", () => {
  it("reads an API date as local midnight, not UTC", () => {
    const parsed = parseDateOnly("2026-03-05");
    expect(parsed.getFullYear()).toBe(2026);
    expect(parsed.getMonth()).toBe(2);
    expect(parsed.getDate()).toBe(5);
    expect(parsed.getHours()).toBe(0);
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
    const { end, isOpenEnded } = barEnd(
      makeReferral({ status: "COMPLETED", outcome_date: "2026-03-10" }),
      TODAY,
    );
    expect(end).toEqual(new Date(2026, 2, 10));
    expect(isOpenEnded).toBe(false);
  });

  it("closes a failed referral on failure_date, which is the field the API stamps", () => {
    // §6.2 sets failure_date on Failed and outcome_date on Completed; a bar that
    // only read outcome_date would run every failure to today.
    const { end } = barEnd(makeReferral({ status: "FAILED", failure_date: "2026-02-20" }), TODAY);
    expect(end).toEqual(new Date(2026, 1, 20));
  });

  it("closes a replaced referral on the failure date it inherited", () => {
    const { end } = barEnd(makeReferral({ status: "REPLACED", failure_date: "2026-02-20" }), TODAY);
    expect(end).toEqual(new Date(2026, 1, 20));
  });

  it("closes a cancelled referral at updated_at, since §6.2 stamps no date for it", () => {
    const { end } = barEnd(
      makeReferral({ status: "CANCELLED", updated_at: "2026-02-02T14:30:00+03:00" }),
      TODAY,
    );
    expect(end.getFullYear()).toBe(2026);
    expect(end.getMonth()).toBe(1);
    expect(end.getDate()).toBe(2);
  });
});

describe("assignLanes", () => {
  it("orders by initiation date", () => {
    const later = makeReferral({ id: "b", initiated_date: "2026-03-01" });
    const earlier = makeReferral({ id: "a", initiated_date: "2026-01-01" });
    expect(assignLanes([later, earlier]).map((r) => r.id)).toEqual(["a", "b"]);
  });

  it("breaks ties on id so the order does not shift between renders", () => {
    const one = makeReferral({ id: "zzz", initiated_date: "2026-01-01" });
    const two = makeReferral({ id: "aaa", initiated_date: "2026-01-01" });
    expect(assignLanes([one, two]).map((r) => r.id)).toEqual(["aaa", "zzz"]);
    expect(assignLanes([two, one]).map((r) => r.id)).toEqual(["aaa", "zzz"]);
  });

  it("keeps a parallel group adjacent even when another referral falls between them by date", () => {
    const first = makeReferral({ id: "p1", initiated_date: "2026-01-01", parallel_group_id: "g1" });
    const interloper = makeReferral({ id: "solo", initiated_date: "2026-01-05" });
    const second = makeReferral({ id: "p2", initiated_date: "2026-01-10", parallel_group_id: "g1" });

    expect(assignLanes([first, interloper, second]).map((r) => r.id)).toEqual(["p1", "p2", "solo"]);
  });
});

describe("chooseTickKind", () => {
  it("scales the axis to the span rather than hardcoding months", () => {
    expect(chooseTickKind(10)).toBe("day");
    expect(chooseTickKind(60)).toBe("week");
    expect(chooseTickKind(400)).toBe("month");
    expect(chooseTickKind(1000)).toBe("quarter");
    expect(chooseTickKind(3000)).toBe("year");
  });
});

describe("buildTicks", () => {
  it("labels monthly ticks and dates the first one", () => {
    const ticks = buildTicks([new Date(2026, 0, 15), new Date(2026, 4, 15)], "month");
    expect(ticks.map((t) => t.label)).toEqual(["Feb 2026", "Mar", "Apr", "May"]);
  });

  it("puts the year back on a January tick", () => {
    const ticks = buildTicks([new Date(2025, 10, 1), new Date(2026, 2, 1)], "month");
    expect(ticks.map((t) => t.label)).toEqual(["Nov 2025", "Dec", "Jan 2026", "Feb"]);
  });

  it("labels daily ticks with day and month", () => {
    const ticks = buildTicks([new Date(2026, 2, 3), new Date(2026, 2, 6)], "day");
    expect(ticks.map((t) => t.label)).toEqual(["3 Mar", "4 Mar", "5 Mar"]);
  });
});

// ---------------------------------------------------------------------------
// Acceptance criteria
// ---------------------------------------------------------------------------

describe("a single sequential chain", () => {
  const referrals = [
    makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-10" }),
    makeReferral({
      id: "r2",
      status: "ACTIVE",
      initiated_date: "2026-02-12",
      parent_referral: "r1",
      referral_trigger: "ONWARD",
    }),
  ];

  it("gives each referral its own lane in date order", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.laneCount).toBe(2);
    expect(layout.bars.map((b) => [b.referral.id, b.lane])).toEqual([
      ["r1", 0],
      ["r2", 1],
    ]);
  });

  it("draws one onward arrow and no brackets", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.brackets).toEqual([]);
    expect(layout.arrows).toHaveLength(1);
    expect(layout.arrows[0]).toMatchObject({ fromId: "r1", toId: "r2", kind: "onward", fromLane: 0, toLane: 1 });
  });

  it("ends the domain at today while a referral is still running", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.domain[0]).toEqual(new Date(2026, 0, 5));
    expect(layout.domain[1]).toEqual(TODAY);
  });
});

describe("two parallel active referrals", () => {
  const referrals = [
    makeReferral({ id: "p1", status: "ACTIVE", initiated_date: "2026-01-05", parallel_group_id: "g1" }),
    makeReferral({ id: "p2", status: "ACTIVE", initiated_date: "2026-01-06", parallel_group_id: "g1" }),
  ];

  it("brackets them across adjacent lanes instead of colouring them differently", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.brackets).toHaveLength(1);
    expect(layout.brackets[0]).toMatchObject({ groupId: "g1", firstLane: 0, lastLane: 1 });
    expect(layout.brackets[0].referralIds).toEqual(["p1", "p2"]);
  });

  it("leaves status free to say something else — a parallel referral can also fail", () => {
    const failed = [
      referrals[0],
      makeReferral({
        id: "p2",
        status: "FAILED",
        initiated_date: "2026-01-06",
        failure_date: "2026-02-01",
        parallel_group_id: "g1",
      }),
    ];
    const layout = buildTimelineLayout(failed, { today: TODAY });
    expect(layout.brackets).toHaveLength(1);
    expect(layout.bars[1].referral.status).toBe("FAILED");
    expect(layout.bars[1].isOpenEnded).toBe(false);
  });

  it("does not bracket a group whose sibling is not on screen", () => {
    const lone = [makeReferral({ id: "p1", parallel_group_id: "g1" })];
    expect(buildTimelineLayout(lone, { today: TODAY }).brackets).toEqual([]);
  });
});

describe("a failure followed by a replacement", () => {
  const referrals = [
    makeReferral({ id: "r1", status: "REPLACED", initiated_date: "2026-01-05", failure_date: "2026-02-01" }),
    makeReferral({
      id: "r2",
      status: "ACTIVE",
      initiated_date: "2026-02-03",
      parent_referral: "r1",
      referral_trigger: "REPLACEMENT",
    }),
  ];

  it("labels the arrow replacement and anchors it to the failure date", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.arrows).toHaveLength(1);
    expect(layout.arrows[0].kind).toBe("replacement");
    expect(layout.arrows[0].fromDate).toEqual(new Date(2026, 1, 1));
    expect(layout.arrows[0].toDate).toEqual(new Date(2026, 1, 3));
  });
});

describe("an onward chain of three hops", () => {
  const referrals = [
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
  ];

  it("draws an arrow per hop, each between adjacent lanes", () => {
    const layout = buildTimelineLayout(referrals, { today: TODAY });
    expect(layout.arrows.map((a) => [a.fromId, a.toId, a.kind])).toEqual([
      ["r1", "r2", "onward"],
      ["r2", "r3", "onward"],
    ]);
    expect(layout.laneCount).toBe(3);
  });
});

describe("edge cases", () => {
  it("handles a case with no referrals", () => {
    const layout = buildTimelineLayout([], { today: TODAY });
    expect(layout.bars).toEqual([]);
    expect(layout.laneCount).toBe(0);
    expect(layout.ticks).toEqual([]);
  });

  it("gives a single same-day referral a domain wide enough to scale", () => {
    const sameDay = [
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-01-05" }),
    ];
    const layout = buildTimelineLayout(sameDay, { today: new Date(2026, 0, 5) });
    expect(layout.domain[1].getTime()).toBeGreaterThan(layout.domain[0].getTime());
  });

  it("never draws a bar backwards when an outcome date precedes initiation", () => {
    // Both dates are hand-entered, so this ordering does reach the client.
    const odd = [
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-03-01", outcome_date: "2026-02-01" }),
    ];
    const layout = buildTimelineLayout(odd, { today: TODAY });
    expect(layout.bars[0].end.getTime()).toBeGreaterThanOrEqual(layout.bars[0].start.getTime());
  });

  it("skips an arrow whose parent is not in the set handed to the component", () => {
    const orphan = [
      makeReferral({ id: "r2", parent_referral: "missing", referral_trigger: "ONWARD" }),
    ];
    expect(buildTimelineLayout(orphan, { today: TODAY }).arrows).toEqual([]);
  });

  it("skips an arrow for a manual referral that somehow carries a parent", () => {
    const referrals = [
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-01" }),
      makeReferral({ id: "r2", initiated_date: "2026-02-05", parent_referral: "r1", referral_trigger: "MANUAL" }),
    ];
    expect(buildTimelineLayout(referrals, { today: TODAY }).arrows).toEqual([]);
  });

  it("ends the domain at the last outcome when every referral has closed", () => {
    const closed = [
      makeReferral({ id: "r1", status: "COMPLETED", initiated_date: "2026-01-05", outcome_date: "2026-02-10" }),
      makeReferral({ id: "r2", status: "FAILED", initiated_date: "2026-01-06", failure_date: "2026-03-15" }),
    ];
    const layout = buildTimelineLayout(closed, { today: TODAY });
    expect(layout.domain[1]).toEqual(new Date(2026, 2, 15));
  });
});
