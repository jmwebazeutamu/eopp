import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { usePreference } from "./preferences";

/**
 * The woreda scope, in one place.
 *
 * Every scoped screen reads the value from here and no screen keeps its own
 * copy. The case list used to carry its own woreda chip row, so narrowing the
 * caseload to Adama left the referral list, the alert inbox and the youth
 * registry showing every woreda — three screens quietly disagreeing with the
 * one in front of you.
 *
 * Two stores, deliberately:
 *  - the URL query, so a narrowed view is a shareable link and the back button
 *    returns to it;
 *  - a per-user preference, so the scope survives a reload and a nav click.
 *
 * The URL wins when it carries one, because a link someone sent you must show
 * what they saw. It is not written back to the preference — inheriting a
 * colleague's scope permanently from one click would be a surprise.
 *
 * This is presentation, not permission. `ScopedQuerySetMixin` decides what a
 * user may read; this only narrows within it, and a value outside the account's
 * own woredas falls back to "all" rather than filtering to an empty screen.
 */

export const SCOPE_PARAM = "woreda";
/** "All woredas" — the absence of a narrowing, not a woreda named "all". */
export const SCOPE_ALL = "";

interface ScopeValue {
  /** The selected woreda, or `SCOPE_ALL`. */
  woreda: string;
  setWoreda: (woreda: string) => void;
  /** Woredas this account may narrow to, from `/users/me/`. */
  options: string[];
  /** Human label for a page subtitle: "All woredas" or the woreda's name. */
  label: string;
  /** Whether there is any choice to offer. A single-woreda account has none. */
  selectable: boolean;
}

const ScopeContext = createContext<ScopeValue | null>(null);

export function ScopeProvider({ user, children }: { user: CurrentUser | null; children: ReactNode }) {
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  const [stored, setStored] = usePreference<string>("scope.woreda", user?.id, SCOPE_ALL);

  const options = useMemo(() => user?.scopable_woredas ?? [], [user]);

  const woreda = useMemo(() => {
    const fromUrl = params.get(SCOPE_PARAM);
    const candidate = fromUrl !== null ? fromUrl : stored;
    // A shared link naming a woreda the recipient cannot see would otherwise
    // filter their screen to nothing and look like an empty programme.
    return candidate && options.includes(candidate) ? candidate : SCOPE_ALL;
  }, [params, stored, options]);

  const setWoreda = useCallback(
    (next: string) => {
      setStored(next);
      setParams(
        (current) => {
          const updated = new URLSearchParams(current);
          if (next === SCOPE_ALL) updated.delete(SCOPE_PARAM);
          else updated.set(SCOPE_PARAM, next);
          // Any change of scope changes the result set, so a page number from
          // the previous scope points at rows that may no longer exist.
          updated.delete("page");
          return updated;
        },
        { replace: true },
      );
    },
    [setStored, setParams],
  );

  const value = useMemo<ScopeValue>(
    () => ({
      woreda,
      setWoreda,
      options,
      label: woreda || t("shell.allWoredas"),
      selectable: options.length > 1,
    }),
    [woreda, setWoreda, options, t],
  );

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): ScopeValue {
  const value = useContext(ScopeContext);
  if (!value) throw new Error("useScope must be used inside a ScopeProvider");
  return value;
}

/**
 * The scope as a query parameter for a given resource.
 *
 * The column is not named the same way everywhere: cases and youth carry
 * `woreda` directly, while referrals and alerts reach it through their case as
 * `case__woreda`. Callers pass what their endpoint expects and get `undefined`
 * when nothing is selected, so the parameter is omitted rather than sent empty.
 */
export function scopeParam(woreda: string, field: "woreda" | "case__woreda" = "woreda") {
  return woreda ? { [field]: woreda } : {};
}
