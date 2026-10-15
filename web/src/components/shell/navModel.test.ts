import { describe, expect, it } from "vitest";

import type { AccessMatrix, CurrentUser, Role } from "../../api/types";
import { activeModule, buildModules, buildNav, isActiveItem, isActivePath } from "./navModel";

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
  it("spends one rail row each on the dashboard and on delivery", () => {
    // Every tier reports on the youth-employment caseload — My work is a case
    // manager's queue, Results is the donor's view of placements — so a
    // top-level "Dashboard" heading claimed a breadth they do not have and put
    // four PSNP screens above the section that names PSNP.
    const sections = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 3 });

    expect(sections.map((s) => s.titleKey)).toEqual(["nav.sectionWork", null, "nav.sectionDirectory"]);
    // Sprints 5 and 6 added five delivery screens. All are offered to anyone
    // with case content, because all are scoped server-side: a trainer sees the
    // enrolments she recorded, a case manager her caseload's.
    // Nine rows became six. The four tiers and the four delivery screens are
    // tabs on the pages they lead to, so the rail no longer duplicates a
    // control that already exists one click away.
    expect(sections[0].items.map((i) => i.path)).toEqual([
      "/dashboard",
      // The register leads the operational items — somebody is registered
      // before a case is opened for them — the same order the WLT section uses.
      "/youth",
      "/cases",
      "/referrals",
      "/alerts",
      "/delivery",
    ]);
    // Directory is a reference list now — partners, and user accounts for the
    // administrator. The register moved out because it is a working screen.
    expect(sections[2].items.map((i) => i.path)).toEqual(["/partners"]);
  });

  it("gives grievances a heading-less section of its own", () => {
    // The complaints channel belongs to neither programme. Filing it under
    // either would say something untrue about who may use it, so it sits at the
    // top level with no heading — and cannot be collapsed away.
    const sections = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 0 });
    const grievances = sections.find((s) => s.items.some((i) => i.path === "/grievances"));

    expect(grievances?.titleKey).toBeNull();
    expect(grievances?.items).toHaveLength(1);
  });

  it("offers grievances to a WLT role that has no case content at all", () => {
    const facilitator = paths(userWith("WLT_FACILITATOR", { case_scope: "NONE", group_scope: "OWN_GROUPS" }));
    expect(facilitator).toContain("/grievances");
    expect(facilitator).not.toContain("/cases");
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

  it("offers one dashboard entry, whichever tiers the role has", () => {
    // Four tier links were four rows of the rail spent on one destination, and
    // the tiers are already tabs on the page they lead to. `/dashboard` sends
    // each role to its own landing tier, so the rail does not have to know
    // which — and `tierAccess` still decides what they then see.
    const pm = paths(userWith("PROGRAMME_MANAGER", { case_scope: "ALL", case_write: false, referral_scope: "ALL" }));
    expect(pm.filter((path) => path.startsWith("/dashboard"))).toEqual(["/dashboard"]);

    const cm = paths(userWith("CASE_MANAGER", {}));
    expect(cm.filter((path) => path.startsWith("/dashboard"))).toEqual(["/dashboard"]);
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

describe("isActiveItem", () => {

  it("lets one rail entry stand for the routes it fronts", () => {
    // `/delivery` redirects to whichever of the four is the reader's, and the
    // four keep their original URLs. Without this the rail loses track the
    // moment the redirect completes: nothing is lit, and the section holding
    // the page collapses because no item claims the route.
    const delivery = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 0 })
      .flatMap((s) => s.items)
      .find((i) => i.path === "/delivery")!;

    expect(isActiveItem(delivery, "/delivery")).toBe(true);
    expect(isActiveItem(delivery, "/training")).toBe(true);
    expect(isActiveItem(delivery, "/verification")).toBe(true);
    expect(isActiveItem(delivery, "/cases")).toBe(false);
  });

  it("does not let an item claim a route it merely prefixes", () => {
    const cases = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 0 })
      .flatMap((s) => s.items)
      .find((i) => i.path === "/cases")!;

    expect(isActiveItem(cases, "/cases/abc")).toBe(true);
    expect(isActiveItem(cases, "/caseload")).toBe(false);
  });
});

describe("buildModules", () => {
  const modules = (user: CurrentUser) => buildModules(buildNav(user, { openAlerts: 0 }));

  it("lands on the module's first permitted destination, never on a route the role lacks", () => {
    const work = modules(userWith("CASE_MANAGER", {})).find((m) => m.key === "nav.sectionWork")!;
    expect(work.landing).toBe(work.items[0].path);
    expect(work.items.map((i) => i.path)).toContain(work.landing);
  });

  it("gives a one-page module no secondary destinations", () => {
    const grievances = modules(userWith("CASE_MANAGER", {})).find((m) => m.landing === "/grievances")!;
    expect(grievances.items).toEqual([]);
  });

  it("offers a role with no case or group access only what it is allowed", () => {
    const partner = modules(userWith("PARTNER_STAFF", { case_scope: "NONE", referral_scope: "LINKED" }));
    expect(partner.flatMap((m) => [m.landing, ...m.items.map((i) => i.path)])).not.toContain("/youth");
  });

  it("rolls the alert count up to the module that holds it", () => {
    const work = buildModules(buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 7 })).find(
      (m) => m.key === "nav.sectionWork",
    )!;
    expect(work.badgeCount).toBe(7);
  });
});

describe("activeModule", () => {
  const sections = buildNav(userWith("CASE_MANAGER", {}), { openAlerts: 0 });
  const mods = buildModules(sections);

  it("follows nested routes and similar prefixes", () => {
    expect(activeModule(mods, sections, "/cases/abc-123")?.key).toBe("nav.sectionWork");
    expect(activeModule(mods, sections, "/partners")?.key).toBe("nav.sectionDirectory");
  });

  it("is none for a route no module owns", () => {
    expect(activeModule(mods, sections, "/nowhere")).toBeUndefined();
  });
});
