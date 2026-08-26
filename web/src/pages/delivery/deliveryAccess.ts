import type { CurrentUser, Role } from "../../api/types";
import type { StringKey } from "../../i18n/strings";

/**
 * Which delivery screens a role is offered.
 *
 * Four rail rows became one. Training, Placements, Enterprises and Verification
 * are four screens that are each a single queue, and putting them side by side
 * in the rail spent four of its nine PSNP rows on work most roles never do.
 * They are tabs now, on the same pattern as the dashboard tiers.
 *
 * **The narrowing is the more useful half.** The rail offered all four to
 * anybody with case content, so a trainer was shown Placements, Enterprises and
 * Verification — three screens that, scoped through `LINKED_THROUGH`, return
 * her nothing at all. This table says what the server already knew:
 * `TRAINER → training_enrolments__recorded_by`,
 * `EMPLOYER_LIAISON → placements__recorded_by`,
 * `ENTERPRISE_OFFICER → enterprises__recorded_by`.
 *
 * Gated by role rather than by the §7 scope columns, the same deliberate
 * exception `TIER_ACCESS` makes and for the same reason: the question is not
 * "what may you read" but "what is this screen for". A supervisor and a trainer
 * both have case content and want different screens.
 *
 * Not the security boundary. Every one of these endpoints is §7-scoped
 * server-side and out-of-scope records 404, so hiding a tab only avoids
 * offering somebody a screen that would come back empty.
 */

export interface DeliveryScreen {
  /** The route, unchanged from when these were four rail items. Links and
   *  bookmarks that predate the tabs still work. */
  path: string;
  labelKey: StringKey;
}

export const DELIVERY_SCREENS: DeliveryScreen[] = [
  { path: "/training", labelKey: "nav.training" },
  { path: "/placements", labelKey: "nav.placements" },
  { path: "/enterprises", labelKey: "nav.enterprises" },
  { path: "/verification", labelKey: "nav.verification" },
];

const ALL = DELIVERY_SCREENS.map((screen) => screen.path);

export const DELIVERY_ACCESS: Record<Role, string[]> = {
  // Roles that carry or oversee a caseload see all four: they record against
  // every one of them, or they read a woreda's worth of all of them.
  OUTREACH_WORKER: ALL,
  CASE_MANAGER: ALL,
  SUPERVISOR: ALL,
  PROGRAMME_MANAGER: ALL,
  SYSTEM_ADMIN: ALL,
  // Verification is M&E's own screen — §8.3 makes the externally verified
  // subset the reportable headline — and she reads the other three.
  MNE_STAFF: ALL,

  // The LINKED roles, each narrowed to the entity they are linked through.
  // Offering the other three showed them empty tables and taught them the
  // application was broken.
  TRAINER: ["/training"],
  EMPLOYER_LIAISON: ["/placements"],
  ENTERPRISE_OFFICER: ["/enterprises"],

  // Partner staff see referrals and no case content; there is nothing here for
  // them. The WLT roles carry `case_scope: NONE` — these four screens count
  // youth-side delivery, and a savings-group facilitator has no caseload at
  // all. Her module's screens are under /wlt.
  PARTNER_STAFF: [],
  WLT_FACILITATOR: [],
  WLT_WOREDA_OFFICER: [],
  WLT_REGION_OFFICER: [],
  WLT_FEDERAL_OFFICER: [],
};

export function visibleDelivery(user: Pick<CurrentUser, "role"> | null | undefined): DeliveryScreen[] {
  const allowed = user ? (DELIVERY_ACCESS[user.role] ?? []) : [];
  // Ordered by `DELIVERY_SCREENS`, not by the table, so the tab row always
  // reads left to right in one order whatever order a row happens to list.
  return DELIVERY_SCREENS.filter((screen) => allowed.includes(screen.path));
}

export function canSeeDelivery(user: Pick<CurrentUser, "role"> | null | undefined, path: string): boolean {
  return visibleDelivery(user).some((screen) => screen.path === path);
}

/** Where `/delivery` lands this role, or null when it has none. */
export function landingDelivery(user: Pick<CurrentUser, "role"> | null | undefined): DeliveryScreen | null {
  return visibleDelivery(user)[0] ?? null;
}
