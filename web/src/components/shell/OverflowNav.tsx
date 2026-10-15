import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import { splitOverflow } from "./navOverflow";

export interface OverflowLink {
  key: string;
  to: string;
  label: string;
  /** This link is the page the reader is on. */
  current: boolean;
  /** This link is the module the reader is in, without being the page (primary row). */
  inside?: boolean;
  badge?: number;
}

/** Space between links; mirrors `.topnav-list` in base.css. */
const GAP = 4;

/**
 * One row of links that never clips.
 *
 * Whatever does not fit moves behind a "More" disclosure *before* it would
 * collide, and the link for the current page is kept on the row — an active
 * destination hidden in a menu is a reader who has lost their place. The same
 * component draws the primary and secondary rows, so overflow is decided in one
 * place.
 *
 * Widths come from a hidden copy of the row (`visibility: hidden`, so it is out
 * of the tab order and the accessibility tree), measured again when the row
 * resizes or the labels change. Where nothing can be measured — jsdom — every
 * link is shown.
 */
export default function OverflowNav({
  label,
  links,
  variant,
}: {
  label: string;
  links: OverflowLink[];
  variant: "primary" | "secondary";
}) {
  const { t } = useLang();
  const location = useLocation();
  const menuId = useId();
  const row = useRef<HTMLDivElement>(null);
  const measure = useRef<HTMLDivElement>(null);
  const more = useRef<HTMLButtonElement>(null);
  const [overflow, setOverflow] = useState<number[]>([]);
  const [open, setOpen] = useState(false);

  const signature = links.map((link) => `${link.key}:${link.label}:${link.badge ?? 0}`).join("|");
  const pinned = links.findIndex((link) => link.current || link.inside);

  useLayoutEffect(() => {
    const compute = () => {
      if (!row.current || !measure.current) return;
      const cells = Array.from(measure.current.querySelectorAll<HTMLElement>("[data-measure]"));
      const widths = cells.slice(0, links.length).map((cell) => cell.offsetWidth);
      const moreWidth = cells[links.length]?.offsetWidth ?? 0;
      const available = row.current.clientWidth;
      if (available === 0) return;
      const split = splitOverflow(widths, available, moreWidth, GAP, pinned >= 0 ? pinned : null);
      setOverflow((was) => (was.join() === split.overflow.join() ? was : split.overflow));
    };
    compute();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(compute);
    if (row.current) observer?.observe(row.current);
    // Web fonts change every width once they arrive.
    void document.fonts?.ready.then(compute);
    return () => observer?.disconnect();
  }, [signature, pinned, links.length]);

  // Navigating closes the menu, whichever way the navigation happened.
  useEffect(() => setOpen(false), [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      more.current?.focus();
    };
    const onPointer = (event: MouseEvent) => {
      if (!row.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [open]);

  const hidden = new Set(overflow);
  const shown = links.filter((_, i) => !hidden.has(i));
  const tucked = links.filter((_, i) => hidden.has(i));
  const moreHoldsCurrent = tucked.some((link) => link.current || link.inside);

  return (
    <nav aria-label={label} className={`topnav topnav-${variant}`}>
      <div className="topnav-inner" ref={row}>
        <ul className="topnav-list">
          {shown.map((link) => (
            <li key={link.key}>
              <NavAnchor link={link} />
            </li>
          ))}
          {tucked.length > 0 && (
            <li className="topnav-more">
              <button
                ref={more}
                type="button"
                className="topnav-link"
                data-current={moreHoldsCurrent ? "true" : undefined}
                aria-expanded={open}
                aria-controls={menuId}
                onClick={() => setOpen((was) => !was)}
              >
                {t("nav.more")}
                <Icon path={ICON_PATHS.chevronDown} size={12} />
              </button>
              {open && (
                <ul id={menuId} className="topnav-menu">
                  {tucked.map((link) => (
                    <li key={link.key}>
                      <NavAnchor link={link} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          )}
        </ul>

        {/* Measuring copy. visibility:hidden keeps it out of focus order and the
            accessibility tree, so no second set of links is exposed. */}
        <div className="topnav-measure" ref={measure} aria-hidden="true">
          {links.map((link) => (
            <span key={link.key} data-measure className="topnav-link">
              {link.label}
              {link.badge ? <span className="count-badge">{link.badge}</span> : null}
            </span>
          ))}
          <span data-measure className="topnav-link">
            {t("nav.more")}
            <Icon path={ICON_PATHS.chevronDown} size={12} />
          </span>
        </div>
      </div>
    </nav>
  );
}

function NavAnchor({ link }: { link: OverflowLink }) {
  return (
    <Link
      to={link.to}
      className="topnav-link"
      // The page itself is `page`; a module you are merely inside is `true`, so
      // an ancestor is never announced as the page.
      aria-current={link.current ? "page" : link.inside ? "true" : undefined}
      data-current={link.current || link.inside ? "true" : undefined}
    >
      {link.label}
      {link.badge ? <span className="count-badge">{link.badge}</span> : null}
    </Link>
  );
}
