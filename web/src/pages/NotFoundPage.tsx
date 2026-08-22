import { useLocation, useNavigate } from "react-router-dom";

import { Button, Card, PageHeader } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

/**
 * An unknown URL says so (defect D16).
 *
 * This used to redirect silently to the home route, which made every
 * URL-tampering permission test unreadable: "you may not see this record" and
 * "there is no such page" produced exactly the same screen, so a scoping
 * failure and a typo were indistinguishable.
 *
 * It deliberately does not guess what was meant. A record the caller may not
 * see 404s on the API by design — the API does not confirm that an
 * out-of-scope record exists — so a page that offered "did you mean…" would
 * leak the very thing that rule protects.
 */
export default function NotFoundPage() {
  const { t } = useLang();
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="page stack">
      <PageHeader title={t("notFound.title")} subtitle={t("notFound.subtitle")} />
      <Card>
        <p style={{ marginTop: 0 }}>{t("notFound.body")}</p>
        <p className="t-meta">
          <code>{location.pathname}</code>
        </p>
        <Button variant="primary" onClick={() => navigate("/")}>
          {t("notFound.home")}
        </Button>
      </Card>
    </div>
  );
}
