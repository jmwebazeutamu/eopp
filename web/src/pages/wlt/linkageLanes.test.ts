import { describe, expect, it } from "vitest";

import type { ServiceLinkage } from "../../api/types";
import { buildLanes, eventDate } from "./linkageLanes";

function linkage(over: Partial<ServiceLinkage> = {}): ServiceLinkage {
  return {
    id: "l1",
    linkage_type: "savings_account",
    type_label: "Group savings account",
    provider: "p1",
    provider_name: "Amhara Rural Bank",
    predecessor: null,
    predecessor_label: null,
    subject_group: "g1",
    subject_cla: null,
    subject_federation: null,
    subject_type: "GROUP",
    subject_name: "Adey SHG",
    status: "APPROVED",
    status_display: "Approved",
    opened_on: "2026-08-20",
    approved_on: null,
    activated_on: null,
    closed_on: null,
    value_etb: null,
    terms: {},
    guarantors: [],
    block_reasons: [],
    next_approval_role: null,
    next_action_role_display: null,
    can_current_user_approve: false,
    ...over,
  };
}

describe("eventDate", () => {
  it("uses the most recent thing that actually happened", () => {
    // A lane parked at its opening date reads as stale work nobody has touched.
    expect(eventDate(linkage({ opened_on: "2026-03-01", activated_on: "2026-08-01" }))).toBe("2026-08-01");
    expect(eventDate(linkage({ opened_on: "2026-03-01", approved_on: "2026-05-01" }))).toBe("2026-05-01");
    expect(
      eventDate(linkage({ opened_on: "2026-03-01", activated_on: "2026-05-01", closed_on: "2026-09-01" })),
    ).toBe("2026-09-01");
  });

  it("falls back to the opening date when nothing else has happened", () => {
    expect(eventDate(linkage())).toBe("2026-08-20");
  });
});

describe("buildLanes", () => {
  it("gives every linkage its own labelled lane", () => {
    const layout = buildLanes([
      linkage({ id: "a", type_label: "Group savings account" }),
      linkage({ id: "b", type_label: "Market or offtake agreement", opened_on: "2026-08-21" }),
    ]);

    expect(layout.lanes.map((lane) => lane.label)).toEqual([
      "Group savings account",
      "Market or offtake agreement",
    ]);
    expect(layout.lanes[0].partner).toBe("Amhara Rural Bank");
  });

  it("keeps every marker inside the plotting area", () => {
    // The fault this replaces: labels ran past the right edge.
    const layout = buildLanes([
      linkage({ id: "a", opened_on: "2026-08-20" }),
      linkage({ id: "b", opened_on: "2026-08-25" }),
    ]);

    for (const lane of layout.lanes) {
      expect(lane.position).toBeGreaterThanOrEqual(0);
      expect(lane.position).toBeLessThanOrEqual(1);
    }
  });

  it("anchors a marker at the edges rather than letting it hang off", () => {
    const layout = buildLanes([
      linkage({ id: "a", opened_on: "2026-08-01" }),
      linkage({ id: "b", opened_on: "2026-08-31" }),
    ]);

    expect(layout.lanes[0].anchor).toBe("start");
    expect(layout.lanes[1].anchor).toBe("end");
  });

  it("centres a marker with room on both sides", () => {
    const layout = buildLanes([
      linkage({ id: "a", opened_on: "2026-08-01" }),
      linkage({ id: "b", opened_on: "2026-08-15" }),
      linkage({ id: "c", opened_on: "2026-08-31" }),
    ]);
    expect(layout.lanes[1].anchor).toBe("middle");
  });

  it("pads a single-day range instead of dividing by zero", () => {
    // Three linkages all opened the same day is ordinary, not an edge case.
    const layout = buildLanes([
      linkage({ id: "a" }),
      linkage({ id: "b" }),
      linkage({ id: "c" }),
    ]);

    expect(layout.axis.singleDay).toBe(true);
    expect(layout.axis.from).not.toBe(layout.axis.to);
    for (const lane of layout.lanes) {
      expect(Number.isFinite(lane.position)).toBe(true);
      expect(lane.position).toBeGreaterThan(0);
      expect(lane.position).toBeLessThan(1);
    }
  });

  it("never prints the same tick date twice", () => {
    // A five-tick axis over three days repeats a date and reads as a fault.
    const layout = buildLanes([
      linkage({ id: "a", opened_on: "2026-08-20" }),
      linkage({ id: "b", opened_on: "2026-08-21" }),
    ]);

    const dates = layout.axis.ticks.map((tick) => tick.date);
    expect(new Set(dates).size).toBe(dates.length);
  });

  it("keeps five ticks when the range is wide enough", () => {
    const layout = buildLanes([
      linkage({ id: "a", opened_on: "2026-01-01" }),
      linkage({ id: "b", opened_on: "2026-12-31" }),
    ]);
    expect(layout.axis.ticks).toHaveLength(5);
    expect(layout.axis.ticks[0].position).toBe(0);
    expect(layout.axis.ticks[4].position).toBe(1);
  });

  it("marks a blocked linkage so the lane can say what is missing", () => {
    const layout = buildLanes([
      linkage({ id: "a", status: "BLOCKED", block_reasons: ["Needs Phase 2"] }),
      linkage({ id: "b" }),
    ]);
    expect(layout.lanes[0].blocked).toBe(true);
    expect(layout.lanes[1].blocked).toBe(false);
  });

  it("returns an empty layout rather than throwing", () => {
    const layout = buildLanes([]);
    expect(layout.lanes).toEqual([]);
    expect(layout.axis.ticks).toEqual([]);
  });
});
