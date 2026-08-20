import { describe, expect, it } from "vitest";

import type { AccessMatrix, CurrentUser, Role } from "../../api/types";
import { buildNav, isActivePath } from "./navModel";

/**
 * Which items a role is offered.
 *
 * These assert on a §7 boundary, not on appearance — hiding an item does not
 * secure it, but offering one that will 403 or come back empty is a defect in
 * its own right. jsdom would tell us nothing about the rail's looks, so the
 * model is tested and the rendering is checked in a browser.
 */

function userWith(role: Role, access: Partial<AccessMatrix>): CurrentUser {
  return {
    id: "u1",
    username: role.toLowerCase(),
    work_email: "",
    personal_email: "",
    work_phone: "",
    personal_phone: "",
    full_name: "Test User",
    role,
    role_display: role,
    woreda_assignment: [],
    partner: null,
    partner_name: null,
    account_status: "ACTIVE",
    scopable_woredas: [],
    access: {
      case_scope: "OWN_CASELOAD",
      case_write: true,
      referral_scope: "OWN_CASELOAD",
      referral_write: true,
      group_scope: "NONE",
      group_write: false,
      delivery_write: false,
      ...access,
    },
  };
}

const paths = (user: CurrentUser) =>
  buildNav(user, { openAlerts: 0 }).flatMap((section) => section.items.map((item) => item.path));

describe("buildNav", () => {
  it("groups a case manager's items into Dashboard, Work and Directory", () => {
    const sections = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 3 });
    expect(sections.map((s) => s.titleKey)).toEqual(["nav.sectionDashboard", "nav.sectionWork", "nav.sectionDirectory"]);
    expect(sections[0].items.map((i) => i.path)).toEqual(["/dashboard/my-work"]);
    // Sprints 5 and 6 added five delivery screens to the Work section. All are
    // offered to anyone with case content, because all are scoped server-side:
    // a trainer sees the enrolments she recorded, an enterprise officer her own
    // records, a case manager her caseload's.
    expect(sections[1].items.map((i) => i.path)).toEqual([
      "/cases",
      "/referrals",
      "/alerts",
      "/training",
      "/placements",
      "/enterprises",
      "/verification",
      "/grievances",
    ]);
    expect(sections[2].items.map((i) => i.path)).toEqual(["/youth", "/partners"]);
  });

  it("offers user administration to the system administrator alone", () => {
    expect(paths(userWith("SYSTEM_ADMIN", { case_scope: "ALL" }))).toContain("/users");
    // A supervisor has the widest case scope short of admin and still must not
    // reach it: §7 grants user administration by role, not by scope.
    expect(paths(userWith("SUPERVISOR", { case_scope: "OWN_WOREDA" }))).not.toContain("/users");
  });

  it("offers partner staff their referrals but no case, youth or dashboard item", () => {
    // The known §7 consequence: CaseViewSet and YouthViewSet declare no
    // partner_field, so those screens come back empty for a partner account.
    // The nav must not invite them into an empty screen.
    const partner = paths(userWith("PARTNER_STAFF", { case_scope: "NONE", referral_scope: "LINKED" }));
    expect(partner).toEqual(["/referrals", "/partners"]);
  });

  it("drops a section entirely rather than drawing an empty heading", () => {
    const sections = buildNav(userWith("PARTNER_STAFF", { case_scope: "NONE", referral_scope: "NONE" }), {
      openAlerts: 0,
    });
    expect(sections.map((s) => s.titleKey)).toEqual(["nav.sectionDirectory"]);
  });

  it("withholds every dashboard tier from a role with no case population", () => {
    // A LINKED referral scope sees individual referrals, never a denominator,
    // so a programme total would be meaningless rather than merely empty.
    const trainer = paths(userWith("TRAINER", { case_scope: "LINKED", referral_scope: "LINKED" }));
    expect(trainer.filter((path) => path.startsWith("/dashboard"))).toEqual([]);
  });

  it("gives a programme manager the comparative tiers and no personal one", () => {
    const pm = paths(userWith("PROGRAMME_MANAGER", { case_scope: "ALL", case_write: false, referral_scope: "ALL" }));
    expect(pm.filter((path) => path.startsWith("/dashboard"))).toEqual([
      "/dashboard/woreda",
      "/dashboard/programme",
      "/dashboard/results",
    ]);
  });

  it("carries the live alert count on the alerts item only", () => {
    const items = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 12 }).flatMap((s) => s.items);
    expect(items.find((i) => i.path === "/alerts")?.badgeCount).toBe(12);
    expect(items.filter((i) => i.badgeCount !== undefined)).toHaveLength(1);
  });
});

describe("isActivePath", () => {
  it("matches a section and its children", () => {
    expect(isActivePath("/cases", "/cases")).toBe(true);
    expect(isActivePath("/cases", "/cases/abc-123")).toBe(true);
  });

  it("does not light a sibling that merely shares a prefix", () => {
    // A bare startsWith lit /case for /cases, and would light /dashboard for
    // every tier once those become sidebar items of their own.
    expect(isActivePath("/case", "/cases")).toBe(false);
    expect(isActivePath("/users", "/youth")).toBe(false);
  });
});
