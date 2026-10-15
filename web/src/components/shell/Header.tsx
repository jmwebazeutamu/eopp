import { useState } from "react";
import { Link } from "react-router-dom";

import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import GlobalSearch from "./GlobalSearch";
import ScopeSelector from "./ScopeSelector";

/**
 * The application header: brand, global search, woreda scope, account.
 *
 * Desktop carries all four. On a phone the bar holds the brand, a search
 * button (a 480px field and a scope select cannot share 390px; the search opens
 * over the bar instead) and whatever the shell passes as `menu` — the labelled
 * Menu button — while scope and account move into the drawer.
 */
export default function Header({
  isPhone = false,
  menu,
  account,
}: {
  isPhone?: boolean;
  menu?: React.ReactNode;
  account?: React.ReactNode;
}) {
  const { t } = useLang();
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className="app-header on-dark" data-phone={isPhone || undefined}>
      <div className="app-header-inner">
      <Link to="/" className="app-brand">
        <span className="app-brand-mark">{t("shell.appMark")}</span>
        <span className="app-brand-name">{t("app.name")}</span>
      </Link>

      {isPhone ? (
        searchOpen ? (
          <div className="app-search-sheet">
            <GlobalSearch autoFocus />
            <button type="button" className="icon-button" onClick={() => setSearchOpen(false)} aria-label={t("common.close")}>
              {"✕"}
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              className="icon-button app-spacer"
              onClick={() => setSearchOpen(true)}
              aria-label={t("search.label")}
            >
              <Icon path={ICON_PATHS.search} size={20} />
            </button>
            {menu}
          </>
        )
      ) : (
        <>
          <div className="app-search">
            <GlobalSearch />
          </div>
          <div className="app-scope">
            <ScopeSelector />
          </div>
          {account}
        </>
      )}
      </div>
    </header>
  );
}
