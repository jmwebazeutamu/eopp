/**
 * The role switcher — a development-only floating panel, bottom right.
 *
 * Switch to any account without a password, and read what §7 grants it: the
 * resolved access row, the dashboards and nav it is offered, and — on demand —
 * what a set of real endpoints actually returns for it.
 *
 * Why it exists: signing out and back in to check a scope is slow enough that
 * it does not get done, and the thing being tested is precisely the memory of
 * what each role sees. Every §7 finding in this repo so far was found by
 * signing in as somebody else; two of the three "P1 defects" in the first
 * dashboard punch list were artefacts of reviewing the screen as `admin`.
 *
 * **Never ships.** The panel is behind `import.meta.env.DEV` and loaded through
 * a dynamic import, so Rollup drops the chunk entirely from a production
 * build — `npm run build && grep -r "role switcher" dist/` finds nothing. The
 * API behind it is gated four ways besides; see `apps/users/dev_views.py`.
 *
 * Two deliberate departures from the design rules, both because this is a tool
 * and not a screen:
 *
 * 1. **Strings are literal, not `t()`.** Rule 7 exists so a translator gets
 *    complete coverage of what field staff read. Nobody outside this repo will
 *    ever see these, and thirty dev keys in `i18n/strings.ts` would be thirty
 *    rows of noise in the table a translator works through.
 * 2. **`position: fixed`.** Rule 4 forbids it for the tab bar, which must stay
 *    sticky inside the main column. A floating tool has no other option; below
 *    780px the launcher lifts clear of the 56px tab bar rather than covering it.
 *
 * Everything else follows: colours come from tokens, and every verdict carries
 * a label and a geometric mark as well as a colour.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, errorMessage, tokens } from "../api/client";
import type { CurrentUser } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { buildNav } from "../components/shell/navModel";
import { visibleTiers } from "../pages/dashboard/tierAccess";
import { classify, groupResults, PROBES, refine, rowCount, summarise, VERDICT_STYLE, type ProbeResult } from "./probe";

/** Who this browser signed in as, before any switching. */
const ORIGIN_KEY = "yep.dev.origin";

interface AccountsResponse {
  accounts: CurrentUser[];
  signed_in_as: string;
}

