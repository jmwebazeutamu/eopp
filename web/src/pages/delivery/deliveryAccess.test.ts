import { describe, expect, it } from "vitest";

import { testUser } from "../../test/authHarness";
import { DELIVERY_SCREENS, canSeeDelivery, landingDelivery, visibleDelivery } from "./deliveryAccess";

/**
 * What is worth asserting is the narrowing, not the table.
 *
 * The rail used to offer all four delivery screens to anybody with case
 * content, so a trainer was shown Placements, Enterprises and Verification —
 * three screens that, scoped through `LINKED_THROUGH`, return her nothing at
 * all. An empty table teaches people the application is broken.
 */

const as = (role: Parameters<typeof testUser>[0]) => testUser(role);

describe("visibleDelivery", () => {
  it("gives a trainer her own screen and nothing else", () => {
    expect(visibleDelivery(as("TRAINER")).map((s) => s.path)).toEqual(["/training"]);
  });

  it("gives each linked role the entity it is linked through", () => {
    // The same mapping `LINKED_THROUGH` makes server-side, said once more here
    // so the rail and the queryset cannot disagree about who works what.
    expect(visibleDelivery(as("EMPLOYER_LIAISON")).map((s) => s.path)).toEqual(["/placements"]);
    expect(visibleDelivery(as("ENTERPRISE_OFFICER")).map((s) => s.path)).toEqual(["/enterprises"]);
  });

  it("gives a role that oversees a caseload all four", () => {
    expect(visibleDelivery(as("SUPERVISOR"))).toHaveLength(4);
    expect(visibleDelivery(as("CASE_MANAGER"))).toHaveLength(4);
  });

  it("gives a WLT role none of them", () => {
    // These four count youth-side delivery, and a facilitator has no caseload.
    expect(visibleDelivery(as("WLT_FACILITATOR"))).toEqual([]);
    expect(visibleDelivery(as("PARTNER_STAFF"))).toEqual([]);
  });

  it("orders the tabs the same way whatever order a role's row lists", () => {
    // The strip and the rail must read left to right in one order.
    expect(visibleDelivery(as("SYSTEM_ADMIN")).map((s) => s.path)).toEqual(DELIVERY_SCREENS.map((s) => s.path));
  });
});

describe("the guard and the landing", () => {
  it("refuses a trainer a screen that is not hers", () => {
    expect(canSeeDelivery(as("TRAINER"), "/training")).toBe(true);
    expect(canSeeDelivery(as("TRAINER"), "/placements")).toBe(false);
  });

  it("lands each role on its own first screen", () => {
    expect(landingDelivery(as("EMPLOYER_LIAISON"))?.path).toBe("/placements");
    expect(landingDelivery(as("SUPERVISOR"))?.path).toBe("/training");
  });

  it("has nowhere to land a role with none, and says so rather than guessing", () => {
    expect(landingDelivery(as("WLT_FACILITATOR"))).toBeNull();
  });

  it("refuses a signed-out reader everything", () => {
    expect(visibleDelivery(null)).toEqual([]);
    expect(canSeeDelivery(undefined, "/training")).toBe(false);
  });
});
