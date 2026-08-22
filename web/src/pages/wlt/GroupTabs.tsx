import { useNavigate } from "react-router-dom";

import { badgeFor, GROUP_TABS, type GroupTab } from "./groupTabs";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The group record's tab strip.
 *
 * Every section of the record used to render in one column — about 3,600px on
 * a group with a full roster and a year of meetings — so the readiness card
 * that the page exists for sat at the same weight as a note about former
 * members, and "Open a meeting" was some 1,800px down.
 *
 * Tabs are routes rather than local state. A link to the roster is a link to
 * the roster, refreshing keeps you where you were, and the back button steps
 * between sections instead of leaving the group entirely.
 *
 * A real `tablist` with arrow-key navigation: these are the page's primary
 * navigation, and a row of buttons that only answers to a mouse would put the
 * whole record behind a pointer.
 */
export default function GroupTabs({
  groupId,
  active,
  counts,
}: {
  groupId: string;
  active: string;
  counts: { members?: number; meetings?: number; linkages?: number };
}) {
  const { t } = useLang();
  const navigate = useNavigate();

  function go(tab: GroupTab) {
    navigate(`/wlt/groups/${groupId}/${tab.slug}`);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const index = GROUP_TABS.findIndex((tab) => tab.slug === active);
    if (index === -1) return;
    // Home and End as well as the arrows: with six tabs the ends are worth
    // reaching directly, and the pattern is what a screen-reader user expects.
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % GROUP_TABS.length
        : event.key === "ArrowLeft"
          ? (index - 1 + GROUP_TABS.length) % GROUP_TABS.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? GROUP_TABS.length - 1
              : -1;
    if (next === -1) return;
    event.preventDefault();
    go(GROUP_TABS[next]);
  }

  return (
    <div className="group-tabs" role="tablist" aria-label={t("wlt.groupTabsLabel")} onKeyDown={onKeyDown}>
      {GROUP_TABS.map((tab) => {
        const selected = tab.slug === active;
        const badge = badgeFor(tab, counts);
        return (
          <button
            key={tab.slug}
            type="button"
            role="tab"
            id={`group-tab-${tab.slug}`}
            aria-controls={`group-panel-${tab.slug}`}
            aria-selected={selected}
            // Only the selected tab is in the tab order; the arrows move
            // between them. Six stops before the content would be six stops
            // on every visit.
            tabIndex={selected ? 0 : -1}
            className="group-tabs__tab"
            data-active={selected ? "true" : undefined}
            onClick={() => go(tab)}
          >
            {t(tab.labelKey)}
            {badge !== null && <span className="group-tabs__count">{badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