export default function RoleSwitcher() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<CurrentUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [probing, setProbing] = useState(false);
  const [results, setResults] = useState<ProbeResult[] | null>(null);
  const [tab, setTab] = useState<"accounts" | "access" | "probe">("accounts");

  // Recorded on first use rather than at sign-in: the switcher may not be the
  // thing that opened the session, and there is no hook into login from here.
  useEffect(() => {
    if (user && !localStorage.getItem(ORIGIN_KEY)) localStorage.setItem(ORIGIN_KEY, user.username);
  }, [user]);

  const origin = localStorage.getItem(ORIGIN_KEY);
  const impersonating = Boolean(user && origin && origin !== user.username);

  useEffect(() => {
    if (!open || accounts) return;
    api
      .get<AccountsResponse>("/dev/accounts/")
      .then((response) => setAccounts(response.data.accounts))
      .catch((caught) =>
        setError(
          errorMessage(
            caught,
            "Could not load accounts. The switcher needs DEBUG and DEV_ROLE_SWITCHER on in the backend.",
          ),
        ),
      );
  }, [open, accounts]);

  const switchTo = useCallback(
    async (username: string) => {
      setBusy(username);
      setError(null);
      try {
        const response = await api.post<{ access: string; refresh: string; user: CurrentUser }>(
          "/dev/impersonate/",
          { username },
        );
        tokens.set(response.data.access, response.data.refresh);
        setUser(response.data.user);
        // The probe belongs to the account that ran it; keeping it across a
        // switch would show one role's answers under another role's name.
        setResults(null);
        // Land on the first destination the resolved access row offers. A
        // single generic route is not safe here: WLT-only roles have no case
        // home, while linked partner roles have no WLT home.
        const firstDestination = buildNav(response.data.user, { openAlerts: 0 })[0]?.items[0]?.path ?? "/";
        navigate(firstDestination);
      } catch (caught) {
        setError(errorMessage(caught, `Could not switch to ${username}.`));
      } finally {
        setBusy(null);
      }
    },
    [navigate, setUser],
  );

  const runProbe = useCallback(async () => {
    setProbing(true);
    setError(null);
    const collected: ProbeResult[] = [];
    for (const probe of PROBES) {
      try {
        // `validateStatus` so a 403 resolves rather than throwing: a refusal is
        // the answer here, not a failure.
        const response = await api.get(probe.path, { validateStatus: () => true });
        const count = rowCount(response.data);
        collected.push({ ...probe, status: response.status, verdict: refine(classify(response.status), count), count });
      } catch {
        // A network-level failure, not an HTTP one — no status to report.
        collected.push({ ...probe, status: 0, verdict: "error", count: null });
      }
    }
    setResults(collected);
    setProbing(false);
  }, []);

  const grouped = useMemo(() => (accounts ? groupByRole(accounts) : []), [accounts]);

  if (!user) return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{ ...LAUNCHER, background: impersonating ? "var(--gold-500)" : "var(--rail-bg)" }}
        title="Role switcher (development only)"
        aria-label="Open the role switcher"
      >
        <span aria-hidden style={{ fontSize: 15 }}>
          ⇄
        </span>
        <span style={{ fontWeight: 600 }}>{impersonating ? user.username : "Roles"}</span>
      </button>
    );
  }

  return (
    <div style={PANEL} role="dialog" aria-label="Role switcher">
      <header style={HEADER}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--on-dark)" }}>Role switcher</div>
          <div style={{ fontSize: 11, color: "var(--on-dark-3)" }}>Development only · never in production</div>
        </div>
        <button type="button" onClick={() => setOpen(false)} style={CLOSE} aria-label="Close the role switcher">
          ✕
        </button>
      </header>

      <div style={CURRENT}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "var(--ink-900)" }}>{user.full_name}</div>
        <div style={{ fontSize: 11, color: "var(--ink-600)" }}>
          {user.role_display} · {user.username}
        </div>
        {impersonating && (
          <button type="button" onClick={() => switchTo(origin as string)} style={RETURN} disabled={busy !== null}>
            ← back to {origin}
          </button>
        )}
      </div>

      <nav style={TABS}>
        {(["accounts", "access", "probe"] as const).map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            style={{
              ...TAB,
              color: tab === name ? "var(--green-700)" : "var(--ink-600)",
              borderBottomColor: tab === name ? "var(--green-500)" : "transparent",
              fontWeight: tab === name ? 700 : 500,
            }}
          >
            {name === "accounts" ? "Accounts" : name === "access" ? "What it grants" : "Probe"}
          </button>
        ))}
      </nav>

      <div style={BODY}>
        {error && <p style={ERROR}>{error}</p>}

        {tab === "accounts" && (
          <>
            {!accounts && !error && <p style={MUTED}>Loading accounts…</p>}
            {grouped.map(({ role, members }) => (
              <section key={role} style={{ marginBottom: 10 }}>
                <h3 style={GROUP_TITLE}>{members[0].role_display}</h3>
                {members.map((account) => {
                  const active = account.username === user.username;
                  return (
                    <button
                      key={account.username}
                      type="button"
                      disabled={active || busy !== null}
                      onClick={() => switchTo(account.username)}
                      style={{
                        ...ACCOUNT,
                        background: active ? "var(--green-100)" : "var(--surface)",
                        borderColor: active ? "var(--green-border)" : "var(--line)",
                        cursor: active ? "default" : "pointer",
                      }}
                    >
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: "block", fontWeight: 600, color: "var(--ink-900)" }}>
                          {account.full_name}
                        </span>
                        <span style={{ display: "block", fontSize: 10, color: "var(--ink-600)" }}>
                          {account.username}
                          {account.partner_name ? ` · ${account.partner_name}` : ""}
                          {account.woreda_assignment.length ? ` · ${account.woreda_assignment.join(", ")}` : ""}
                        </span>
                      </span>
                      <span style={{ fontSize: 10, color: "var(--ink-400)", whiteSpace: "nowrap" }}>
                        {busy === account.username ? "…" : active ? "current" : scopeSummary(account)}
                      </span>
                    </button>
                  );
                })}
              </section>
            ))}
          </>
        )}

        {tab === "access" && <AccessTab user={user} />}

        {tab === "probe" && (
          <>
            <p style={MUTED}>
              Calls {PROBES.length} list endpoints as <strong>{user.username}</strong> and reports what came back.
              Reads only — a probe that exercised writes would leave records behind.
            </p>
            <button type="button" onClick={runProbe} disabled={probing} style={PRIMARY}>
              {probing ? "Probing…" : results ? "Run again" : "Run probe"}
            </button>

            {results && (
              <>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, margin: "8px 0" }}>
                  {summarise(results).map(({ verdict, count }) => (
                    <Pill key={verdict} verdict={verdict} text={`${count} ${VERDICT_STYLE[verdict].label}`} />
                  ))}
                </div>
                {groupResults(results).map(({ group, results: rows }) => (
                  <section key={group} style={{ marginBottom: 10 }}>
                    <h3 style={GROUP_TITLE}>{group}</h3>
                    {rows.map((row) => (
                      <div key={row.path} style={PROBE_ROW}>
                        <span style={{ minWidth: 0, flex: 1 }}>
                          <span style={{ display: "block", color: "var(--ink-900)" }}>{row.label}</span>
                          <span style={{ display: "block", fontSize: 10, color: "var(--ink-400)" }}>{row.path}</span>
                        </span>
                        {row.count !== null && (
                          <span style={{ fontSize: 10, color: "var(--ink-600)", whiteSpace: "nowrap" }}>
                            {row.count} row{row.count === 1 ? "" : "s"}
                          </span>
                        )}
                        <Pill verdict={row.verdict} text={String(row.status || "—")} />
                      </div>
                    ))}
                  </section>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AccessTab({ user }: { user: CurrentUser }) {
  const tiers = visibleTiers(user);
  const nav = buildNav(user, { openAlerts: 0 });

  const rows: Array<[string, string | boolean]> = [
    ["Case scope", user.access.case_scope],
    ["Case write", user.access.case_write],
    ["Referral scope", user.access.referral_scope],
    ["Referral write", user.access.referral_write],
    ["Delivery write", user.access.delivery_write],
    ["Group scope", user.access.group_scope],
    ["Group write", user.access.group_write],
  ];

  return (
    <>
      <h3 style={GROUP_TITLE}>The §7 row the API resolved</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: 10 }}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td style={{ ...CELL, color: "var(--ink-600)" }}>{label}</td>
              <td style={{ ...CELL, textAlign: "right" }}>
                {typeof value === "boolean" ? (
                  <Pill verdict={value ? "allowed" : "refused"} text={value ? "yes" : "no"} />
                ) : (
                  <code style={{ fontSize: 10, color: "var(--ink-900)" }}>{value}</code>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 style={GROUP_TITLE}>Dashboards offered</h3>
      <p style={{ ...MUTED, marginTop: 0 }}>
        {tiers.length ? tiers.map((tier) => tier.path).join(" · ") : "None — this role gets no dashboard tab."}
      </p>

      <h3 style={GROUP_TITLE}>Navigation offered</h3>
      {nav.map((section) => (
        <p key={section.titleKey} style={{ ...MUTED, marginTop: 0 }}>
          <strong style={{ color: "var(--ink-600)" }}>{section.titleKey}</strong>:{" "}
          {section.items.map((item) => item.path).join(" · ")}
        </p>
      ))}
      <p style={{ ...MUTED, borderTop: "1px solid var(--line-soft)", paddingTop: 6 }}>
        The nav gate is not the security boundary — every route behind it is scoped server-side. Use the Probe tab to
        see what the API actually returns.
      </p>
    </>
  );
}

function Pill({ verdict, text }: { verdict: ProbeResult["verdict"]; text: string }) {
  const style = VERDICT_STYLE[verdict];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 3,
        padding: "1px 6px",
        borderRadius: "var(--r-chip)",
        background: style.fill,
        color: style.ink,
        fontSize: 10,
        fontWeight: 600,
        whiteSpace: "nowrap",
      }}
      title={style.label}
    >
      <span aria-hidden>{style.mark}</span>
      {text}
    </span>
  );
}

/** Accounts by role, roles in the order the API returned them. */
function groupByRole(accounts: CurrentUser[]): Array<{ role: string; members: CurrentUser[] }> {
  const groups: Array<{ role: string; members: CurrentUser[] }> = [];
  for (const account of accounts) {
    const existing = groups.find((g) => g.role === account.role);
    if (existing) existing.members.push(account);
    else groups.push({ role: account.role, members: [account] });
  }
  return groups;
}

/** The shortest true thing about an account's reach, for the picker row. */
function scopeSummary(account: CurrentUser): string {
  if (account.access.case_scope !== "NONE") return account.access.case_scope;
  if (account.access.group_scope !== "NONE") return `group: ${account.access.group_scope}`;
  return "no case scope";
}

// ---------------------------------------------------------------------------
// Styles. Inline rather than in base.css: this file is dropped from the
// production bundle whole, and a stylesheet rule would survive it.
// ---------------------------------------------------------------------------

const LAUNCHER: React.CSSProperties = {
  position: "fixed",
  right: 16,
  // Clears the 56px tab bar plus its breathing room on a phone. The tab bar is
  // sticky inside the main column, so it occupies the bottom of the viewport.
  bottom: "calc(var(--tabbar-height, 56px) + 20px)",
  zIndex: 900,
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "8px 12px",
  minHeight: 40,
  border: "none",
  borderRadius: "var(--r-button)",
  color: "var(--on-dark)",
  boxShadow: "var(--raised)",
  cursor: "pointer",
  fontFamily: "var(--font-body)",
  fontSize: 12,
};

const PANEL: React.CSSProperties = {
  position: "fixed",
  right: 16,
  bottom: "calc(var(--tabbar-height, 56px) + 20px)",
  zIndex: 900,
  width: "min(360px, calc(100vw - 32px))",
  maxHeight: "min(70vh, 620px)",
  display: "flex",
  flexDirection: "column",
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: "var(--r-card)",
  boxShadow: "var(--raised)",
  overflow: "hidden",
  fontFamily: "var(--font-body)",
};

const HEADER: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
  padding: "10px 12px",
  background: "var(--rail-bg)",
};

const CLOSE: React.CSSProperties = {
  border: "none",
  background: "transparent",
  color: "var(--on-dark-2)",
  cursor: "pointer",
  fontSize: 13,
  lineHeight: 1,
  padding: 4,
};

const CURRENT: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid var(--line-soft)",
  background: "var(--surface-alt)",
};

