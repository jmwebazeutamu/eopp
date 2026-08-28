import { describe, expect, it } from "vitest";

import { ABSENT, groupSizeRange, phaseRail, statStrip, type Parameters } from "./landingFacts";

/** The seeded defaults, as `GET /wlt/public-parameters/` returns them. */
const SEEDED: Parameters = {
  "group.size.hard_min": 15,
  "group.size.hard_max": 25,
  "gate.cla.min_groups": 8,
  "gate.cla.delegates_per_group": 2,
  "gate.federation.min_clas": 10,
  "gate.federation.min_cla_months": 12,
  "gate.p1.meeting_adherence_pct": 90,
  "gate.p1.attendance_pct": 80,
  "gate.p1.savings_compliance_pct": 80,
  "gate.p1.min_savings_meetings": 10,
  "gate.p1.max_par30_pct": 0,
  "gate.p2.fund_adequacy_weeks": 12,
  "gate.p2.completed_loan_cycles": 1,
  "gate.p2.max_par30_pct": 0,
  "gate.p2.min_weeks_since_p1": 52,
};

/** Echoes the key and its variables, so a test reads the wiring not the copy. */
const t = ((key: string, vars?: Record<string, string | number>) =>
  vars ? `${key}(${Object.entries(vars).map(([k, v]) => `${k}=${v}`).join(",")})` : key) as never;

describe("groupSizeRange", () => {
  it("joins the two ends of the rule with an en dash", () => {
    expect(groupSizeRange(SEEDED)).toBe("15–25");
  });

  it("says nothing rather than something wrong when a parameter is missing", () => {
    // The standing rule across this platform: absent is not zero. "0–25" on a
    // public page would state a group size the programme has never allowed.
    expect(groupSizeRange({ "group.size.hard_max": 25 })).toBe(ABSENT);
    expect(groupSizeRange({})).toBe(ABSENT);
  });
});

describe("statStrip", () => {
  it("reads all three structural figures from the parameters", () => {
    const [size, cla, federation] = statStrip(SEEDED, 12);
    expect(size.value).toBe("15–25");
    expect(cla.value).toBe("8");
    expect(federation.value).toBe("10");
  });

  it("moves when the programme moves the parameter", () => {
    // The whole reason the page fetches these rather than printing them. The
    // handbook disputes the CLA threshold between 6 and 8, so this will happen.
    const strip = statStrip({ ...SEEDED, "gate.cla.min_groups": 6 }, 12);
    expect(strip.find((s) => s.key === "cla")?.value).toBe("6");
  });

  it("carries the linkage state count it is given, not a figure of its own", () => {
    // The mock's "33 linkage steps" is traceable to nothing. This one is
    // `LinkageStatus`, counted at the call site off the tone table.
    expect(statStrip(SEEDED, 12).find((s) => s.key === "linkage")?.value).toBe("12");
  });

  it("renders an empty payload as dashes, never as zeroes", () => {
    expect(statStrip({}, 12).map((s) => s.value)).toEqual([ABSENT, ABSENT, ABSENT, "12"]);
  });
});

describe("phaseRail", () => {
  it("states every condition DEFINITIONS.md §2 lists for Phase 1", () => {
    // The mock abridges this list to three pills and drops savings compliance,
    // under a heading promising "when they are all met". The spec wins.
    const p1 = phaseRail(SEEDED, t).find((step) => step.key === "p1");
    const keys = p1?.conditions.map((c) => c.text.split("(")[0]);
    expect(keys).toEqual([
      "landing.condAdherence",
      "landing.condAttendance",
      "landing.condSavings",
      "landing.condMeetings",
      "landing.condPar30",
    ]);
  });

  it("keeps Phase 2's social fund and its 52-week minimum", () => {
    const p2 = phaseRail(SEEDED, t).find((step) => step.key === "p2");
    const texts = p2?.conditions.map((c) => c.text) ?? [];
    expect(texts).toContain("landing.condSocialFund");
    expect(texts).toContain("landing.condSincePhaseOne(weeks=52)");
  });

  it("keeps the constitution on both structural gates", () => {
    const rail = phaseRail(SEEDED, t);
    expect(rail.find((s) => s.key === "cla")?.conditions.map((c) => c.text)).toContain(
      "landing.condClaConstitution",
    );
    expect(rail.find((s) => s.key === "federation")?.conditions.map((c) => c.text)).toContain(
      "landing.condFederationConstitution",
    );
  });

  it("passes every threshold in as a variable rather than baking it into copy", () => {
    const rail = phaseRail(SEEDED, t);
    const all = rail.flatMap((step) => step.conditions.map((c) => c.text));
    expect(all).toContain("landing.condAdherence(pct=90)");
    expect(all).toContain("landing.condFund(weeks=12)");
    expect(all).toContain("landing.condEligibleGroups(n=8)");
    expect(all).toContain("landing.condMinClas(n=10)");
    expect(all).toContain("landing.condClaMonths(n=12)");
  });

  it("reports a missing threshold as a dash inside the pill", () => {
    // Not "Adherence ≥0%", which is a rule nobody wrote and everybody passes.
    const rail = phaseRail({}, t);
    const p1 = rail.find((step) => step.key === "p1");
    expect(p1?.conditions[0].text).toBe(`landing.condAdherence(pct=${ABSENT})`);
  });

  it("only ever tones a pill whose words already carry the meaning", () => {
    // "Never colour alone". Every toned pill is PAR30 or woreda approval, both
    // of which say so in text.
    const toned = phaseRail(SEEDED, t)
      .flatMap((step) => step.conditions)
      .filter((c) => c.tone);
    expect(toned.length).toBeGreaterThan(0);
    for (const condition of toned) {
      expect(condition.text).toMatch(/condPar30|condWoredaApproval/);
    }
  });
});
