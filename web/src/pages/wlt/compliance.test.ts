import { describe, expect, it } from "vitest";

import type { GateCondition, WltMemberSavingsCompliance } from "../../api/types";
import { BAND_STYLE, bandFor, FALLBACK_THRESHOLD, summarise, thresholdFrom } from "./compliance";

function member(over: Partial<WltMemberSavingsCompliance> = {}): WltMemberSavingsCompliance {
  return {
    person_id: "p1",
    full_name: "Chaltu Bekele",
    meetings_met: 8,
    meetings_expected: 10,
    compliance_pct: "80",
    is_compliant: true,
    is_current: true,
    ...over,
  };
}

function condition(threshold: unknown): GateCondition {
  return {
    code: "savings_compliance",
    label: "Savings compliance",
    threshold: threshold as never,
    actual: 55 as never,
    met: false,
    unmeasurable: false,
    unit: "",
  };
}

describe("thresholdFrom", () => {
  it("reads the group's own gate rather than a constant", () => {
    // `gate.p1.savings_compliance_pct` is effective-dated and geography-scoped
    // and currently reads 80, not the 90 in some copy. Banding against a bar
    // the group is not judged on would make the card and the tile disagree.
    expect(thresholdFrom([condition(80)])).toBe(80);
    expect(thresholdFrom([condition(90)])).toBe(90);
  });

  it("falls back only when there is no gate to read", () => {
    expect(thresholdFrom(undefined)).toBe(FALLBACK_THRESHOLD);
    expect(thresholdFrom([])).toBe(FALLBACK_THRESHOLD);
  });

  it("ignores a threshold that is not a usable number", () => {
    expect(thresholdFrom([condition("n/a")])).toBe(FALLBACK_THRESHOLD);
    expect(thresholdFrom([condition(0)])).toBe(FALLBACK_THRESHOLD);
  });
});

describe("bandFor", () => {
  it("bands against the threshold it is given, not a fixed number", () => {
    expect(bandFor(85, 80)).toBe("compliant");
    expect(bandFor(85, 90)).toBe("watch");
  });

  it("puts the bar itself in compliant", () => {
    expect(bandFor(80, 80)).toBe("compliant");
  });

  it("separates a near miss from a real problem", () => {
    // 78 on an 80 bar and 30 on an 80 bar call for different conversations;
    // one "not compliant" label would send a facilitator to both alike.
    expect(bandFor(78, 80)).toBe("watch");
    expect(bandFor(30, 80)).toBe("at-risk");
  });

  it("moves the watch floor with the threshold", () => {
    expect(bandFor(81, 90)).toBe("watch");
    expect(bandFor(80, 90)).toBe("at-risk");
  });

  it("has no band for a member with nothing recorded", () => {
    expect(bandFor(null, 80)).toBeNull();
  });
});

describe("summarise", () => {
  it("counts only current members", () => {
    // A former member is not somebody to chase.
    const summary = summarise(
      [member({ compliance_pct: "20" }), member({ person_id: "p2", compliance_pct: "10", is_current: false })],
      80,
    );
    expect(summary.counted).toBe(1);
    expect(summary.lowest).toHaveLength(1);
  });

  it("counts nothing-recorded apart from zero", () => {
    // "Not yet asked" and "asked and saved nothing" are different findings and
    // only one of them is a compliance problem.
    const summary = summarise(
      [member({ compliance_pct: null }), member({ person_id: "p2", compliance_pct: "0" })],
      80,
    );
    expect(summary.unmeasured).toBe(1);
    expect(summary.counted).toBe(1);
    expect(summary.atRisk).toBe(1);
  });

  it("ranks the worst first, which is the point of the card", () => {
    const summary = summarise(
      [
        member({ person_id: "a", full_name: "A", compliance_pct: "95" }),
        member({ person_id: "b", full_name: "B", compliance_pct: "20" }),
        member({ person_id: "c", full_name: "C", compliance_pct: "60" }),
      ],
      80,
    );
    expect(summary.lowest.map((row) => row.full_name)).toEqual(["B", "C"]);
    expect(summary.compliant).toBe(1);
    expect(summary.belowThreshold).toBe(2);
  });

  it("caps the follow-up list without hiding the count", () => {
    const many = Array.from({ length: 9 }, (_, i) =>
      member({ person_id: `p${i}`, full_name: `M${i}`, compliance_pct: String(i * 5) }),
    );
    const summary = summarise(many, 80, 4);

    expect(summary.lowest).toHaveLength(4);
    // The card says "9 members below 80%" even though it lists four.
    expect(summary.belowThreshold).toBe(9);
  });

  it("reports an all-compliant group as having nobody to chase", () => {
    const summary = summarise([member({ compliance_pct: "100" })], 80);
    expect(summary.belowThreshold).toBe(0);
    expect(summary.lowest).toEqual([]);
  });
});

describe("band styling", () => {
  it("never relies on colour alone", () => {
    for (const style of Object.values(BAND_STYLE)) {
      expect(style.label.length).toBeGreaterThan(0);
    }
  });

  it("takes every colour from a token", () => {
    for (const style of Object.values(BAND_STYLE)) {
      expect(style.fg).toMatch(/^var\(--/);
      expect(style.fill).toMatch(/^var\(--/);
    }
  });
});
