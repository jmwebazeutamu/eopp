import { useSearchParams } from "react-router-dom";

import { useLang } from "../i18n/LanguageContext";
import { Button } from "./ui";

/**
 * Page controls for a server-paginated list.
 *
 * One component for every list, because the two that had pagination had
 * written it inline with hardcoded "Previous" and "Next" — untranslatable, and
 * about to be copied onto two more screens.
 *
 * `param` is named by the caller so a screen can paginate more than one list
 * independently: the referrals queue carries three, and a single `?page=`
 * could not say which queue it meant.
 *
 * Renders nothing when everything fits on one page. A control that can only be
 * disabled is noise.
 */
export default function Paginator({
  total,
  pageSize,
  param = "page",
  label,
}: {
  total: number;
  pageSize: number;
  /** Query parameter holding the page number. */
  param?: string;
  /** Names the list, for screen readers, when a page has several. */
  label?: string;
}) {
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const page = Math.max(1, Number(params.get(param) ?? 1));
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return null;

  function go(next: number) {
    const updated = new URLSearchParams(params);
    if (next <= 1) updated.delete(param);
    else updated.set(param, String(next));
    setParams(updated, { replace: true });
  }

  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label={label ?? t("page.label")}
      style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 12, marginTop: 12 }}
    >
      {/* Announced when the page changes, so a screen reader hears the new
          range rather than silently landing on different rows. */}
      <span className="t-meta" role="status">
        {t("page.range", { first, last, total })}
      </span>
      <Button size="sm" disabled={page <= 1} onClick={() => go(page - 1)}>
        {t("page.previous")}
      </Button>
      <Button size="sm" disabled={page >= lastPage} onClick={() => go(page + 1)}>
        {t("page.next")}
      </Button>
    </nav>
  );
}
