/**
 * The permission probe: what does the current account actually get back?
 *
 * The §7 access row tells you what the matrix *says*. This tells you what the
 * API *does*, which is the thing worth checking — the two have disagreed
 * before, and every time they did it was a viewset that forgot to declare a
 * scope field and returned an empty queryset instead of a refusal.
 *
 * Reads only, deliberately. A probe that exercised writes would create a
 * training enrolment or a grievance every time somebody pressed the button, and
 * a dev tool that leaves records behind stops being usable on a database you
 * care about. Write permissions are shown from the access row instead, which is
 * honest about being a claim rather than an observation.
 *
 * The arithmetic lives here rather than in the component for the reason
 * `timelineLayout.ts` gives: this is the part that can be unit-tested, and a
 * test asserting on the panel's markup would assert on nothing useful.
 */

export interface Probe {
  /** What to call it on screen. */
  label: string;
  /** Path under /api/v1, leading slash included. */
  path: string;
  /** Which domain it belongs to, for grouping. */
  group: "Youth side" | "Delivery" | "Dashboards" | "WLT group module" | "Administration";
}

/**
 * The endpoints worth asking about — one per boundary that has ever been
 * wrong, not one per route. A probe list that mirrors the URLconf would take
 * thirty seconds to run and nobody would read the result.
 */
export const PROBES: Probe[] = [
  { label: "Cases", path: "/cases/", group: "Youth side" },
  { label: "Beneficiary registry", path: "/youth/", group: "Youth side" },
  { label: "Referrals", path: "/referrals/", group: "Youth side" },
  { label: "Alerts", path: "/alerts/", group: "Youth side" },

  { label: "Training enrolments", path: "/training/enrolments/", group: "Delivery" },
  { label: "Placements", path: "/placements/placements/", group: "Delivery" },
  { label: "Retention checks", path: "/placements/checks/", group: "Delivery" },
  { label: "Enterprises", path: "/enterprises/enterprises/", group: "Delivery" },
  { label: "Contact log", path: "/followups/contacts/", group: "Delivery" },
  { label: "Grievances", path: "/grievances/grievances/", group: "Delivery" },

  { label: "Tier 1 · My work", path: "/dashboard/my-work/", group: "Dashboards" },
  { label: "Tier 2 · Woreda", path: "/dashboard/woreda/", group: "Dashboards" },
  { label: "Tier 3 · Programme", path: "/dashboard/programme/", group: "Dashboards" },
  { label: "Tier 4 · Results", path: "/dashboard/results/", group: "Dashboards" },

  { label: "Groups", path: "/wlt/groups/", group: "WLT group module" },
  { label: "Beneficiary profiles", path: "/wlt/profiles/", group: "WLT group module" },
  { label: "Service linkages", path: "/wlt/linkages/", group: "WLT group module" },

  { label: "User accounts", path: "/users/", group: "Administration" },
];

export type Verdict = "allowed" | "empty" | "refused" | "absent" | "unauthenticated" | "error";

export interface ProbeResult extends Probe {
  status: number;
  verdict: Verdict;
  /** Row count where the body was a list or a paginated envelope. */
  count: number | null;
}

/**
 * Turn an HTTP status into the answer somebody is actually looking for.
 *
 * 403 and 404 are kept apart on purpose. CLAUDE.md's rule is that an
 * out-of-scope *record* 404s — the API does not confirm that a row the caller
 * cannot see exists — while a whole endpoint a role may not touch 403s. So a
 * 404 here means the route is not mounted, and seeing one against a list
 * endpoint is a finding, not a permission.
 */
export function classify(status: number): Verdict {
  if (status === 200) return "allowed";
  if (status === 401) return "unauthenticated";
  if (status === 403) return "refused";
  if (status === 404) return "absent";
  return "error";
}

/**
 * Pull a row count out of whatever shape the endpoint returned.
 *
 * List endpoints paginate to `{count, results}`; the dashboard tiers return an
 * object that is not a list at all. Returning null for the latter is the point:
 * "0" would read as an empty programme rather than as a shape with no rows in
 * it.
 */
export function rowCount(body: unknown): number | null {
  if (Array.isArray(body)) return body.length;
  if (body && typeof body === "object") {
    const envelope = body as { count?: unknown; results?: unknown };
    if (typeof envelope.count === "number") return envelope.count;
    if (Array.isArray(envelope.results)) return envelope.results.length;
  }
  return null;
}

/**
 * An allowed-but-empty result is its own verdict.
 *
 * This is the distinction the whole tool exists for. A case manager who gets
 * 200 with zero rows and a partner staff account that gets 403 are two
 * different access models, and the §7 note in CLAUDE.md records that the
 * codebase has both — `CaseViewSet` declares no `partner_field`, so partner
 * staff see an empty case list rather than a refusal. Rendering both as "no
 * access" would hide exactly that.
 */
export function refine(verdict: Verdict, count: number | null): Verdict {
  if (verdict === "allowed" && count === 0) return "empty";
  return verdict;
}

/** Colour token, label and geometric mark. Never colour alone (design rule 2). */
export const VERDICT_STYLE: Record<Verdict, { label: string; mark: string; fill: string; ink: string }> = {
  allowed: { label: "Allowed", mark: "●", fill: "var(--green-100)", ink: "var(--green-700)" },
  empty: { label: "Allowed, empty", mark: "○", fill: "var(--slate-100)", ink: "var(--slate-700)" },
  refused: { label: "403 refused", mark: "◆", fill: "var(--gold-100)", ink: "var(--gold-700)" },
  absent: { label: "404 not mounted", mark: "▲", fill: "var(--terra-100)", ink: "var(--terra-700)" },
  unauthenticated: { label: "401 no session", mark: "■", fill: "var(--red-100)", ink: "var(--red-700)" },
  error: { label: "Error", mark: "■", fill: "var(--red-100)", ink: "var(--red-700)" },
};

/** Counts by verdict, for the one-line summary above the table. */
export function summarise(results: ProbeResult[]): Array<{ verdict: Verdict; count: number }> {
  const tally = new Map<Verdict, number>();
  for (const result of results) tally.set(result.verdict, (tally.get(result.verdict) ?? 0) + 1);
  // Fixed order rather than insertion order, so the summary does not reshuffle
  // between runs and become unreadable at a glance.
  const order: Verdict[] = ["allowed", "empty", "refused", "absent", "unauthenticated", "error"];
  return order.filter((v) => tally.has(v)).map((verdict) => ({ verdict, count: tally.get(verdict) ?? 0 }));
}

/** Probes in declaration order, grouped, with empty groups dropped. */
export function groupResults(results: ProbeResult[]): Array<{ group: Probe["group"]; results: ProbeResult[] }> {
  const groups: Array<{ group: Probe["group"]; results: ProbeResult[] }> = [];
  for (const result of results) {
    const existing = groups.find((g) => g.group === result.group);
    if (existing) existing.results.push(result);
    else groups.push({ group: result.group, results: [result] });
  }
  return groups;
}
