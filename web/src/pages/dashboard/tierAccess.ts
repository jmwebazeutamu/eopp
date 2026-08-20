import type { CurrentUser, Role } from "../../api/types";
import type { StringKey } from "../../i18n/strings";

/**
 * Which dashboard tiers a role is offered.
 *
 * `dashboard_handoff_youth_employment/README.md` §1: four small dashboards, not
 * one with role-based hiding. A single dashboard with permissions converges on
 * the union of every stakeholder's requirements, and the case manager ends up
 * reading donor indicators.
 *
 * Gated by role rather than by the §7 scope columns, which is a deliberate
 * exception to the repository rule that visibility follows `ACCESS_MATRIX`.
 * The distinction the tiers draw is not "what may you read" but "what is this
 * screen for": a programme manager and a system administrator share
 * `case_scope: ALL` and want different dashboards, while a supervisor and an
 * outreach worker share `OWN_WOREDA` and also want different ones. Scope cannot
 * express that, and the previous scope-based rule proved it by handing the
 * programme tier to supervisors through a `!case_write` test that was really
 * standing in for a role.
 *
 * This is still one table in one place, not a role test at a call site. And it
 * is not the security boundary: every tier endpoint is §7-scoped server-side,
 * so hiding a tab only avoids offering someone a screen that is not theirs.
 */

export interface Tier {
  path: string;
  labelKey: StringKey;
  titleKey: StringKey;
  whyKey: StringKey;
}

export const TIERS: Tier[] = [
  { path: "my-work", labelKey: "tier.myWork", titleKey: "tier.myWorkFull", whyKey: "tier.myWorkWhy" },
  { path: "woreda", labelKey: "tier.woreda", titleKey: "tier.woredaFull", whyKey: "tier.woredaWhy" },
  { path: "programme", labelKey: "tier.programme", titleKey: "tier.programmeFull", whyKey: "tier.programmeWhy" },
  { path: "results", labelKey: "tier.results", titleKey: "tier.resultsFull", whyKey: "tier.resultsWhy" },
];

/**
 * The role table.
 *
 * The four rows the brief names, plus the six roles it does not. Those six are
 * decided by whether the role has a case population of its own to look at:
 * an outreach worker carries a caseload and gets My work; the four LINKED roles
 * — trainer, employer liaison, enterprise officer, partner staff — see
 * individual referrals but never a denominator, so a programme total would be
 * meaningless rather than merely empty, and they get no dashboard at all.
 */
export const TIER_ACCESS: Record<Role, string[]> = {
  OUTREACH_WORKER: ["my-work"],
  CASE_MANAGER: ["my-work"],
  SUPERVISOR: ["my-work", "woreda"],
  PROGRAMME_MANAGER: ["woreda", "programme", "results"],
  MNE_STAFF: ["woreda", "programme", "results"],
  SYSTEM_ADMIN: ["my-work", "woreda", "programme", "results"],
  TRAINER: [],
  EMPLOYER_LIAISON: [],
  ENTERPRISE_OFFICER: [],
  PARTNER_STAFF: [],
  // The WLT roles get none of the four youth tiers. Not an omission: these
  // dashboards count cases, referrals and placements, and a savings-group
  // facilitator has no case population at all. The module's own screens are
  // under /wlt.
  WLT_FACILITATOR: [],
  WLT_WOREDA_OFFICER: [],
  WLT_REGION_OFFICER: [],
  WLT_FEDERAL_OFFICER: [],
};

export function visibleTiers(user: Pick<CurrentUser, "role"> | null | undefined): Tier[] {
  const allowed = user ? (TIER_ACCESS[user.role] ?? []) : [];
  // Ordered by TIERS, not by the table, so the tab row and the rail always read
  // in the same left-to-right order whatever order a row happens to list.
  return TIERS.filter((tier) => allowed.includes(tier.path));
}

export function canSeeTier(user: Pick<CurrentUser, "role"> | null | undefined, path: string): boolean {
  return visibleTiers(user).some((tier) => tier.path === path);
}

/**
 * Where `/dashboard` lands.
 *
 * The first tier the role is offered, which by the ordering above is the most
 * personal one it has: a case manager gets their own work, a programme manager
 * gets their woreda comparison, a donor-facing administrator can still reach
 * results in one click. Sending everyone to the same tier is how one dashboard
 * ends up serving four audiences badly.
 */
export function landingTier(user: Pick<CurrentUser, "role"> | null | undefined): Tier | null {
  return visibleTiers(user)[0] ?? null;
}
