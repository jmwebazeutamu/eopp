import { Tooltip } from "antd";
import { useNavigate } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
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

export const RAIL_EXPANDED = 240;
export const RAIL_COLLAPSED = 64;

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
      aria-label={t("nav.primary")}
      style={{
        width: collapsed ? RAIL_COLLAPSED : RAIL_EXPANDED,
        flexShrink: 0,
        background: "var(--green-700)",
        color: "var(--on-dark)",
        display: "flex",
        flexDirection: "column",
        padding: "12px 8px",
        gap: 2,
        transition: "width 120ms ease",
        height: "100%",
        // Its own scrollbar, so a long nav scrolls inside the rail rather than
        // pushing the footer off the bottom of the document.
        overflowY: "auto",
      }}
    >
      <button
        type="button"
        onClick={onToggleCollapse}
        aria-expanded={!collapsed}
        aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
        title={collapsed ? t("nav.expand") : t("nav.collapse")}
        style={{
          alignSelf: collapsed ? "center" : "flex-end",
          width: 40,
          height: 40,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          borderRadius: "var(--r-button)",
          border: "none",
          background: "transparent",
          color: "var(--on-dark-2)",
          cursor: "pointer",
          marginBottom: 4,
        }}
      >
        <Icon path={collapsed ? ICON_PATHS.railExpand : ICON_PATHS.railCollapse} size={20} />
      </button>

      {sections.map((section, index) => (
        <div key={section.titleKey} style={{ display: "contents" }}>
          {index > 0 && (
            <hr
              style={{
                border: 0,
                borderTop: "1px solid rgba(255,255,255,.15)",
                margin: "10px 8px 6px",
                width: "calc(100% - 16px)",
              }}
            />
          )}
          {/* The heading is dropped rather than hidden when collapsed: at 64px
              there is no width for it, and an ellipsised section label reads as
              a broken nav item. The divider still separates the groups. */}
          {!collapsed && (
            <div
              style={{
                padding: "6px 12px 4px",
                fontSize: 11,
                fontWeight: 700,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--on-dark-3)",
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
                  minHeight: 44,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: collapsed ? "center" : "flex-start",
                  gap: 12,
                  padding: collapsed ? 0 : "0 12px",
                  borderRadius: "var(--r-button)",
                  border: "none",
                  background: active ? "var(--green-500)" : "transparent",
                  color: "var(--on-dark)",
                  font: "inherit",
                  fontSize: 15,
                  fontWeight: active ? 600 : 400,
                  fontFamily: "var(--font-body)",
                  cursor: "pointer",
                  textAlign: "left",
                  width: "100%",
                  overflow: "hidden",
                }}
              >
                {/* The third channel: colour, weight and this rule. */}
                {active && (
                  <span
                    aria-hidden="true"
                    style={{
                      position: "absolute",
                      insetBlock: 6,
                      left: 0,
                      width: 3,
                      borderRadius: "0 2px 2px 0",
                      background: "var(--on-dark)",
                    }}
                  />
                )}
                <Icon path={entry.icon} />
                {!collapsed && (
                  <>
                    <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {label}
                    </span>
                    {entry.badgeCount ? <NavBadge count={entry.badgeCount} /> : null}
                  </>
                )}
                {/* Collapsed, a count has nowhere to sit, so it becomes a dot.
                    Losing the number is acceptable; losing the signal is not. */}
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
                      background:
                        entry.badgeCount > ALERT_BADGE_ATTENTION_AT ? "var(--gold-500)" : "var(--on-dark-3)",
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
              button
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
      }}
    >
      {count}
    </span>
  );
}
