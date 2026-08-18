import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import type { StringKey } from "../../i18n/strings";

/**
 * The four tiers, as a submenu under Dashboard.
 *
 * `dashboard_handoff_youth_employment/README.md` §1: four small dashboards, not
 * one with role-based hiding. A single dashboard with permissions always
 * converges on the union of every stakeholder's requirements, and the case
 * manager ends up looking at donor indicators.
 *
 * So the tabs are gated as well as the data. Every tier is §7-scoped server-side
 * regardless — hiding a tab only avoids offering someone a screen that is not
 * theirs to read, it is not the security boundary.
 */

export interface Tier {
  path: string;
  labelKey: StringKey;
  titleKey: StringKey;
  whyKey: StringKey;
  /** Who this tier is for, read off the §7 access row rather than the role. */
  visible: (scope: string, canWrite: boolean) => boolean;
}

export const TIERS: Tier[] = [
  {
    path: "my-work",
    labelKey: "tier.myWork",
    titleKey: "tier.myWorkFull",
    whyKey: "tier.myWorkWhy",
    // Anyone with a caseload of their own to work.
    visible: () => true,
  },
  {
    path: "woreda",
    labelKey: "tier.woreda",
    titleKey: "tier.woredaFull",
    whyKey: "tier.woredaWhy",
    visible: (scope) => scope === "OWN_WOREDA" || scope === "ALL",
  },
  {
    path: "programme",
    labelKey: "tier.programme",
    titleKey: "tier.programmeFull",
    whyKey: "tier.programmeWhy",
    // Supervisory and above. A case manager reading programme conversion rates
    // is the cream-skimming pressure the handoff warns about.
    visible: (scope, canWrite) => scope === "ALL" || (scope === "OWN_WOREDA" && !canWrite),
  },
  {
    path: "results",
    labelKey: "tier.results",
    titleKey: "tier.resultsFull",
    whyKey: "tier.resultsWhy",
    visible: (scope) => scope === "ALL",
  },
];

export function visibleTiers(scope: string, canWrite: boolean): Tier[] {
  return TIERS.filter((tier) => tier.visible(scope, canWrite));
}

export default function DashboardLayout() {
  const { user } = useAuth();
  const { t } = useLang();
  const tiers = visibleTiers(user?.access.case_scope ?? "", user?.access.case_write ?? false);

  return (
    <div className="page stack">
      {/* A tab strip, not a second nav rail: these are four views of one thing,
          and the brief's breakpoint budget has no room for nested navigation. */}
      <nav
        aria-label={t("nav.dashboard")}
        style={{ display: "flex", gap: 4, flexWrap: "wrap", borderBottom: "1px solid var(--line)" }}
      >
        {tiers.map((tier) => (
          <NavLink
            key={tier.path}
            to={tier.path}
            style={({ isActive }) => ({
              padding: "10px 14px",
              minHeight: 44,
              display: "flex",
              alignItems: "center",
              fontWeight: 600,
              fontSize: 14,
              textDecoration: "none",
              color: isActive ? "var(--green-900)" : "var(--ink-600)",
              borderBottom: `3px solid ${isActive ? "var(--green-500)" : "transparent"}`,
              marginBottom: -1,
            })}
          >
            {t(tier.labelKey)}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  );
}
