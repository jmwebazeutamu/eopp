import { Drawer } from "antd";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import AccountPanel from "./AccountPanel";
import { buildModules, isActiveItem, isActivePath, type NavSection } from "./navModel";
import ScopeSelector from "./ScopeSelector";

/**
 * The phone's navigation: a labelled Menu button that opens a drawer holding
 * every module with its destinations, the woreda scope, and the account.
 *
 * It draws the same `buildModules` the desktop rows do. The drawer is antd's —
 * modal, focus-trapped, restores focus to the button, closes on Escape — which
 * is behaviour, and antd keeps the behaviour here. Every link closes it, so the
 * reader lands on the page rather than behind a sheet.
 */
export default function MobileNav({
  user,
  sections,
  pathname,
  onSignOut,
  onOpenProfile,
}: {
  user: CurrentUser;
  sections: NavSection[];
  pathname: string;
  onSignOut: () => void;
  onOpenProfile: () => void;
}) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const modules = buildModules(sections);

  // Resizing up to the desktop layout unmounts this; a route change closes it.
  useEffect(() => setOpen(false), [pathname]);

  return (
    <>
      <button
        type="button"
        className="menu-button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <Icon path={ICON_PATHS.menu} size={20} />
        {t("nav.menu")}
      </button>

      <Drawer
        placement="left"
        open={open}
        onClose={() => setOpen(false)}
        title={t("nav.menu")}
        size={320}
        styles={{ body: { padding: 12 } }}
      >
        <nav aria-label={t("nav.primary")}>
          {modules.map((module) => {
            const single = module.items.length === 0;
            return (
              <section key={module.key} className="drawer-module">
                {single ? (
                  <DrawerLink
                    to={module.landing}
                    label={t(module.labelKey)}
                    current={isActivePath(module.landing, pathname)}
                    strong
                  />
                ) : (
                  <>
                    <h3 className="drawer-heading">{t(module.labelKey)}</h3>
                    <ul>
                      {module.items.map((entry) => (
                        <li key={entry.path}>
                          <DrawerLink
                            to={entry.path}
                            label={t(entry.labelKey)}
                            current={isActiveItem(entry, pathname)}
                            badge={entry.badgeCount}
                          />
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </section>
            );
          })}
        </nav>

        <div className="drawer-scope">
          <ScopeSelector variant="sheet" />
        </div>

        <AccountPanel
          user={user}
          onSignOut={onSignOut}
          onOpenProfile={onOpenProfile}
          onNavigate={() => setOpen(false)}
        />
      </Drawer>
    </>
  );
}

function DrawerLink({
  to,
  label,
  current,
  badge,
  strong,
}: {
  to: string;
  label: string;
  current: boolean;
  badge?: number;
  strong?: boolean;
}) {
  return (
    <Link
      to={to}
      className="drawer-link"
      aria-current={current ? "page" : undefined}
      data-current={current ? "true" : undefined}
      style={strong ? { fontWeight: 700 } : undefined}
    >
      {label}
      {badge ? <span className="count-badge">{badge}</span> : null}
    </Link>
  );
}
