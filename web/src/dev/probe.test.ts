import { describe, expect, it } from "vitest";

import { classify, groupResults, PROBES, refine, rowCount, summarise, VERDICT_STYLE, type ProbeResult } from "./probe";

const result = (over: Partial<ProbeResult> = {}): ProbeResult => ({
  label: "Cases",
  path: "/cases/",
  group: "Youth side",
  status: 200,
  verdict: "allowed",
  count: 3,
  ...over,
});

describe("classify", () => {
  it("keeps 403 and 404 apart", () => {
    // The distinction is load-bearing: CLAUDE.md's rule is that an out-of-scope
    // record 404s, so a 404 against a *list* endpoint means the route is not
    // mounted — a finding, not a permission.
    expect(classify(403)).toBe("refused");
    expect(classify(404)).toBe("absent");
  });

  it("names an expired session rather than calling it a refusal", () => {
    expect(classify(401)).toBe("unauthenticated");
  });

  it("falls back to error for anything unexpected", () => {
    expect(classify(500)).toBe("error");
    expect(classify(502)).toBe("error");
  });
});

describe("rowCount", () => {
  it("reads a paginated envelope", () => {
    expect(rowCount({ count: 42, results: [] })).toBe(42);
  });

  it("reads a bare list", () => {
    expect(rowCount([1, 2, 3])).toBe(3);
  });

  it("prefers count over the length of the page", () => {
    // The page is 20 rows of 435; reporting 20 would misdescribe the scope.
    expect(rowCount({ count: 435, results: new Array(20).fill(null) })).toBe(435);
  });

  it("returns null for a shape that is not a list", () => {
    // A dashboard tier returns an object of figures. Zero would read as an
    // empty programme rather than as "this endpoint has no rows".
    expect(rowCount({ registered: { value: 12 } })).toBeNull();
    expect(rowCount(null)).toBeNull();
    expect(rowCount("nope")).toBeNull();
  });
});

describe("refine", () => {
  it("separates allowed-and-empty from allowed", () => {
    // The distinction the tool exists for: partner staff get an empty case
    // list rather than a refusal, because CaseViewSet declares no
    // partner_field. Both rendered as "no access" would hide that.
    expect(refine("allowed", 0)).toBe("empty");
    expect(refine("allowed", 5)).toBe("allowed");
  });

  it("leaves a null count alone", () => {
    // Not a list — "empty" would be a claim about rows that do not exist here.
    expect(refine("allowed", null)).toBe("allowed");
  });

  it("never upgrades a refusal", () => {
    expect(refine("refused", 0)).toBe("refused");
    expect(refine("absent", 0)).toBe("absent");
  });
});

describe("summarise", () => {
  it("counts by verdict in a fixed order", () => {
    const summary = summarise([
      result({ verdict: "refused" }),
      result({ verdict: "allowed" }),
      result({ verdict: "refused" }),
      result({ verdict: "empty" }),
    ]);

    expect(summary).toEqual([
      { verdict: "allowed", count: 1 },
      { verdict: "empty", count: 1 },
      { verdict: "refused", count: 2 },
    ]);
  });

  it("drops verdicts that did not occur", () => {
    expect(summarise([result()]).map((s) => s.verdict)).toEqual(["allowed"]);
  });

  it("is stable across runs with the same verdicts in a different order", () => {
    const a = summarise([result({ verdict: "refused" }), result({ verdict: "allowed" })]);
    const b = summarise([result({ verdict: "allowed" }), result({ verdict: "refused" })]);
    expect(a).toEqual(b);
  });
});

describe("groupResults", () => {
  it("groups in declaration order and drops nothing", () => {
    const grouped = groupResults([
      result({ group: "Youth side", label: "Cases" }),
      result({ group: "Dashboards", label: "Tier 1" }),
      result({ group: "Youth side", label: "Referrals" }),
    ]);

    expect(grouped.map((g) => g.group)).toEqual(["Youth side", "Dashboards"]);
    expect(grouped[0].results.map((r) => r.label)).toEqual(["Cases", "Referrals"]);
  });

  it("returns nothing for no results", () => {
    expect(groupResults([])).toEqual([]);
  });
});

describe("the probe list", () => {
  it("has no duplicate paths", () => {
    const paths = PROBES.map((p) => p.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it("gives every path a leading and trailing slash", () => {
    // DRF's APPEND_SLASH would redirect otherwise, and a 301 in the middle of
    // a probe reads as an error.
    for (const probe of PROBES) {
      expect(probe.path.startsWith("/")).toBe(true);
      expect(probe.path.endsWith("/")).toBe(true);
    }
  });

  it("covers every boundary the four-tier gate draws", () => {
    const paths = PROBES.map((p) => p.path);
    expect(paths).toContain("/dashboard/my-work/");
    expect(paths).toContain("/dashboard/woreda/");
    expect(paths).toContain("/dashboard/programme/");
    expect(paths).toContain("/dashboard/results/");
  });

  it("covers both sides of the WLT module boundary", () => {
    // The boundary is tested server-side on the same woman; the probe is how
    // you see it from the client without signing in twice.
    expect(PROBES.some((p) => p.group === "WLT group module")).toBe(true);
    expect(PROBES.some((p) => p.group === "Youth side")).toBe(true);
  });
});

describe("verdict styling", () => {
  it("never relies on colour alone", () => {
    // Design rule 2: colour plus a label plus a geometric mark.
    for (const style of Object.values(VERDICT_STYLE)) {
      expect(style.label.length).toBeGreaterThan(0);
      expect(style.mark.length).toBeGreaterThan(0);
    }
  });

  it("takes every colour from a token", () => {
    // Design rule 1: no literal hex outside design/status.ts and ANTD_THEME.
    for (const style of Object.values(VERDICT_STYLE)) {
      expect(style.fill).toMatch(/^var\(--/);
      expect(style.ink).toMatch(/^var\(--/);
    }
  });

  it("reserves red for genuine failure", () => {
    // Design rule 3. A 403 is the system working; gold carries waiting.
    expect(VERDICT_STYLE.refused.fill).not.toContain("red");
    expect(VERDICT_STYLE.absent.fill).not.toContain("red");
    expect(VERDICT_STYLE.error.fill).toContain("red");
  });
});
