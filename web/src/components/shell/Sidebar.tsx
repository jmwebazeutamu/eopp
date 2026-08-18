import { Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import GlobalSearch from "./GlobalSearch";
import ScopeSelector from "./ScopeSelector";
import { Icon, ICON_PATHS } from "../ui";
import { ALERT_BADGE_ATTENTION_AT, isActivePath, type NavSection } from "./navModel";

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
 * The rail fills the shell row and owns its own scroll. It used to stretch to
 * the height of the *page*, which on a 145-row case list made it 2,203px tall
 * and put the signed-in user's block — and the only sign-out button in the
 * application — 2,153px down, reachable only by scrolling past every case.
 * `AppLayout` now pins the shell to the viewport and scrolls `main` instead, so
 * this is simply full height.
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
  sections,
  pathname,
  collapsed,
  onToggleCollapse,
  footer,
}: SidebarProps) {
  const { t } = useLang();
  const navigate = useNavigate();

  return (
    <nav
      className="on-dark"
      aria-label={t("nav.primary")}
      style={{
        width: collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED,
        flexShrink: 0,
        background: "#173629",
        color: "var(--on-dark)",
        display: "flex",
        flexDirection: "column",
        padding: 0,
        gap: 0,
        transition: "width 120ms ease",
        height: "100%",
        overflowY: "auto",
      }}
    >
      {!collapsed ? (
        <div style={{ padding: "14px 16px 10px 16px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.01em", color: "#ffffff", lineHeight: 1.2, maxWidth: 150 }}>
            {t("app.name")}
          </div>
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-expanded={!collapsed}
            aria-label={t("nav.collapse")}
            title={t("nav.collapse")}
            style={{
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
            }}
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
            style={{
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
            }}
          >
            <Icon path={ICON_PATHS.railExpand} size={14} />
          </button>
        </div>
      )}

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

      {sections.map((section, index) => (
        <div key={section.titleKey} style={{ display: "contents" }}>
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
          {!collapsed && (
            <div
              style={{
                padding: index === 0 ? "10px 16px 4px" : "0 16px 4px",
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.4)",
              }}
            >
              {t(section.titleKey)}
            </div>
          )}

          {section.items.map((entry) => {
            const active = isActivePath(entry.path, pathname);
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
                  background: active ? "#2a5240" : "transparent",
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
              <div key={entry.path} style={{ padding: "0 8px 1px" }}>{button}</div>
            );
          })}
        </div>
      ))}

      <div style={{ marginTop: "auto" }}>{footer}</div>
    </nav>
  );
}

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
