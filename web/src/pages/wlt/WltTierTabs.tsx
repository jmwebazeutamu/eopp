import { NavLink } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { visibleWltTiers } from "./wltTiers";

/**
 * The tab row shared by the four WLT dashboard tiers.
 *
 * Under the title, the same placement `TierPage` and `DeliveryTabs` use — the
 * tabs are a secondary choice within a named screen, not the screen's identity.
 *
 * Rendered only when the role has two or more. A facilitator has exactly one,
 * and a strip with a single tab only tells her there is nowhere else to go.
 */
export default function WltTierTabs() {
  const { user } = useAuth();
  const { t } = useLang();
  const tiers = visibleWltTiers(user);

  if (tiers.length < 2) return null;

  return (
    <nav
      aria-label={t("nav.wltDashboard")}
      style={{ display: "flex", gap: 4, flexWrap: "wrap", borderBottom: "1px solid var(--line)" }}
    >
      {tiers.map((tier) => (
        <NavLink
          key={tier.path}
          to={`/wlt/dashboard/${tier.path}`}
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
  );
}
