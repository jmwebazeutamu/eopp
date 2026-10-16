import { Link } from "react-router-dom";

import { useLang } from "../../i18n/LanguageContext";

/** The footer on every signed-in page: orientation, help, and the data-protection reminder. */
export default function Footer({ clearance = 0 }: { clearance?: number }) {
  const { t } = useLang();
  const year = new Date().getFullYear();

  return (
    <footer
      className="app-footer"
      aria-label={t("footer.label")}
      style={clearance ? { paddingBottom: `calc(20px + ${clearance}px)` } : undefined}
    >
      <div className="app-footer__inner">
        <div className="app-footer__grid">
          <div>
            <Link to="/" className="app-footer__brand">
              {t("shell.appMark")}
            </Link>
            <p>{t("app.name")}</p>
          </div>
          <section>
            <h2>{t("footer.programmes")}</h2>
            <ul>
              <li>{t("footer.youth")}</li>
              <li>{t("footer.wlt")}</li>
            </ul>
          </section>
          <section>
            <h2>{t("footer.support")}</h2>
            <ul>
              <li>
                <a href="/manual.html" target="_blank" rel="noreferrer">
                  {t("footer.manual")}
                  <span className="sr-only"> {t("shell.opensNewTab")}</span>
                </a>
              </li>
              <li>
                <a href="/healthz/">{t("footer.status")}</a>
              </li>
            </ul>
          </section>
          <section>
            <h2>{t("footer.account")}</h2>
            <p>{t("footer.accountBody")}</p>
          </section>
        </div>
        <div className="app-footer__bottom">
          <p>{t("footer.privacy")}</p>
          <p>{t("footer.copyright").replace("{year}", String(year))}</p>
        </div>
      </div>
    </footer>
  );
}
