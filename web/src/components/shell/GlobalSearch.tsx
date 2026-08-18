import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../api/client";
import { useLang } from "../../i18n/LanguageContext";
import { Icon, ICON_PATHS } from "../ui";
import { maskPhone } from "../ui";

/**
 * Search across record types, from the header.
 *
 * There is no single search endpoint, so this fans out to the four list
 * endpoints that already have `search_fields` and groups what comes back. That
 * is a deliberate choice over adding a server-side search API in a structural
 * pass: each endpoint is already §7-scoped, so a fan-out inherits the scoping
 * for free and cannot leak a record the caller could not otherwise read. A
 * combined endpoint would have to re-derive all four scopes in one query.
 *
 * Youth phone numbers stay masked here as everywhere else. This is a lookup
 * surface, not a record, and the registry has no reveal.
 */

const DEBOUNCE_MS = 250;
const PER_GROUP = 5;

interface Hit {
  id: string;
  title: string;
  detail: string;
  href: string;
}

interface Group {
  labelKey: "search.youth" | "search.cases" | "search.partners" | "search.referrals";
  hits: Hit[];
}

export default function GlobalSearch({ autoFocus = false }: { autoFocus?: boolean } = {}) {
  const { t } = useLang();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [groups, setGroups] = useState<Group[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const container = useRef<HTMLDivElement>(null);

  // `/` and Cmd/Ctrl-K focus the field from anywhere, except while the caller
  // is already typing into something.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable === true;
      const shortcut = (event.key === "/" && !typing) || ((event.metaKey || event.ctrlKey) && event.key === "k");
      if (shortcut) {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
        return;
      }
      if (event.key === "Escape" && open) {
        setOpen(false);
        input.current?.blur();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    const onPointer = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, []);

  const run = useCallback(
    async (term: string) => {
      setLoading(true);
      try {
        setGroups(await searchEverything(term));
        setOpen(true);
      } catch {
        // A failed lookup is not worth a modal; the empty state says so.
        setGroups([]);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    const term = query.trim();
    if (term.length < 2) {
      setGroups([]);
      return;
    }
    const timer = setTimeout(() => void run(term), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, run]);

  const total = groups.reduce((sum, group) => sum + group.hits.length, 0);

  return (
    <div ref={container} style={{ position: "relative", flex: 1, maxWidth: 480 }}>
      <label className="sr-only" htmlFor="global-search">
        {t("search.label")}
      </label>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <span style={{ position: "absolute", left: 10, display: "flex", color: "var(--on-dark-3)" }}>
          <Icon path={ICON_PATHS.search} size={16} />
        </span>
        <input
          id="global-search"
          ref={input}
          autoFocus={autoFocus}
          type="search"
          role="combobox"
          aria-expanded={open}
          aria-controls="global-search-results"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => groups.length > 0 && setOpen(true)}
          placeholder={t("search.placeholder")}
          style={{
            width: "100%",
            minHeight: 36,
            padding: "0 10px 0 32px",
            borderRadius: "var(--r-button)",
            border: "1px solid rgba(255,255,255,.25)",
            background: "rgba(255,255,255,.10)",
            color: "var(--on-dark)",
            font: "inherit",
            fontSize: 14,
            fontFamily: "var(--font-body)",
          }}
        />
      </div>

      {open && query.trim().length >= 2 && (
        <div
          id="global-search-results"
          role="listbox"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            background: "var(--surface)",
            color: "var(--ink-900)",
            borderRadius: "var(--r-card)",
            border: "1px solid var(--line)",
            boxShadow: "var(--overlay)",
            padding: 6,
            maxHeight: "60vh",
            overflowY: "auto",
            zIndex: 30,
          }}
        >
          {loading && total === 0 && <div className="t-meta" style={{ padding: 10 }}>{t("common.loading")}</div>}
          {!loading && total === 0 && <div className="t-meta" style={{ padding: 10 }}>{t("search.none")}</div>}

          {groups.map((group) => (
            <div key={group.labelKey}>
              <div
                style={{
                  padding: "8px 10px 4px",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  color: "var(--ink-600)",
                }}
              >
                {t(group.labelKey)}
              </div>
              {group.hits.map((hit) => (
                <button
                  key={hit.href}
                  type="button"
                  role="option"
                  aria-selected={false}
                  onClick={() => {
                    setOpen(false);
                    setQuery("");
                    navigate(hit.href);
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    minHeight: 44,
                    padding: "6px 10px",
                    borderRadius: "var(--r-button)",
                    border: "none",
                    background: "transparent",
                    font: "inherit",
                    fontFamily: "var(--font-body)",
                    cursor: "pointer",
                  }}
                >
                  <span style={{ display: "block", fontWeight: 600, fontSize: 14 }}>{hit.title}</span>
                  <span style={{ display: "block" }} className="t-meta">
                    {hit.detail}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Looks enough like a UUID to be worth fetching directly. */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

async function searchEverything(term: string): Promise<Group[]> {
  const params = { search: term, page_size: PER_GROUP };

  // A referral is reachable by its own id, which no `search_fields` can match:
  // the column is a uuid and an icontains against it is not a query Postgres
  // will run. An exact id is fetched directly instead.
  const referralById = UUID.test(term)
    ? api
        .get(`/referrals/${term}/`)
        .then((response) => [response.data])
        .catch(() => [])
    : Promise.resolve([]);

  const [youth, cases, partners, referrals, byId] = await Promise.all([
    safeList("/youth/", params),
    safeList("/cases/", params),
    safeList("/partners/", params),
    safeList("/referrals/", params),
    referralById,
  ]);

  const groups: Group[] = [
    {
      labelKey: "search.youth",
      hits: youth.map((row: Record<string, unknown>) => ({
        id: String(row.id),
        title: String(row.full_name ?? ""),
        detail: [row.woreda, maskPhone(String(row.phone_number ?? ""))].filter(Boolean).join(" · "),
        href: `/youth?search=${encodeURIComponent(String(row.full_name ?? ""))}`,
      })),
    },
    {
      labelKey: "search.cases",
      hits: cases.map((row: Record<string, unknown>) => ({
        id: String(row.id),
        title: String((row.youth as Record<string, unknown>)?.full_name ?? ""),
        detail: [row.woreda, row.case_status_display ?? row.case_status].filter(Boolean).join(" · "),
        href: `/cases/${row.id}`,
      })),
    },
    {
      labelKey: "search.partners",
      hits: partners.map((row: Record<string, unknown>) => ({
        id: String(row.id),
        title: String(row.partner_name ?? ""),
        detail: [row.partner_type_display ?? row.partner_type, row.contact_name].filter(Boolean).join(" · "),
        href: `/partners?search=${encodeURIComponent(String(row.partner_name ?? ""))}`,
      })),
    },
    {
      labelKey: "search.referrals",
      hits: [...byId, ...referrals].map((row: Record<string, unknown>) => ({
        id: String(row.id),
        title: String((row.case_youth_name as string) ?? (row.receiving_partner_name as string) ?? String(row.id)),
        detail: [row.referral_category_label, row.status_display ?? row.status].filter(Boolean).join(" · "),
        href: row.case ? `/cases/${row.case}` : "/referrals",
      })),
    },
  ];

  return groups.filter((group) => group.hits.length > 0);
}

async function safeList(path: string, params: Record<string, unknown>) {
  try {
    const response = await api.get(path, { params });
    const data = response.data as { results?: unknown[] } | unknown[];
    const rows = Array.isArray(data) ? data : (data.results ?? []);
    return rows.slice(0, PER_GROUP) as Record<string, unknown>[];
  } catch {
    // One resource refusing — a role with no case access, say — must not blank
    // the other three.
    return [];
  }
}
