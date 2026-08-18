import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Summary } from "../api/types";
import { useLang } from "../i18n/LanguageContext";

/**
 * The counter row, as filter chips.
 *
 * These were five or six cards in a grid, ~110px tall, which pushed the table
 * below the fold on every list screen — and they were never metrics. The alerts
 * page said so itself: "Tap a counter to filter." So they read as what they do.
 *
 * The server contract is unchanged and is the whole point: each counter arrives
 * as `{param, value, label, count}`, so the chip toggles exactly the query that
 * produced its number and no counter can drift from the list it filters to.
 * Counts cover the whole scoped set rather than the loaded page, and narrow
 * with the search box, so they answer "how do these matches break down?".
 *
 * Multi-select where the parameter supports it — the `__in` lookups the
 * viewsets declare — by joining values with commas, which is the encoding
 * django-filter's `BaseInFilter` reads. A parameter without `__in` toggles one
 * value at a time, because sending two would silently return rows matching
 * neither.
 */

interface Props {
  /** Resource path, e.g. "/cases" — the summary is at `${resource}/summary/`. */
  resource: string;
  /** Extra query parameters the screen is already filtering by, e.g. woreda. */
  params?: Record<string, string | undefined>;
  /**
   * Chip tone per counter value. Takes the *whole* chip palette, not just a
   * foreground: the counter cards took `fg` alone and painted `CASE_TONE.PLACED`
   * — white, designed to sit on a dark green chip — onto a white card, so the
   * "Placed" count rendered invisible while the other four showed. A tone is
   * a background and a foreground together or it is not a tone.
   */
  tones?: Record<string, { fg: string; bg: string; bd?: string; mark?: string }>;
  /** Reported to the page so its subtitle can state the filtered count. */
  onTotal?: (total: number) => void;
}

export default function FilterChips({ resource, params, tones, onTotal }: Props) {
  const { t } = useLang();
  const [searchParams, setSearchParams] = useSearchParams();
  const [summary, setSummary] = useState<Summary | null>(null);

  const search = searchParams.get("q") ?? "";

  // Serialised so the dependency is a primitive. Screens pass `params` as an
  // object literal, whose identity changes on every render — depending on the
  // object itself would refetch forever.
  const paramKey = JSON.stringify(params ?? {});

  const load = useCallback(async () => {
    try {
      const response = await api.get<Summary>(`${resource}/summary/`, {
        // The screen's own dimension is deliberately not sent: a counter that
        // only ever counted the filter already applied could not tell anyone
        // where to look next.
        params: { search: search || undefined, ...(JSON.parse(paramKey) as Record<string, string | undefined>) },
      });
      setSummary(response.data);
      onTotal?.(response.data.total);
    } catch {
      // A chip row is not worth an error banner; the list below it still loads
      // and reports its own failure.
      setSummary(null);
    }
    // `onTotal` is deliberately absent — a page passing an inline arrow would
    // otherwise refetch on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resource, search, paramKey]);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(() => {
    const byParam = new Map<string, Set<string>>();
    for (const counter of summary?.counters ?? []) {
      if (byParam.has(counter.param)) continue;
      byParam.set(counter.param, new Set((searchParams.get(counter.param) ?? "").split(",").filter(Boolean)));
    }
    return byParam;
  }, [summary, searchParams]);

  if (!summary || summary.counters.length === 0) return null;

  const anySelected = [...selected.values()].some((values) => values.size > 0);

  function apply(update: (next: URLSearchParams) => void) {
    const next = new URLSearchParams(searchParams);
    update(next);
    // Any filter change invalidates the page cursor.
    next.delete("page");
    setSearchParams(next, { replace: true });
  }

  function toggle(param: string, value: string) {
    apply((next) => {
      const multi = param.endsWith("__in");
      const current = new Set((next.get(param) ?? "").split(",").filter(Boolean));
      if (current.has(value)) current.delete(value);
      else if (multi) current.add(value);
      else {
        current.clear();
        current.add(value);
      }
      if (current.size === 0) next.delete(param);
      else next.set(param, [...current].join(","));
    });
  }

  function clearAll() {
    apply((next) => {
      for (const param of selected.keys()) next.delete(param);
    });
  }

  return (
    <div className="chip-row" role="group" aria-label={t("filters.label")}>
      <button
        type="button"
        className="chip-filter"
        aria-pressed={!anySelected}
        onClick={clearAll}
      >
        {t("filters.all")}
        <span className="chip-filter__count">{summary.total}</span>
      </button>

      {summary.counters.map((counter) => {
        const active = selected.get(counter.param)?.has(counter.value) ?? false;
        const tone = tones?.[counter.value];
        const empty = counter.count === 0;
        return (
          <button
            key={`${counter.param}:${counter.value}`}
            type="button"
            className="chip-filter"
            aria-pressed={active}
            onClick={() => toggle(counter.param, counter.value)}
            // Reduced emphasis, not disabled: "no stalled cases" is a finding,
            // and a filter that proves it is worth being able to click.
            data-empty={empty ? "true" : undefined}
            style={
              active && tone
                ? { background: tone.bg, color: tone.fg, borderColor: tone.bd ?? tone.bg }
                : undefined
            }
          >
            {/* The geometric mark leads the label, so it is not the part that
                gets dropped when the label truncates. */}
            {tone?.mark && <span aria-hidden="true">{tone.mark}</span>}
            {counter.label}
            <span className="chip-filter__count">{counter.count}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * The search box that goes with it.
 *
 * Kept beside the chips because they are one control: the box narrows the rows,
 * the chips say how the narrowed set breaks down.
 */
export function SearchBox({ placeholder }: { placeholder: string }) {
  const [searchParams, setSearchParams] = useSearchParams();

  return (
    <input
      className="input"
      type="search"
      placeholder={placeholder}
      aria-label={placeholder}
      defaultValue={searchParams.get("q") ?? ""}
      onChange={(event) => {
        const next = new URLSearchParams(searchParams);
        if (event.target.value) next.set("q", event.target.value);
        else next.delete("q");
        next.delete("page");
        setSearchParams(next, { replace: true });
      }}
    />
  );
}
