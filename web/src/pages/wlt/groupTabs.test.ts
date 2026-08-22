import { describe, expect, it } from "vitest";

import { badgeFor, DEFAULT_TAB, GROUP_TABS, tabFor } from "./groupTabs";

describe("tabFor", () => {
  it("resolves each slug to its own tab", () => {
    for (const tab of GROUP_TABS) {
      expect(tabFor(tab.slug).slug).toBe(tab.slug);
    }
  });

  it("falls back to the default rather than failing on an unknown segment", () => {
    // The segment comes from a pasted or hand-edited URL. A group that exists
    // is still worth showing; a wrong *group* id is a different matter and
    // still 404s.
    expect(tabFor("nonsense").slug).toBe(DEFAULT_TAB);
    expect(tabFor(undefined).slug).toBe(DEFAULT_TAB);
    expect(tabFor("").slug).toBe(DEFAULT_TAB);
  });

  it("opens on overview, because readiness is why the page exists", () => {
    expect(GROUP_TABS[0].slug).toBe("overview");
    expect(DEFAULT_TAB).toBe("overview");
  });
});

describe("badgeFor", () => {
  const members = GROUP_TABS.find((t) => t.slug === "members")!;
  const overview = GROUP_TABS.find((t) => t.slug === "overview")!;

  it("shows a zero, because zero is a reason to open the tab", () => {
    // "0 linkages" is information. `undefined` — not loaded — is not.
    expect(badgeFor(members, { members: 0 })).toBe(0);
  });

  it("shows nothing before the count has loaded", () => {
    expect(badgeFor(members, {})).toBeNull();
  });

  it("gives no badge to a tab that carries none", () => {
    expect(badgeFor(overview, { members: 17 })).toBeNull();
  });

  it("reads the count its own tab names, not another's", () => {
    expect(badgeFor(members, { members: 17, meetings: 33, linkages: 3 })).toBe(17);
  });
});

describe("the tab set", () => {
  it("has unique slugs", () => {
    const slugs = GROUP_TABS.map((t) => t.slug);
    expect(new Set(slugs).size).toBe(slugs.length);
  });

  it("uses URL-safe slugs", () => {
    for (const tab of GROUP_TABS) {
      expect(tab.slug).toMatch(/^[a-z-]+$/);
    }
  });
});
