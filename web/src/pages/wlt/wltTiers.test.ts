import { describe, expect, it } from "vitest";

import { testUser } from "../../test/authHarness";
import { WLT_TIERS, canSeeWltTier, landingWltTier, visibleWltTiers } from "./wltTiers";

/**
 * Four small dashboards, not one with role-based hiding.
 *
 * What is worth asserting is the split the handoff insists on: a facilitator
 * must not be offered the programme view, because a single dashboard with
 * permissions converges on the union of every stakeholder's requirements and
 * she ends up reading donor indicators.
 */

const as = (role: Parameters<typeof testUser>[0]) => testUser(role);

describe("visibleWltTiers", () => {
  it("gives a facilitator her queue and nothing above it", () => {
    // No cross-group comparison, no regional aggregate — the handoff deletes
    // both from Tier 1.
    expect(visibleWltTiers(as("WLT_FACILITATOR")).map((t) => t.path)).toEqual(["home"]);
  });

  it("gives a woreda officer her queue and her oversight view", () => {
    // She approves phase moves, so the approval card is her job — and the
    // tactical tier is the one written for her.
    expect(visibleWltTiers(as("WLT_WOREDA_OFFICER")).map((t) => t.path)).toEqual(["home", "woreda"]);
  });

  it("gives a region officer the comparative tiers and no personal queue", () => {
    expect(visibleWltTiers(as("WLT_REGION_OFFICER")).map((t) => t.path)).toEqual([
      "woreda",
      "programme",
      "results",
    ]);
  });

  it("gives a youth-side role none of them", () => {
    // These count savings groups. A case manager has no group population.
    expect(visibleWltTiers(as("CASE_MANAGER"))).toEqual([]);
    expect(visibleWltTiers(as("TRAINER"))).toEqual([]);
  });

  it("orders the tabs the same way whatever order a role's row lists", () => {
    expect(visibleWltTiers(as("SYSTEM_ADMIN")).map((t) => t.path)).toEqual(WLT_TIERS.map((t) => t.path));
  });
});

describe("the guard and the landing", () => {
  it("refuses a facilitator a tier that is not hers", () => {
    expect(canSeeWltTier(as("WLT_FACILITATOR"), "home")).toBe(true);
    expect(canSeeWltTier(as("WLT_FACILITATOR"), "programme")).toBe(false);
  });

  it("lands each role on its own first tier", () => {
    expect(landingWltTier(as("WLT_FACILITATOR"))?.path).toBe("home");
    expect(landingWltTier(as("WLT_REGION_OFFICER"))?.path).toBe("woreda");
  });

  it("has nowhere to land a role with none, and says so rather than guessing", () => {
    expect(landingWltTier(as("CASE_MANAGER"))).toBeNull();
    expect(visibleWltTiers(null)).toEqual([]);
  });
});
