import type { CurrentUser, Role } from "../../api/types";
import type { StringKey } from "../../i18n/strings";

/**
 * Which WLT dashboard tier a role is offered.
 *
 * Four small dashboards, not one with role-based hiding — the same call the
 * youth bundle makes and for the same reason: a single dashboard with
 * permissions converges on the union of every stakeholder\'s requirements, and
 * the facilitator ends up reading donor indicators.
 *
 * Gated by role rather than by `group_scope`, the deliberate exception
 * `TIER_ACCESS` already records. The distinction is not "what may you read" but
 * "what is this screen for": a woreda officer and a region officer share a
 * scope and want different dashboards.
 *
 * Not the security boundary. Every tier is scoped server-side through
 * `scope_group_queryset`, so hiding a tab only avoids offering somebody a
 * screen that is not theirs.
 */

export interface WltTier {
  path: string;
  labelKey: StringKey;
  titleKey: StringKey;
  whyKey: StringKey;
}

export const WLT_TIERS: WltTier[] = [
  { path: "home", labelKey: "wlt.tierHome", titleKey: "wlt.homeTitle", whyKey: "wlt.tierHomeWhy" },
  { path: "woreda", labelKey: "wlt.tierWoreda", titleKey: "wlt.tierWoredaFull", whyKey: "wlt.tierWoredaWhy" },
  { path: "programme", labelKey: "wlt.tierProgramme", titleKey: "wlt.tierProgrammeFull", whyKey: "wlt.tierProgrammeWhy" },
  { path: "results", labelKey: "wlt.tierResults", titleKey: "wlt.tierResultsFull", whyKey: "wlt.tierResultsWhy" },
];

export const WLT_TIER_ACCESS: Partial<Record<Role, string[]>> = {
  // She records the work, so she gets the queue and nothing above it. No
  // cross-group comparison, no regional aggregate — the handoff deletes both
  // from this tier.
  WLT_FACILITATOR: ["home"],
  // Her own queue too: she approves phase moves, and the approval card is her
  // job. Plus the tactical view she is the audience for.
  WLT_WOREDA_OFFICER: ["home", "woreda"],
  WLT_REGION_OFFICER: ["woreda", "programme", "results"],
  WLT_FEDERAL_OFFICER: ["woreda", "programme", "results"],
  SYSTEM_ADMIN: ["home", "woreda", "programme", "results"],
};

export function visibleWltTiers(user: Pick<CurrentUser, "role"> | null | undefined): WltTier[] {
  const allowed = user ? (WLT_TIER_ACCESS[user.role] ?? []) : [];
  // Ordered by WLT_TIERS, so the tab strip and the rail always read the same
  // way whatever order a role\'s row happens to list.
  return WLT_TIERS.filter((tier) => allowed.includes(tier.path));
}

export function canSeeWltTier(user: Pick<CurrentUser, "role"> | null | undefined, path: string): boolean {
  return visibleWltTiers(user).some((tier) => tier.path === path);
}

export function landingWltTier(user: Pick<CurrentUser, "role"> | null | undefined): WltTier | null {
  return visibleWltTiers(user)[0] ?? null;
}
