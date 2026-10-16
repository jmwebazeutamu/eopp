import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import { activeModule, buildModules, isActiveItem, isActivePath, type NavModule, type NavSection } from "./navModel";

/**
 * The horizontal navigation: one row of modules, with each module's
 * destinations in a dropdown panel beneath it.
 *
 * Reads `buildNav` through `buildModules`, the single place that decides what a
 * role is offered. The current module and page are derived from the URL on every
 * render, so a refresh, a deep link and Back all land on the right highlight
 * with no state to drift. Only "which panel is open" is state, and it is local.
 *
 * A module with one destination is an ordinary link. One with several is a
 * disclosure button — a nonmodal panel of real links, never hover-only, with no
 * focus trap: Tab walks through the links and out the far side.
 */
export default function TopNav({ sections, pathname }: { user?: CurrentUser; sections: NavSection[]; pathname: string }) {
  const { t } = useLang();
  const location = useLocation();
  const modules = buildModules(sections);
  const current = activeModule(modules, sections, pathname);
  const root = useRef<HTMLElement>(null);
  const [openKey, setOpenKey] = useState<string | null>(null);

  // Navigating closes the panel, whichever way the navigation happened.
  useEffect(() => setOpenKey(null), [location.pathname]);

  useEffect(() => {
    if (!openKey) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpenKey(null);
      root.current?.querySelector<HTMLElement>(`[data-trigger="${CSS.escape(openKey)}"]`)?.focus();
    };
    const onPointer = (event: MouseEvent | TouchEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpenKey(null);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("touchstart", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("touchstart", onPointer);
    };
  }, [openKey]);

  return (
    <nav aria-label={t("nav.primary")} className="topnav" ref={root}>
      <div className="topnav-inner">
        <ul className="topnav-list">
          {modules.map((module) => {
            const inside = current?.key === module.key;
            return (
              <li key={module.key} className="topnav-item">
                {module.items.length === 0 ? (
                  <Link
                    to={module.landing}
                    className="topnav-link"
                    aria-current={isActivePath(module.landing, pathname) ? "page" : undefined}
                    data-current={inside || undefined}
                  >
                    {t(module.labelKey)}
                    {module.badgeCount ? <span className="count-badge">{module.badgeCount}</span> : null}
                  </Link>
                ) : (
                  <Dropdown
                    module={module}
                    pathname={pathname}
                    inside={inside}
                    open={openKey === module.key}
                    onToggle={() => setOpenKey((was) => (was === module.key ? null : module.key))}
                  />
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

function Dropdown({
  module,
  pathname,
  inside,
  open,
  onToggle,
}: {
  module: NavModule;
  pathname: string;
  inside: boolean;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useLang();
  const panelId = useId();
  const panel = useRef<HTMLUListElement>(null);
  const [alignEnd, setAlignEnd] = useState(false);

  // Keep the panel inside the viewport: anchor to the trigger's left edge, and
  // flip to its right edge when that would run off the screen.
  useLayoutEffect(() => {
    if (!open || !panel.current) return;
    const rect = panel.current.getBoundingClientRect();
    const trigger = panel.current.parentElement?.getBoundingClientRect();
    if (!trigger) return;
    setAlignEnd(trigger.left + rect.width > window.innerWidth - 8);
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="topnav-link"
        data-trigger={module.key}
        data-current={inside || undefined}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
      >
        {t(module.labelKey)}
        {module.badgeCount ? <span className="count-badge">{module.badgeCount}</span> : null}
        <Icon path={ICON_PATHS.chevronDown} size={12} />
      </button>
      {/* Not rendered when closed, so nothing hidden can take focus. */}
      {open && (
        <ul id={panelId} ref={panel} className="topnav-menu" data-align={alignEnd ? "end" : undefined}>
          {module.items.map((entry) => {
            const page = isActiveItem(entry, pathname);
            return (
              <li key={entry.path}>
                <Link
                  to={entry.path}
                  className="topnav-menu-link"
                  aria-current={page ? "page" : undefined}
                  data-current={page || undefined}
                >
                  {t(entry.labelKey)}
                  {entry.badgeCount ? <span className="count-badge">{entry.badgeCount}</span> : null}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
