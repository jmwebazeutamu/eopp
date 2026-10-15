import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import OverflowNav, { type OverflowLink } from "./OverflowNav";
import { activeModule, buildModules, isActiveItem, isActivePath, type NavSection } from "./navModel";

/**
 * The horizontal navigation: modules in one row, the active module's
 * destinations in a second.
 *
 * Both rows read `buildNav` through `buildModules`, which is the single place
 * that decides what a role is offered. The active module and page are derived
 * from the URL on every render, so a refresh, a deep link and the Back button
 * all land on the right highlight with no state to drift.
 *
 * The secondary row is omitted when the module has one destination: a row with
 * a single link is a control that cannot do anything.
 */
export default function TopNav({ sections, pathname }: { user?: CurrentUser; sections: NavSection[]; pathname: string }) {
  const { t } = useLang();
  const modules = buildModules(sections);
  const current = activeModule(modules, sections, pathname);

  const primary: OverflowLink[] = modules.map((module) => {
    const single = module.items.length === 0;
    const onItsPage = single && isActivePath(module.landing, pathname);
    return {
      key: module.key,
      to: module.landing,
      label: t(module.labelKey),
      // A one-page module IS its page; a bigger one is only somewhere you are inside.
      current: onItsPage,
      inside: !single && current?.key === module.key,
      badge: module.badgeCount || undefined,
    };
  });

  const secondary: OverflowLink[] = (current?.items ?? []).map((entry) => ({
    key: entry.path,
    to: entry.path,
    label: t(entry.labelKey),
    current: isActiveItem(entry, pathname),
    badge: entry.badgeCount || undefined,
  }));

  return (
    <>
      <OverflowNav label={t("nav.primary")} links={primary} variant="primary" />
      {secondary.length > 0 && <OverflowNav label={t("nav.secondary")} links={secondary} variant="secondary" />}
    </>
  );
}
