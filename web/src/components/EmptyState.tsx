import type { ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import { useLang } from "../i18n/LanguageContext";
import { Button, Card } from "./ui";

/**
 * What a list with no rows says.
 *
 * The tables used to render a bare header over nothing, which reads as a
 * failure rather than a fact. Three things make it a fact: what this list
 * holds, why it is empty now, and what would put something in it.
 *
 * The distinction that matters most is between "there is nothing" and "your
 * filters exclude everything". They look identical and mean opposite things —
 * an empty caseload is a finding, an over-filtered one is a mistake — so when
 * any filter is active the empty state says so first and offers to clear them.
 */
export default function EmptyState({
  title,
  body,
  action,
}: {
  /** What this list holds, stated plainly. */
  title: string;
  /** Why it is empty, and what would fill it. */
  body: ReactNode;
  /** The action that would fill it, when the caller can perform one. */
  action?: ReactNode;
}) {
  const { t } = useLang();
  const [params, setParams] = useSearchParams();

  const filters = [...params.keys()].filter((key) => !NOT_A_FILTER.has(key));
  const filtered = filters.length > 0;

  return (
    <Card>
      <div style={{ padding: "16px 4px", maxWidth: 560 }}>
        <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>
          {filtered ? t("list.emptyFiltered") : title}
        </div>
        <div className="t-meta">{filtered ? t("empty.filteredBody") : body}</div>

        <div style={{ marginTop: 14, display: "flex", gap: 8, flexWrap: "wrap" }}>
          {filtered && (
            <Button
              onClick={() => {
                const next = new URLSearchParams(params);
                for (const key of filters) next.delete(key);
                next.delete("page");
                setParams(next, { replace: true });
              }}
            >
              {t("list.clearFilters")}
            </Button>
          )}
          {action}
        </div>
      </div>
    </Card>
  );
}

/**
 * Query parameters that are not filters.
 *
 * `page` is a cursor, and `woreda` is the shell's scope — clearing it from an
 * empty list would silently widen the user's view past what they chose, which
 * is the one thing a "clear filters" button must not do.
 */
const NOT_A_FILTER = new Set(["page", "woreda"]);
