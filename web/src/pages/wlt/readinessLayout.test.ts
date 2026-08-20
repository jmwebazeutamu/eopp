import { describe, expect, it } from "vitest";

import type { GateCondition, GateResult } from "../../api/types";
import { conditionLine, freshness, summarise } from "./readinessLayout";

function condition(overrides: Partial<GateCondition> = {}): GateCondition {
  return {
    code: "attendance",
    label: "Attendance",
    threshold: 80,
    actual: "74.0",
    met: false,
    unmeasurable: false,
    unit: "%",
    ...overrides,
  };
}

function gate(conditions: GateCondition[]): GateResult {
  return {
    gate_set: "p1_to_p2",
    passed: conditions.every((item) => item.met),
    conditions,
    policy_version_id: "v1",
    computed_at: "2026-08-20T09:00:00Z",
  };
}

describe("conditionLine", () => {
  it("keeps the actual value next to the threshold", () => {
    // The rule the readiness card exists for. A line that said only "below
    // threshold" would tell a facilitator she failed and nothing else.
    const line = conditionLine(condition());
    expect(line.sentence).toBe("Attendance: 74.0% (need 80%)");
    expect(line.actual).toBe("74.0%");
    expect(line.threshold).toBe("80%");
  });

  it("separates not-measurable-yet from below-the-threshold", () => {
    // Different instructions: one means hold more meetings, the other means
    // the group has none to measure. Rendering both in red gave the wrong one.
    const line = conditionLine(condition({ actual: null, unmeasurable: true }));
    expect(line.state).toBe("unmeasurable");
    expect(line.sentence).toBe("Attendance: not measurable yet (need 80%)");
  });

  it("renders a boolean condition as yes or no rather than true or false", () => {
    const line = conditionLine(
      condition({ code: "social_fund", label: "Social fund active", threshold: true, actual: false, unit: "" })
    );
    expect(line.sentence).toBe("Social fund active: no (need yes)");
  });

  it("marks a met condition as met", () => {
    expect(conditionLine(condition({ actual: "92.0", met: true })).state).toBe("met");
  });
});

describe("summarise", () => {
  it("counts what is met and lists what is outstanding", () => {
    const summary = summarise(
      gate([
        condition({ code: "a", actual: "92.0", met: true }),
        condition({ code: "b" }),
        condition({ code: "c", actual: null, unmeasurable: true }),
      ])
    );
    expect(summary?.met).toBe(1);
    expect(summary?.total).toBe(3);
    expect(summary?.outstanding.map((line) => line.code)).toEqual(["b", "c"]);
  });

  it("puts what the group can act on above what it cannot yet measure", () => {
    // A short condition is this month's work; an unmeasurable one usually just
    // means "keep meeting". The actionable ones belong at the top.
    const summary = summarise(
      gate([
        condition({ code: "unmeasurable-one", actual: null, unmeasurable: true }),
        condition({ code: "short-one" }),
      ])
    );
    expect(summary?.outstanding[0].code).toBe("short-one");
  });

  it("returns nothing when there is no gate to read", () => {
    expect(summarise(null)).toBeNull();
  });
});

describe("freshness", () => {
  it("says nothing when the card was computed today", () => {
    expect(freshness("2026-08-20T09:00:00Z", "2026-08-20")).toBeNull();
  });

  it("stamps its age when it was not", () => {
    // A stale card that is honest about its age beats a fresh one that is
    // wrong — the handoff's rule for reading offline from the last sync.
    expect(freshness("2026-08-14T09:00:00Z", "2026-08-20")).toBe("As at 2026-08-14");
  });
});
