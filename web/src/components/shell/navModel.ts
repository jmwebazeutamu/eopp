import type { CurrentUser } from "../../api/types";
import type { StringKey } from "../../i18n/strings";
import { visibleTiers } from "../../pages/dashboard/tierAccess";
import { visibleDelivery } from "../../pages/delivery/deliveryAccess";
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
  /**
   * Other routes this item stands for.
   *
   * One rail entry can front several screens: `/delivery` lands on whichever of
   * Training, Placements, Enterprises or Verification is the reader's, and the
   * four keep their original URLs so older links still work. Without this the
   * rail loses track the moment the redirect completes — nothing is lit, and
   * the section holding the page collapses because no item claims the route.
   */
  ownsPaths?: string[];
}

export interface NavSection {
  /**
   * Section heading, rendered above the group and dropped when the rail is
   * collapsed to icons.
   *
   * **Null means a top-level item with no heading**, which cannot be collapsed
   * and is always shown. Grievances is the only one: it belongs to neither
   * programme, so filing it under either would say something untrue about who
   * the channel is for.
   */
  titleKey: StringKey | null;
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

  // **One entry, not one per tier.** Four tier links were four rows of the rail
  // spent on one destination, and the tiers are already tabs on the page they
  // lead to — so the rail was duplicating a control that exists, better, one
  // click away.
  //
  // `/dashboard` rather than a tier path: `DashboardHome` sends each role to
  // its own landing tier, so a case manager gets her work and a donor gets
  // results without the rail having to know which. `isActivePath` lights this
  // item on every `/dashboard/*` route, so the reader still sees where they are.
  //
  // A role offered no tier at all — the LINKED roles, which see individual
  // referrals but never a denominator — gets no item, because `/dashboard`
  // would bounce them straight out again.
  const tiers: NavItem[] =
    visibleTiers(user).length > 0 ? [item("/dashboard", "nav.dashboard", ICON_PATHS.dashboard)] : [];

  // The tiers lead the PSNP section rather than standing as a section of their
  // own. Every one of them reports on the youth-employment caseload — My work
  // is a case manager's queue, Results is the donor's view of placements — so a
  // top-level "Dashboard" heading claimed a breadth they do not have, and put
  // four PSNP screens above the section that names PSNP.
  const work: NavItem[] = [
    ...tiers,
    // The register leads the operational items, the same way it does in the WLT
    // section: somebody is registered before a case is opened for them, and the
    // nav reads better in the order the work happens than in alphabetical
    // groups. It was under Directory, which is where a *reference* list belongs
    // — partners, user accounts — and this is a working screen.
    //
    // Under PSNP rather than at the top level, unlike Grievances, because it is
    // already gated on `hasCases`: a WLT role never sees it and gets
    // `/wlt/beneficiaries` instead. The two views read one register (handoff
    // D1, one identity) and each programme reaches it through its own door.
    ...(hasCases ? [item("/youth", "nav.registry", ICON_PATHS.registry)] : []),
    ...(hasCases ? [item("/cases", "nav.cases", ICON_PATHS.cases)] : []),
    ...(hasReferrals ? [item("/referrals", "nav.referrals", ICON_PATHS.queue)] : []),
    ...(hasCases ? [{ ...item("/alerts", "nav.alerts", ICON_PATHS.alerts), badgeCount: options.openAlerts }] : []),
  ];

  // Sprint 5. Offered to anyone with case content, because the two screens are
  // scoped server-side: a trainer sees the enrolments she recorded, a case
  // manager her caseload's, a supervisor her woreda's. Hiding an item does not
  // secure it; this only avoids offering a screen that would come back empty.
  // **One entry, not four.** Training, Placements, Enterprises and Verification
  // are four screens that are each a single queue, and side by side in the rail
  // they spent four of nine PSNP rows on work most roles never do. They are
  // tabs now, on the dashboard's pattern.
  //
  // `visibleDelivery` narrows by role rather than by `hasCases`, which is the
  // more useful half: a trainer used to be offered Placements, Enterprises and
  // Verification — three screens that, scoped through `LINKED_THROUGH`, return
  // her nothing. She now gets Training, and no tab strip, because a strip with
  // one tab is a control that cannot do anything.
  const deliveryScreens = visibleDelivery(user);
  const delivery: NavItem[] = deliveryScreens.length
    ? [{ ...item("/delivery", "nav.delivery", ICON_PATHS.queue), ownsPaths: deliveryScreens.map((s) => s.path) }]
    : [];


