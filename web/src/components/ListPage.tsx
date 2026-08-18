import type { ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { useLang } from "../i18n/LanguageContext";
import EmptyState from "./EmptyState";
import FilterChips, { SearchBox } from "./FilterChips";
import { usePreference } from "./shell/preferences";
import { PageHeader } from "./ui";

/**
 * The frame every list screen renders inside.
 *
 * Title and one primary action, then search, then the filter chips, then the
 * table. Each of the six list pages used to rebuild that arrangement itself,
 * which is how they drifted: five carried a counter grid, one hand-rolled its
 * own; two stated the woreda in the subtitle and two did not; one measured its
 * own chrome at 336px and another at 250px.
 *
 * The vertical budget is the point. The brief's target is 220px from the top of
 * the content column to the table header at 1440px, so the gaps between these
 * four things are tighter than the page's default stack — a list screen is
 * dense by nature, and a case manager opening their caseload should see cases.
 */

/** Row heights: the comfortable default, and a compact option. */
export const DENSITY = { comfortable: "", compact: "table--compact" } as const;
export type Density = keyof typeof DENSITY;

interface Props {
  title: string;
  /** Result count and active scope. */
  subtitle?: ReactNode;
  /** One primary action, right-aligned on the title row. */
  action?: ReactNode;
  searchPlaceholder: string;
  /** Resource path for the chip row, e.g. "/cases". Omit for no chips. */
  resource?: string;
  chipParams?: Record<string, string | undefined>;
  chipTones?: Record<string, { fg: string; bg: string; bd?: string; mark?: string }>;
  /**
   * Rendered instead of `children` when the list has no rows. Centralised here
   * so a bare table header over nothing cannot come back on one screen.
   */
  empty?: { when: boolean; title: string; body: ReactNode; action?: ReactNode };
  /**
   * Whether this screen renders rows whose height the density control can
   * change. Partners and Users render stacked cards, and a control that does
   * nothing is worse than no control.
   */
  rowDensity?: boolean;
  /** Receives the density class to put on its table. */
  children: (density: string) => ReactNode;
}

export default function ListPage({
  title,
  subtitle,
  action,
  searchPlaceholder,
  resource,
  chipParams,
  chipTones,
  empty,
  rowDensity = true,
  children,
}: Props) {
  const { t } = useLang();
  const { user } = useAuth();
  const [density, setDensity] = usePreference<Density>("list.density", user?.id, "comfortable");

  return (
    <div className="page list-page">
      <PageHeader title={title} subtitle={subtitle} action={action} />

      <div className="list-page__controls">
        <SearchBox placeholder={searchPlaceholder} />
        {rowDensity && (
        <button
          type="button"
          className="chip-filter only-laptop"
          aria-pressed={density === "compact"}
          onClick={() => setDensity(density === "compact" ? "comfortable" : "compact")}
          title={t("list.densityHint")}
        >
          {t(density === "compact" ? "list.comfortable" : "list.compact")}
        </button>
        )}
      </div>

      {resource && <FilterChips resource={resource} params={chipParams} tones={chipTones} />}

      {empty?.when ? (
        <EmptyState title={empty.title} body={empty.body} action={empty.action} />
      ) : (
        children(DENSITY[density])
      )}
    </div>
  );
}
