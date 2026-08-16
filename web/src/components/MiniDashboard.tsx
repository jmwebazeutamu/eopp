import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import type { Summary } from "../api/types";
import { Card } from "./ui";

/**
 * The counter row every list screen carries, after the pattern the alerts
 * screen set.
 *
 * Each counter is also the filter that produces it: the server returns the
 * query parameter alongside the count, so clicking "Stalled · 6" navigates to
 * exactly the six rows it counted, and clicking again clears it. That is the
 * whole contract — no counter can drift from the list it filters to, because
 * neither side decides the mapping locally.
 *
 * Counters are computed over the caller's whole scoped set, not the loaded
 * page, and they narrow with the search box so they answer "how do these
 * matches break down?" rather than restating the total.
 */

interface Props {
  /** Resource path, e.g. "/cases" — the summary is at `${resource}/summary/`. */
  resource: string;
  /** Extra query parameters the screen is already filtering by, e.g. woreda. */
  params?: Record<string, string | undefined>;
  /** Tone per counter value, keyed by the value the counter filters on. */
  tones?: Record<string, { fg: string; bg?: string }>;
  /** A line under each counter saying why it exists. */
  reasons?: Record<string, string>;
}

export default function MiniDashboard({ resource, params, tones, reasons }: Props) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [summary, setSummary] = useState<Summary | null>(null);

  const search = searchParams.get("q") ?? "";

  // Serialised so the dependency is a primitive. Screens pass `params` as an
  // object literal, whose identity changes on every render — depending on the
  // object itself would refetch on every render, forever.
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
    } catch {
      // A counter row is not worth an error banner over; the list below it
      // still loads and reports its own failure.
      setSummary(null);
    }
  }, [resource, search, paramKey]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!summary || summary.counters.length === 0) return null;

  function toggle(param: string, value: string) {
    const next = new URLSearchParams(searchParams);
    if (next.get(param) === value) next.delete(param);
    else next.set(param, value);
    // Any filter change invalidates the page cursor.
    next.delete("page");
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="grid-counters">
      {summary.counters.map((counter) => {
        const active = searchParams.get(counter.param) === counter.value;
        const tone = tones?.[counter.value];
        return (
          <Card
            key={`${counter.param}:${counter.value}`}
            onClick={() => toggle(counter.param, counter.value)}
            style={active ? { borderColor: "var(--green-700)", borderWidth: 2 } : undefined}
          >
            <div className="t-metric-sm" style={{ color: tone?.fg ?? "var(--ink-900)" }}>
              {counter.count}
            </div>
            <div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{counter.label}</div>
            {reasons?.[counter.value] && (
              <div className="t-meta" style={{ fontSize: 11 }}>
                {reasons[counter.value]}
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}

/**
 * The search box that goes with it.
 *
 * Kept next to the counters because they are one control: the box narrows the
 * rows, the counters say how the narrowed set breaks down.
 */
export function SearchBox({ placeholder }: { placeholder: string }) {
  const [searchParams, setSearchParams] = useSearchParams();

  return (
    <input
      className="input"
      placeholder={placeholder}
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
