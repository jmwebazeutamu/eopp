import type { CurrentUser } from "../../api/types";
import type { StringKey } from "../../i18n/strings";
import { visibleTiers } from "../../pages/dashboard/tierAccess";
import { ICON_PATHS } from "../ui";

/**
 * What the sidebar offers, as data.
 *
 * Kept apart from the rendering for the same reason `timelineLayout.ts` is: the
 * part worth testing is which items a role gets, not how a `<button>` draws.
 * jsdom applies no stylesheet, so a test asserting on the rail's appearance
 * would assert on nothing — but "a partner staff account is offered no youth
 * registry" is a real claim about a real boundary, and it can be tested here.
 *
 * Visibility follows the §7 access matrix the API resolves, not the role name,
 * with one exception noted on `/users`. Hiding an item does not secure it — the
 * API refuses out-of-scope reads regardless, and out-of-scope records 404. This
 * only avoids offering a screen that would come back empty or refused.
 */

export interface NavItem {
  path: string;
  labelKey: StringKey;
  icon: string;
  /** Live count rendered right-aligned. Only Alerts carries one today. */
  badgeCount?: number;
}

export interface NavSection {
  /** Section heading, rendered above the group and dropped when collapsed. */
  titleKey: StringKey;
  items: NavItem[];
}

/**
 * Above this many open alerts the badge stops being muted and takes the gold
 * "waiting" tone. A working inbox always holds a few; a badge that shouts at
 * three teaches people to stop reading it.
 *
 * A display threshold, deliberately not one of the §11 programme thresholds —
 * it changes nothing about when an alert is raised. Worth confirming with
 * supervisors in Phase 1 all the same.
 */
export const ALERT_BADGE_ATTENTION_AT = 10;

export function buildNav(user: CurrentUser, options: { openAlerts: number }): NavSection[] {
  const hasCases = user.access.case_scope !== "NONE";
  const hasReferrals = user.access.referral_scope !== "NONE";

  // Each dashboard tier is a destination of its own rather than four pages
  // behind one "Dashboard" entry. Nothing used to reveal that Results existed.
  // A role offered none — the LINKED roles, which see individual referrals but
  // never a denominator — contributes no items at all.
  const tiers: NavItem[] = visibleTiers(user).map((tier) => ({
    path: `/dashboard/${tier.path}`,
    labelKey: tier.labelKey,
    icon: TIER_ICONS[tier.path] ?? ICON_PATHS.dashboard,
  }));

  const work: NavItem[] = [
    ...tiers,
    ...(hasCases ? [item("/cases", "nav.cases", ICON_PATHS.cases)] : []),
    ...(hasReferrals ? [item("/referrals", "nav.referrals", ICON_PATHS.queue)] : []),
    ...(hasCases ? [{ ...item("/alerts", "nav.alerts", ICON_PATHS.alerts), badgeCount: options.openAlerts }] : []),
  ];

  const directory: NavItem[] = [
    ...(hasCases ? [item("/youth", "nav.registry", ICON_PATHS.registry)] : []),
    item("/partners", "nav.partners", ICON_PATHS.partners),
    // User administration is the one genuine role test: §7 grants it to the
    // system administrator alone, and no scope column expresses that.
    ...(user.role === "SYSTEM_ADMIN" ? [item("/users", "nav.users", ICON_PATHS.users)] : []),
  ];

  // An empty section would otherwise draw a heading and a divider over nothing:
  // a partner staff account is offered no Work items at all.
  return [
    { titleKey: "nav.sectionWork" as StringKey, items: work },
    { titleKey: "nav.sectionDirectory" as StringKey, items: directory },
  ].filter((section) => section.items.length > 0);
}

/**
 * One icon per tier, so the collapsed 64px rail can still tell them apart.
 * Four identical dashboard glyphs would be four blank squares.
 */
const TIER_ICONS: Record<string, string> = {
  "my-work": ICON_PATHS.dashboard,
  woreda: ICON_PATHS.woreda,
  programme: ICON_PATHS.programme,
  results: ICON_PATHS.results,
};

function item(path: string, labelKey: StringKey, icon: string): NavItem {
  return { path, labelKey, icon };
}

/**
 * Whether a nav path owns the current location.
 *
 * Segment-aware rather than a bare `startsWith`, which lights `/case` for
 * `/cases` and — once the dashboard tiers arrive as sibling routes — would
 * light two items at once.
 */
export function isActivePath(navPath: string, pathname: string): boolean {
  return pathname === navPath || pathname.startsWith(`${navPath}/`);
}
