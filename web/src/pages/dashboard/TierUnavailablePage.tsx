import { useLocation } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { useLang } from "../../i18n/LanguageContext";
import { Card, PageHeader } from "../../components/ui";
import { TIERS, landingTier, visibleTiers } from "./tierAccess";

/**
 * What a deep link into a tier the role does not cover renders.
 *
 * Not a redirect: bouncing someone from a link a colleague sent them to a
 * different screen, silently, is how people conclude the link was broken. It
 * also risks a loop, since the tier they would be sent to may itself redirect.
 * So this states plainly which screen was asked for, that their role does not
 * cover it, and where they can go instead.
 */
export default function TierUnavailablePage() {
  const { user } = useAuth();
  const { t } = useLang();
  const location = useLocation();

  const requested = TIERS.find((tier) => location.pathname.endsWith(`/${tier.path}`));
  const available = visibleTiers(user);
  const landing = landingTier(user);

  return (
    <>
      <PageHeader
        title={requested ? t(requested.titleKey) : t("tier.unavailableTitle")}
        subtitle={t("tier.unavailableRole", { role: user?.role_display ?? "" })}
      />
      <Card>
        <p style={{ margin: 0 }}>{t("tier.unavailableBody")}</p>
        {available.length > 0 && landing ? (
          <p style={{ marginTop: 12, marginBottom: 0 }}>
            {t("tier.unavailableAlternatives", { tiers: available.map((tier) => t(tier.labelKey)).join(", ") })}
          </p>
        ) : (
          <p style={{ marginTop: 12, marginBottom: 0 }}>{t("tier.unavailableNone")}</p>
        )}
      </Card>
    </>
  );
}
