import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { PageHeader } from "../../components/ui";
import { visibleTiers } from "./tierAccess";

/**
 * The frame every dashboard tier renders inside: title, then the tab row
 * beneath it as a secondary control, then the tier's own content.
 *
 * The tabs sit under the title rather than above it because they are a
 * secondary choice within a named screen, not the screen's identity. They used
 * to be the first thing on the page, above a heading that then named a tier the
 * tab strip had already selected.
 *
 * Rendered only when the role is offered two or more tiers. A case manager has
 * exactly one, and a tab strip with a single tab is a control that cannot do
 * anything — it just tells them there is nowhere else to go.
 */
export default function TierPage({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  const { user } = useAuth();
  const { t } = useLang();
  const tiers = visibleTiers(user);

  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />

      {tiers.length > 1 && (
        <nav
          aria-label={t("nav.dashboard")}
          style={{ display: "flex", gap: 4, flexWrap: "wrap", borderBottom: "1px solid var(--line)" }}
        >
          {tiers.map((tier) => (
            <NavLink
              key={tier.path}
              to={`/dashboard/${tier.path}`}
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
              // The underline is a second channel beside the colour; this is
              // the third, and the one a screen reader hears.
              aria-current={undefined}
            >
              {t(tier.labelKey)}
            </NavLink>
          ))}
        </nav>
      )}

      {children}
    </>
  );
}