const RETURN: React.CSSProperties = {
  marginTop: 6,
  padding: "3px 8px",
  border: "1px solid var(--gold-border)",
  borderRadius: "var(--r-chip)",
  background: "var(--gold-100)",
  color: "var(--gold-700)",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
};

const TABS: React.CSSProperties = { display: "flex", borderBottom: "1px solid var(--line-soft)" };

const TAB: React.CSSProperties = {
  flex: 1,
  padding: "7px 4px",
  border: "none",
  borderBottom: "2px solid transparent",
  background: "transparent",
  cursor: "pointer",
  fontSize: 11,
  fontFamily: "var(--font-body)",
};

const BODY: React.CSSProperties = { padding: "10px 12px", overflowY: "auto", fontSize: 11 };

const GROUP_TITLE: React.CSSProperties = {
  margin: "0 0 4px",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: ".04em",
  textTransform: "uppercase",
  color: "var(--ink-400)",
};

const ACCOUNT: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 8,
  width: "100%",
  marginBottom: 3,
  padding: "6px 8px",
  border: "1px solid var(--line)",
  borderRadius: "var(--r-control)",
  textAlign: "left",
  fontFamily: "var(--font-body)",
  fontSize: 11,
};

const PROBE_ROW: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "4px 0",
  borderBottom: "1px solid var(--line-soft)",
};

const CELL: React.CSSProperties = { padding: "3px 0", borderBottom: "1px solid var(--line-soft)", fontSize: 11 };

const MUTED: React.CSSProperties = { margin: "0 0 8px", color: "var(--ink-600)", fontSize: 11, lineHeight: 1.45 };

const ERROR: React.CSSProperties = {
  margin: "0 0 8px",
  padding: "6px 8px",
  borderRadius: "var(--r-control)",
  background: "var(--red-100)",
  color: "var(--red-700)",
  fontSize: 11,
};

const PRIMARY: React.CSSProperties = {
  padding: "6px 12px",
  border: "none",
  borderRadius: "var(--r-button)",
  background: "var(--green-500)",
  color: "var(--on-dark)",
  fontSize: 11,
  fontWeight: 600,
  cursor: "pointer",
  fontFamily: "var(--font-body)",
};
