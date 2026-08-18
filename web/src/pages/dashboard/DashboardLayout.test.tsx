import { describe, expect, it } from "vitest";

import { visibleTiers } from "./DashboardLayout";

/**
 * Which tiers a role is offered.
 *
 * The handoff's organising argument: four small dashboards, not one with
 * role-based hiding, "because a single dashboard with permissions always
 * converges on the union of every stakeholder's requirements, and the case
 * manager ends up looking at donor indicators".
 *
 * This is the tab gate, not the security boundary — every tier is §7-scoped
 * server-side regardless, and the API refuses a scope with no case population.
 * Hiding a tab only avoids offering someone a screen that is not theirs.
 */

const paths = (scope: string, canWrite: boolean) => visibleTiers(scope, canWrite).map((tier) => tier.path);

describe("visibleTiers", () => {
  it("gives a case manager their own work and nothing comparative", () => {
    // OWN_CASELOAD, writes cases.
    expect(paths("OWN_CASELOAD", true)).toEqual(["my-work"]);
  });

  it("keeps programme conversion rates away from a case manager", () => {
    // The cream-skimming pressure the handoff warns about: a case manager who
    // can see their own placement rate has an incentive to pick easier youth.
    expect(paths("OWN_CASELOAD", true)).not.toContain("programme");
    expect(paths("OWN_CASELOAD", true)).not.toContain("results");
  });

  it("gives an outreach worker their woreda but not the programme view", () => {
    // OWN_WOREDA and writes — registers youth at intake.
    expect(paths("OWN_WOREDA", true)).toEqual(["my-work", "woreda"]);
  });

  it("gives a supervisor the woreda and programme tiers", () => {
    // OWN_WOREDA, read-only: supervisory rather than case-facing.
    expect(paths("OWN_WOREDA", false)).toEqual(["my-work", "woreda", "programme"]);
  });

  it("gives a programme manager every tier including the donor one", () => {
    expect(paths("ALL", false)).toEqual(["my-work", "woreda", "programme", "results"]);
  });

  it("offers a LINKED role nothing beyond its own work", () => {
    // Partner staff and trainers have no case population; the API 403s on all
    // four, so the only honest tab list is the minimum one.
    expect(paths("LINKED", false)).toEqual(["my-work"]);
  });

  it("never offers the donor tier to anyone scoped below the whole programme", () => {
    for (const scope of ["OWN_CASELOAD", "OWN_WOREDA", "LINKED", "NONE"]) {
      expect(paths(scope, false)).not.toContain("results");
      expect(paths(scope, true)).not.toContain("results");
    }
  });
});