  const directory: NavItem[] = [
    item("/partners", "nav.partners", ICON_PATHS.partners),
    // User administration is the one genuine role test: §7 grants it to the
    // system administrator alone, and no scope column expresses that.
    ...(user.role === "SYSTEM_ADMIN" ? [item("/users", "nav.users", ICON_PATHS.users)] : []),
  ];

  // The WLT group module. Its own section rather than entries under Work,
  // because it is a second programme with a second subject: these screens are
  // about savings groups, and the roles that see them see no case content at
  // all. `group_scope` is the same server-resolved matrix row the case items
  // read, so the boundary is stated once.
  const hasGroups = user.access.group_scope !== "NONE";

  // The complaints channel belongs to neither module, so it is offered to
  // anybody either module admits. It sat under the youth-side delivery group,
  // which meant a facilitator could reach it only by typing the URL — and a
  // grievance mechanism nobody can find is not one.
  const grievances: NavItem[] =
    hasCases || hasGroups ? [item("/grievances", "nav.grievances", ICON_PATHS.alerts)] : [];
  const wlt: NavItem[] = hasGroups
    ? [
        // In workflow order, which is also the order a facilitator meets them:
        // a woman is registered, then seated in a group, then her group reaches
        // a service or a structure. The register leads because before it the
        // module had no first step at all.
        // Her queue leads, the same way My work leads the youth rail: the
        // question this module's Tier 1 answers is "what do I record today",
        // and it is not answerable from a register or a group list.
        // One entry, four tiers as tabs — the same shape the youth rail now
        // uses. `/wlt/dashboard` lands each role on its own tier, and the item
        // stands for every route beneath it so the rail keeps track after the
        // redirect.
        {
          ...item("/wlt/dashboard", "nav.wltDashboard", ICON_PATHS.dashboard),
          ownsPaths: ["/wlt/home"],
        },
        item("/wlt/beneficiaries", "nav.wltBeneficiaries", ICON_PATHS.registry),
        item("/wlt/groups", "nav.wltGroups", ICON_PATHS.cases),
        item("/wlt/linkages", "nav.wltLinkages", ICON_PATHS.partners),
        item("/wlt/cla-readiness", "nav.wltCla", ICON_PATHS.dashboard),
        item("/wlt/federation-readiness", "nav.wltFederation", ICON_PATHS.dashboard),
      ]
    : [];

  // An empty section would otherwise draw a heading and a divider over nothing:
  // a partner staff account is offered no Work items at all.
  return [
    { titleKey: "nav.sectionWork" as StringKey, items: [...work, ...delivery] },
    { titleKey: "nav.sectionWlt" as StringKey, items: wlt },
    // Between the two programmes and the directory, and under no heading. It
    // sat inside the PSNP group, which said the complaints channel was a
    // youth-side screen — and a savings group's complaint is not.
    { titleKey: null, items: grievances },
    { titleKey: "nav.sectionDirectory" as StringKey, items: directory },
  ].filter((section) => section.items.length > 0);
}

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

/**
 * Whether a nav item owns the current location — its own path, or any it fronts.
 *
 * Used for the highlight and for deciding which section to expand. A bare
 * `isActivePath` against the item's path alone left `/training` claimed by
 * nobody, so the rail lit nothing and folded the section the reader was
 * standing in.
 */
export function isActiveItem(navItem: NavItem, pathname: string): boolean {
  if (isActivePath(navItem.path, pathname)) return true;
  return (navItem.ownsPaths ?? []).some((owned) => isActivePath(owned, pathname));
}
