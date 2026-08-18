import { describe, expect, it } from "vitest";

import type { Role } from "../../api/types";
import { TIER_ACCESS, TIERS, canSeeTier, landingTier, visibleTiers } from "./tierAccess";

/**
 * Which tiers a role is offered.
 *
 * The handoff's organising argument: four small dashboards, not one with
 * role-based hiding, "because a single dashboard with permissions always
 * converges on the union of every stakeholder's requirements, and the case
 * manager ends up looking at donor indicators".
 *
 * This is the tab gate, not the security boundary — every tier is §7-scoped
 * server-side regardless. Hiding a tab only avoids offering someone a screen
 * that is not theirs to read.
 */

const as = (role: Role) => ({ role });
const paths = (role: Role) => visibleTiers(as(role)).map((tier) => tier.path);

describe("visibleTiers", () => {
  it("gives a case manager their own work and nothing comparative", () => {
    expect(paths("CASE_MANAGER")).toEqual(["my-work"]);
  });

  it("keeps programme conversion rates away from a case manager", () => {
    // The cream-skimming pressure the handoff warns about: a case manager who
    // can see their own placement rate has an incentive to pick easier youth.
    expect(paths("CASE_MANAGER")).not.toContain("programme");
    expect(paths("CASE_MANAGER")).not.toContain("results");
  });

  it("gives a supervisor their work and their woreda", () => {
    expect(paths("SUPERVISOR")).toEqual(["my-work", "woreda"]);
  });

  it("gives programme and M&E staff the comparative tiers but no personal one", () => {
    // They have no caseload, so "My work" would be an empty screen rather than
    // a small one. Both roles carry case_scope ALL, which is exactly why scope
    // could not express this and the role table does.
    expect(paths("PROGRAMME_MANAGER")).toEqual(["woreda", "programme", "results"]);
    expect(paths("MNE_STAFF")).toEqual(["woreda", "programme", "results"]);
  });

  it("gives the system administrator all four", () => {
    expect(paths("SYSTEM_ADMIN")).toEqual(["my-work", "woreda", "programme", "results"]);
  });

  it("offers a LINKED role no dashboard at all", () => {
    // Partner staff, trainers, employer liaisons and enterprise officers see
    // individual referrals but never a denominator, so every tier would be
    // either refused or a screen of zeroes.
    for (const role of ["PARTNER_STAFF", "TRAINER", "EMPLOYER_LIAISON", "ENTERPRISE_OFFICER"] as Role[]) {
      expect(paths(role)).toEqual([]);
    }
  });

  it("never offers the donor tier below the whole programme", () => {
    for (const role of Object.keys(TIER_ACCESS) as Role[]) {
      if (["PROGRAMME_MANAGER", "MNE_STAFF", "SYSTEM_ADMIN"].includes(role)) continue;
      expect(paths(role)).not.toContain("results");
    }
  });

  it("orders every role's tiers the same way", () => {
    // The rail and the tab row read from this, so a row that happened to list
    // its tiers out of order would put Results before Woreda for one role only.
    const order = TIERS.map((tier) => tier.path);
    for (const role of Object.keys(TIER_ACCESS) as Role[]) {
      const got = paths(role);
      expect(got).toEqual(order.filter((path) => got.includes(path)));
    }
  });

  it("names only tiers that exist", () => {
    const known = new Set(TIERS.map((tier) => tier.path));
    for (const [role, allowed] of Object.entries(TIER_ACCESS)) {
      for (const path of allowed) expect(known.has(path), `${role} → ${path}`).toBe(true);
    }
  });
});

describe("canSeeTier", () => {
  it("refuses a tier the role does not cover, and admits one it does", () => {
    expect(canSeeTier(as("CASE_MANAGER"), "results")).toBe(false);
    expect(canSeeTier(as("CASE_MANAGER"), "my-work")).toBe(true);
  });

  it("refuses everything to a signed-out caller", () => {
    for (const tier of TIERS) expect(canSeeTier(null, tier.path)).toBe(false);
  });
});

describe("landingTier", () => {
  it("lands each role on the most personal tier it has", () => {
    expect(landingTier(as("CASE_MANAGER"))?.path).toBe("my-work");
    expect(landingTier(as("PROGRAMME_MANAGER"))?.path).toBe("woreda");
    expect(landingTier(as("SYSTEM_ADMIN"))?.path).toBe("my-work");
  });

  it("returns nothing for a role with no dashboard, rather than a tier that would refuse it", () => {
    expect(landingTier(as("PARTNER_STAFF"))).toBeNull();
  });
});
