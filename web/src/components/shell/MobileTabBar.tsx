import { Drawer } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import LanguageSwitch from "./LanguageSwitch";
import { isActivePath, type NavSection } from "./navModel";

/** Labels the bar and sheet shorten. The rail keeps the full wording. */
const SHORT: Record<string, "nav.registryShort"> = { "nav.registry": "nav.registryShort" };
const shortLabel = (key: string) => SHORT[key] ?? key;

/**
 * The phone's primary navigation.
 *
 * It used to carry every nav item — seven at the widest — across a 390px bar,
 * which gave each one 55px and made "Youth registry" wrap to two lines at 9px.
 * Five is what fits: the four things a case manager does, and More.
 *
 * Sticky inside the main column rather than `position: fixed`, per the
 * handoff — fixed escapes a constrained shell and lands in the wrong place
 * inside an embedded frame.
 */

export const TAB_BAR_HEIGHT = 56;

/** The four that stay on the bar, in the order the work happens. */
const PRIMARY = ["/dashboard/my-work", "/dashboard/woreda", "/dashboard/programme", "/dashboard/results", "/cases", "/referrals", "/alerts"];
const MAX_PRIMARY = 4;

export default function MobileTabBar({
  user,
  sections,
  pathname,
  onSignOut,
}: {
  user: CurrentUser;
  sections: NavSection[];
  pathname: string;
  onSignOut: () => void;
}) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [moreOpen, setMoreOpen] = useState(false);

  const all = sections.flatMap((section) => section.items);
  // The role's first dashboard tier, then Cases, Referrals, Alerts. A role with
  // several tiers puts only its first on the bar; the rest go under More,
  // because four dashboards on a phone bar is not navigation.
  const primary = PRIMARY.filter((path) => all.some((item) => item.path === path))
    .reduce<string[]>((kept, path) => {
      const isTier = path.startsWith("/dashboard/");
      if (isTier && kept.some((p) => p.startsWith("/dashboard/"))) return kept;
      return kept.length < MAX_PRIMARY ? [...kept, path] : kept;
    }, []);

  const onBar = primary.map((path) => all.find((item) => item.path === path)!).filter(Boolean);
  const inMore = all.filter((item) => !primary.includes(item.path));

  return (
    <>
      <nav
        className="on-dark"
        aria-label={t("nav.primary")}
        style={{
          position: "sticky",
          bottom: 0,
          height: TAB_BAR_HEIGHT,
          flexShrink: 0,
          background: "var(--green-700)",
          display: "flex",
          alignItems: "stretch",
          // The home indicator on an iPhone sits over the bottom of the screen.
          paddingBottom: "env(safe-area-inset-bottom, 0px)",
          boxSizing: "content-box",
        }}
      >
        {onBar.map((entry) => (
          <TabButton
            key={entry.path}
            icon={entry.icon}
            label={t(shortLabel(entry.labelKey) as typeof entry.labelKey)}
            active={isActivePath(entry.path, pathname)}
            badge={Boolean(entry.badgeCount)}
            onClick={() => navigate(entry.path)}
          />
        ))}
        {inMore.length > 0 && (
          <TabButton
            icon={ICON_PATHS.more}
            label={t("nav.more")}
            active={inMore.some((entry) => isActivePath(entry.path, pathname))}
            expanded={moreOpen}
            onClick={() => setMoreOpen(true)}
          />
        )}
      </nav>

      <Drawer
        placement="bottom"
        open={moreOpen}
        onClose={() => setMoreOpen(false)}
        title={user.full_name}
        styles={{ body: { padding: 12 } }}
      >
        <div className="t-meta" style={{ marginTop: -8, marginBottom: 12 }}>
          {user.role_display} ·{" "}
          {user.woreda_assignment?.length ? user.woreda_assignment.join(", ") : t("shell.allWoredas")}
        </div>

        {inMore.map((entry) => (
          <button
            key={entry.path}
            type="button"
            onClick={() => {
              setMoreOpen(false);
              navigate(entry.path);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              width: "100%",
              minHeight: 48,
              padding: "0 8px",
              borderRadius: "var(--r-button)",
              border: "none",
              background: isActivePath(entry.path, pathname) ? "var(--green-100)" : "transparent",
              color: "var(--ink-900)",
              font: "inherit",
              fontFamily: "var(--font-body)",
              fontSize: 15,
              cursor: "pointer",
              textAlign: "left",
            }}
          >
            <Icon path={entry.icon} />
            {t(shortLabel(entry.labelKey) as typeof entry.labelKey)}
          </button>
        ))}

        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--line)" }}>
          <div className="t-meta" style={{ marginBottom: 6 }}>
            {t("shell.language")}
          </div>
          <LanguageSwitch />
        </div>

        <button
          type="button"
          onClick={onSignOut}
          style={{
            marginTop: 12,
            minHeight: 48,
            width: "100%",
            borderRadius: "var(--r-button)",
            border: "1px solid var(--line)",
            background: "transparent",
            color: "var(--ink-900)",
            font: "inherit",
            fontFamily: "var(--font-body)",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          {t("nav.signOut")}
        </button>
      </Drawer>
    </>
  );
}

function TabButton({
  icon,
  label,
  active,
  badge,
  expanded,
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  badge?: boolean;
  expanded?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      aria-expanded={expanded}
      style={{
        position: "relative",
        flex: 1,
        minWidth: 44,
        border: "none",
        background: active ? "var(--green-500)" : "transparent",
        color: "var(--on-dark)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 2,
        cursor: "pointer",
        fontFamily: "var(--font-body)",
      }}
    >
      <Icon path={icon} size={20} />
      {/* 11px and never wrapping. A label that wraps at 360px has already
          failed; the short forms exist so it does not have to. */}
      <span style={{ fontSize: 11, fontWeight: 600, whiteSpace: "nowrap" }}>{label}</span>
      {badge && (
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            top: 6,
            right: "50%",
            marginRight: -16,
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--gold-500)",
          }}
        />
      )}
    </button>
  );
}
