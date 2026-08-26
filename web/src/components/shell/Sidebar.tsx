import { Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { useSessionPreference } from "./preferences";
import { Icon, ICON_PATHS } from "../ui";
import GlobalSearch from "./GlobalSearch";
import { ALERT_BADGE_ATTENTION_AT, isActiveItem, type NavSection } from "./navModel";
import ScopeSelector from "./ScopeSelector";

/**
 * The navigation rail.
 *
 * 240px expanded, 64px icon-only collapsed. The old rail was 236px of dark
 * panel headed by a "Case / Case Management" block that named the product a
 * second time and linked nowhere; that space now goes to the sections.
 *
 * Two rules from the handoff apply here and are the reason this is not a plain
 * antd `Menu`:
 *  - never colour alone — the active item carries a filled background *and* a
 *    3px left rule *and* `aria-current="page"`, so it survives a monochrome
 *    screen and announces itself to a screen reader;
 *  - collapsed items keep their accessible name through the tooltip's
 *    `aria-label`, so the rail stays usable by keyboard at either width.
 *
 * The rail fills the shell row. The controls at its head and foot stay pinned,
 * while the section list between them scrolls: a longer nav must not push the
 * account menu or sign-out control out of reach.
 */

export const RAIL_EXPANDED = 232;
export const RAIL_COLLAPSED = 60;

interface SidebarProps {
  user: CurrentUser;
  sections: NavSection[];
  pathname: string;
  collapsed: boolean;
  onToggleCollapse: () => void;
  /** Rendered at the foot. The user menu lands here in item 3. */
  footer?: React.ReactNode;
}

export default function Sidebar({
  user,
  sections,
  pathname,
  collapsed,
  onToggleCollapse,
  footer,
}: SidebarProps) {
  const { t } = useLang();
  const navigate = useNavigate();
  /**
   * Which sections the reader has opened, this sitting only.
   *
   * **Everything starts closed.** Four open sections put fifteen items in the
   * rail, which is a list to read rather than a place to navigate — and the one
   * a reader wants is somewhere in the middle of it. Closed by default makes the
   * rail a set of four choices.
   *
   * Session-scoped rather than remembered for good: "collapsed on load" is the
   * specified behaviour, so a lasting preference would defeat it from the second
   * visit onwards. Within one sitting, a section stays as it was left.
   */
  const [openSections, setOpenSections] = useSessionPreference<Record<string, boolean>>(
    "nav.openSections",
    user.id,
    {},
  );

  const activeKey = sectionKey(
    sections.find((section) => section.items.some((entry) => isActiveItem(entry, pathname))),
  );

  /**
   * A section is open when the reader opened it, or when the page they are on
   * lives in it.
   *
   * Derived rather than written into state on navigation. Storing it would mean
   * that arriving at a page and then leaving it leaves the section open behind
   * you — the rail slowly reverting to the fully-expanded list this replaces.
   * An explicit close still wins: `false` in the record beats being active, so
   * somebody who shuts the section they are standing in gets what they asked for.
   */
  function isOpen(section: NavSection) {
    const key = sectionKey(section);
    if (key in openSections) return openSections[key];
    return key === activeKey;
  }

  return (
    <nav
      className="on-dark"
      aria-label={t("nav.primary")}
      style={{
        width: collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED,
        flexShrink: 0,
        background: "var(--rail-bg)",
        color: "var(--on-dark)",
        display: "flex",
        flexDirection: "column",
        padding: 0,
        gap: 0,
        transition: "width 120ms ease",
        height: "100%",
        minHeight: 0,
      }}
    >
      {!collapsed ? (
        <div style={{ padding: "14px 16px 10px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.01em", color: "#ffffff", lineHeight: 1.2, maxWidth: 150 }}>
            {t("app.name")}
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-expanded={!collapsed}
            aria-label={t("nav.collapse")}
            title={t("nav.collapse")}
            style={railToggleButtonStyle}
          >
            <Icon path={ICON_PATHS.railCollapse} size={14} />
          </button>
        </div>
      ) : (
        <div style={{ display: "flex", justifyContent: "center", padding: "14px 0 10px" }}>
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-expanded={!collapsed}
            aria-label={t("nav.expand")}
            title={t("nav.expand")}
            style={railToggleButtonStyle}
          >
            <Icon path={ICON_PATHS.railExpand} size={14} />
          </button>
        </div>
      )}

      <div style={{ flexShrink: 0 }}>
        {!collapsed && (
          <div style={{ padding: "0 12px 4px" }}>
            <GlobalSearch />
          </div>
        )}

        {/* Scope sits with search: the two shell-global controls, both answering
            "what am I looking at" before any page decides anything. It is not in
            a page header on purpose — the scope frames every screen, and a
            per-page control reads as a page-local filter. */}
        {!collapsed ? (
          <div style={{ padding: "0 12px 8px" }}>
            <ScopeSelector />
          </div>
        ) : (
          <ScopeSelector variant="collapsed" onExpand={onToggleCollapse} />
        )}
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", paddingBottom: 8 }}>
        {sections.map((section, index) => {
          // A heading-less section is a single top-level item: nothing to
          // collapse, so nothing to close.
          const open = collapsed || section.titleKey === null || isOpen(section);

          return (
            <div key={sectionKey(section)}>
              {index > 0 && (
                <hr
                  style={{
                    border: 0,
                    borderTop: "1px solid rgba(255,255,255,.1)",
                    margin: "8px 16px",
                    width: "calc(100% - 40px)",
                  }}
                />
              )}

              {!collapsed && section.titleKey !== null && (
                <div style={{ padding: index === 0 ? "10px 12px 4px" : "0 12px 4px" }}>
                  <button
                    type="button"
                    onClick={() =>
                      setOpenSections({ ...openSections, [sectionKey(section)]: !open })
                    }
                    aria-expanded={open}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                      padding: "2px 4px",
                      border: "none",
                      background: "transparent",
                      color: "var(--rail-ink)",
                      cursor: "pointer",
                    }}
                  >
                    <span
                      style={{
                        fontSize: 10,
                        fontWeight: 600,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                      }}
                    >
                      {t(section.titleKey)}
                    </span>
                    <span
                      aria-hidden="true"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        color: "rgba(255,255,255,0.68)",
                        transform: open ? "rotate(-90deg)" : "rotate(0deg)",
                        transition: "transform 120ms ease",
                      }}
                    >
                      <Icon path={ICON_PATHS.railCollapse} size={12} />
                    </span>
                  </button>
                </div>
              )}

              {open &&
                section.items.map((entry) => {
                  const active = isActiveItem(entry, pathname);
                  const label = t(entry.labelKey);
                  const button = (
                    <button
                      key={entry.path}
                      type="button"
                      onClick={() => navigate(entry.path)}
                      aria-current={active ? "page" : undefined}
                      aria-label={collapsed ? label : undefined}
                      style={{
                        position: "relative",
                        minHeight: 28,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: collapsed ? "center" : "flex-start",
                        gap: 9,
                        padding: collapsed ? "7px 0" : "6px 9px",
                        borderRadius: 6,
                        border: "none",
                        background: active ? "var(--rail-active)" : "transparent",
                        color: active ? "#ffffff" : "rgba(255,255,255,0.82)",
                        font: "inherit",
                        fontSize: 12.5,
                        fontWeight: active ? 600 : 400,
                        fontFamily: "var(--font-body)",
                        cursor: "pointer",
                        textAlign: "left",
                        width: "100%",
                        overflow: "hidden",
                      }}
                    >
                      <Icon path={entry.icon} size={15} />
                      {!collapsed && (
                        <>
                          <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {label}
                          </span>
                          {entry.badgeCount ? <NavBadge count={entry.badgeCount} /> : null}
                        </>
                      )}
                      {collapsed && entry.badgeCount ? (
                        <span
                          aria-hidden="true"
                          style={{
                            position: "absolute",
                            top: 8,
                            right: 10,
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            background: entry.badgeCount > ALERT_BADGE_ATTENTION_AT ? "var(--gold-500)" : "var(--on-dark-3)",
                          }}
                        />
                      ) : null}
                    </button>
                  );

                  return collapsed ? (
                    <Tooltip key={entry.path} title={label} placement="right">
                      {button}
                    </Tooltip>
                  ) : (
                    <div key={entry.path} style={{ padding: "0 8px 1px" }}>
                      {button}
                    </div>
                  );
                })}
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: "auto", flexShrink: 0 }}>{footer}</div>
    </nav>
  );
}

