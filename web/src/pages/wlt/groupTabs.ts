import type { StringKey } from "../../i18n/strings";

/**
 * The group record's tabs, as data.
 *
 * Kept apart from the page for the reason `navModel.ts` and `timelineLayout.ts`
 * are: which tabs exist, what they are called and which counts they carry is
 * testable, and a test asserting on a rendered `<button>` would be asserting on
 * antd.
 *
 * Tabs are **routes**, not local state — `/wlt/groups/:groupId/:tab` — so a
 * field officer can send a colleague a link to the roster rather than to the
 * top of a 3,600px page, and the browser's back button behaves.
 */

export interface GroupTab {
  /** URL segment, and the value stored in the route. */
  slug: string;
  labelKey: StringKey;
  /**
   * Which count sits in the tab's badge, or null for none.
   *
   * Named rather than computed here: the page holds the data, this holds the
   * decision about which number belongs on which tab.
   */
  badge: "members" | "meetings" | "linkages" | null;
}

/**
 * In the order the work happens, not alphabetically: readiness first because
 * it is why the page exists, then the people, then what they did, then the
 * money, then the outside world, then the record of all of it.
 */
export const GROUP_TABS: GroupTab[] = [
  { slug: "overview", labelKey: "wlt.tabOverview", badge: null },
  { slug: "members", labelKey: "wlt.tabMembers", badge: "members" },
  { slug: "meetings", labelKey: "wlt.tabMeetings", badge: "meetings" },
  { slug: "savings", labelKey: "wlt.tabSavings", badge: null },
  { slug: "linkages", labelKey: "wlt.tabLinkages", badge: "linkages" },
  { slug: "history", labelKey: "wlt.tabHistory", badge: null },
];

export const DEFAULT_TAB = "overview";

/**
 * Resolve a URL segment to a tab.
 *
 * An unknown segment falls back to the default rather than 404ing: the segment
 * arrives from a pasted or edited URL, and a group that exists is still worth
 * showing. A wrong *group* id is a different matter and still 404s.
 */
export function tabFor(slug: string | undefined): GroupTab {
  return GROUP_TABS.find((tab) => tab.slug === slug) ?? GROUP_TABS[0];
}

/** The badge number for a tab, or null when it carries none or has no data yet. */
export function badgeFor(
  tab: GroupTab,
  counts: { members?: number; meetings?: number; linkages?: number },
): number | null {
  if (!tab.badge) return null;
  const value = counts[tab.badge];
  // Zero is a real answer and worth showing — "0 linkages" is the reason to
  // open that tab. `undefined` means not loaded yet, which is not.
  return typeof value === "number" ? value : null;
}
