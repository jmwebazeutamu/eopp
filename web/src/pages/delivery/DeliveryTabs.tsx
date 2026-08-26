import { NavLink } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { visibleDelivery } from "./deliveryAccess";

/**
 * The tab row shared by the four delivery screens.
 *
 * Under the title rather than above it, the same rule `TierPage` follows: the
 * tabs are a secondary choice within a named screen, not the screen's identity.
 *
 * **Rendered only when the role has two or more.** A trainer has exactly one,
 * and a tab strip with a single tab is a control that cannot do anything — it
 * only tells her there is nowhere else to go.
 */
export default function DeliveryTabs() {
  const { user } = useAuth();
  const { t } = useLang();
  const screens = visibleDelivery(user);

  if (screens.length < 2) return null;

  return (
    <nav
      aria-label={t("nav.delivery")}
      style={{ display: "flex", gap: 4, flexWrap: "wrap", borderBottom: "1px solid var(--line)" }}
    >
      {screens.map((screen) => (
        <NavLink
          key={screen.path}
          to={screen.path}
          style={({ isActive }) => ({
            padding: "10px 14px",
            minHeight: 44,
            display: "flex",
            alignItems: "center",
            fontWeight: 600,
            fontSize: 14,
            textDecoration: "none",
            color: isActive ? "var(--green-900)" : "var(--ink-600)",
            // The underline is a second channel beside the colour, so the
            // selected tab survives a monochrome screen.
            borderBottom: `3px solid ${isActive ? "var(--green-500)" : "transparent"}`,
            marginBottom: -1,
          })}
        >
          {t(screen.labelKey)}
        </NavLink>
      ))}
    </nav>
  );
}