const railToggleButtonStyle: React.CSSProperties = {
  width: 24,
  height: 24,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.25)",
  background: "transparent",
  color: "rgba(255,255,255,0.6)",
  cursor: "pointer",
  padding: 0,
};

/**
 * The alert count.
 *
 * Muted until it passes `ALERT_BADGE_ATTENTION_AT`, then gold — the handoff's
 * "waiting" colour. `--gold-500` is fill only at 2.6:1, so the loud state uses
 * `--gold-300`, the step the tokens mark as the accent for dark green, with
 * `--gold-700` digits on it. The collapsed dot carries no text and can take the
 * 500.
 */
function NavBadge({ count }: { count: number }) {
  const loud = count > ALERT_BADGE_ATTENTION_AT;
  return (
    <span
      className="count-badge"
      style={{
        background: loud ? "var(--gold-300)" : "rgba(255,255,255,.18)",
        color: loud ? "var(--gold-700)" : "var(--on-dark-2)",
        minWidth: 20,
        height: 20,
        fontSize: 11,
      }}
    >
      {count}
    </span>
  );
}


/**
 * The key a section is remembered under.
 *
 * Its heading where it has one; its first path where it does not, so a
 * heading-less top-level item still has a stable identity if one is ever made
 * collapsible. Never the array index — inserting a section above would shift
 * every remembered state onto the wrong row.
 */
function sectionKey(section: NavSection | undefined): string {
  if (!section) return "";
  return section.titleKey ?? section.items[0]?.path ?? "";
}
