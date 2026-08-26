import { useNavigate } from "react-router-dom";

import { useAuth } from "../../auth/AuthContext";
import { Button, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import { visibleWltTiers } from "./wltTiers";

/**
 * A WLT tier this role is not offered.
 *
 * **Explained in place, never redirected.** Bouncing somebody off a link a
 * colleague sent them reads as a broken link, and the tier they would be
 * bounced to may redirect in turn.
 *
 * Its own component rather than the youth `TierUnavailablePage`, which was
 * reached first and told a woreda officer that her role has no dashboard and
 * that she works from "the case, referral and alert lists". Both halves are
 * false: she has a dashboard, and every WLT role carries `case_scope: NONE`, so
 * those three screens are exactly the ones she cannot open. A refusal that
 * misdirects is worse than a bare 403.
 */
export default function WltTierUnavailable() {
  const { user } = useAuth();
  const { t } = useLang();
  const navigate = useNavigate();
  const mine = visibleWltTiers(user);

  return (
    <div className="page stack">
      <div>
        <h1 className="group-title">{t("wlt.tierUnavailable")}</h1>
        <p className="t-meta" style={{ margin: "4px 0 0" }}>
          {t("wlt.tierUnavailableRole", { role: user?.role_display ?? "" })}
        </p>
      </div>

      <Card>
        <p style={{ marginTop: 0 }}>{t("wlt.tierUnavailableBody")}</p>
        {mine.length > 0 ? (
          <>
            <p className="t-meta">{t("wlt.tierUnavailableYours")}</p>
            <div className="chip-row">
              {mine.map((entry) => (
                <Button key={entry.path} onClick={() => navigate(`/wlt/dashboard/${entry.path}`)}>
                  {t(entry.labelKey)}
                </Button>
              ))}
            </div>
          </>
        ) : (
          // Never "use the case lists": every WLT role carries `case_scope:
          // NONE`, so those are the screens she cannot open.
          <p className="t-meta">{t("wlt.tierUnavailableNone")}</p>
        )}
      </Card>
    </div>
  );
}
