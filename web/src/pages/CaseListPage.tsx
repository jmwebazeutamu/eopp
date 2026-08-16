import { App } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { CaseListRow, CaseStatus, Paginated } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import CaseFormModal from "../components/CaseFormModal";
import MiniDashboard, { SearchBox } from "../components/MiniDashboard";
import { Button, CaseStatusChip, Card, PageHeader } from "../components/ui";
import { CASE_TONE } from "../design/status";
import { useLang } from "../i18n/LanguageContext";

/**
 * The caseload — the handoff's Cases list.
 *
 * A case manager carries 80–200 youth, so the screen is built for scanning at
 * that volume: a sticky filter bar, no zebra striping, and `Next action` as a
 * first-class column because it is what staff actually read down. Filters live
 * in the URL so a row someone found can be sent to a colleague, and the back
 * button returns to the same list rather than an unfiltered one.
 *
 * Chips rather than dropdowns — on a phone a dropdown hides the options that
 * matter and costs two taps each.
 */

const PAGE_SIZE = 25;

/** Counters take their colour from the status they filter to. */
const CASE_COUNTER_TONES = Object.fromEntries(
  Object.entries(CASE_TONE).map(([status, tone]) => [status, { fg: tone.fg }]),
);

export default function CaseListPage() {
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<CaseListRow[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);

  const woreda = params.get("woreda") ?? "";
  const status = (params.get("case_status") ?? "") as CaseStatus | "";
  const query = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1);

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params);
      if (value) next.set(key, value);
      else next.delete(key);
      // Any filter change invalidates the page cursor.
      if (key !== "page") next.delete("page");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  // The user's own woredas are the only ones their scope can return, so they
  // are the only chips worth offering.
  const woredas = useMemo(() => user?.woreda_assignment ?? [], [user]);

  const canOpenCase = (user?.access.case_write ?? false) && user?.access.case_scope !== "OWN_CASELOAD";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<CaseListRow>>("/cases/", {
        params: {
          page,
          page_size: PAGE_SIZE,
          case_status: status || undefined,
          woreda: woreda || undefined,
          search: query || undefined,
        },
      });
      setRows(response.data.results);
      setCount(response.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load cases."));
    } finally {
      setLoading(false);
    }
  }, [page, status, woreda, query, message]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page stack">
      <PageHeader
        title={t("cases.title")}
        subtitle={t("cases.subtitle", { count, name: user?.full_name ?? "" })}
        action={
          canOpenCase ? (
            <Button variant="primary" onClick={() => setFormOpen(true)}>
              {t("cases.new")}
            </Button>
          ) : undefined
        }
      />

      {/* Sticky so the filters stay reachable while scrolling 200 rows. */}
      <div
        style={{
          position: "sticky",
          top: 0,
          zIndex: 3,
          background: "var(--paper)",
          paddingBottom: 8,
          display: "flex",
          flexDirection: "column",
          gap: 8,
        }}
      >
        <SearchBox placeholder={t("cases.search")} />

        {woredas.length > 1 && (
          <div className="chip-row">
            <FilterChip active={!woreda} onClick={() => setParam("woreda", "")}>
              {t("cases.all")}
            </FilterChip>
            {woredas.map((name) => (
              <FilterChip key={name} active={woreda === name} onClick={() => setParam("woreda", name)}>
                {name}
              </FilterChip>
            ))}
          </div>
        )}

      </div>

      {/* The counters carry the status filter now — the chip row said the same
          thing without the numbers. */}
      <MiniDashboard resource="/cases" params={{ woreda: woreda || undefined }} tones={CASE_COUNTER_TONES} />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {!loading && rows.length === 0 && (
        <Card>
          <div className="t-meta">{t("cases.none")}</div>
        </Card>
      )}

      {rows.length > 0 && (
        <>
          {/* Laptop: a table. Phone: purpose-built cards, not a shrunken table. */}
          <div className="only-laptop">
            <Card style={{ padding: 0, overflow: "hidden" }}>
              <table className="table">
                <thead>
                  <tr>
                    <th>{t("cases.col.name")}</th>
                    <th>{t("cases.col.status")}</th>
                    <th>{t("cases.col.woreda")}</th>
                    <th>{t("cases.col.manager")}</th>
                    <th>{t("cases.col.activity")}</th>
                    <th>{t("cases.col.next")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} onClick={() => navigate(`/cases/${row.id}`)}>
                      <td>
                        <div style={{ fontSize: 14, fontWeight: 600 }}>{row.youth.full_name}</div>
                        <div style={{ color: "var(--ink-400)" }}>
                          {row.youth.age} · {row.youth.sex}
                        </div>
                      </td>
                      <td>
                        <CaseStatusChip status={row.case_status} label={row.case_status_display} />
                      </td>
                      <td>
                        {row.woreda} · {row.youth.kebele}
                      </td>
                      <td>{row.case_manager_name}</td>
                      <td>{relativeDays(row.days_since_activity)}</td>
                      <td>{row.next_action || <span style={{ color: "var(--ink-400)" }}>—</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="only-phone">
            {rows.map((row) => (
              <Card key={row.id} onClick={() => navigate(`/cases/${row.id}`)} style={{ padding: "12px 14px" }}>
                <div style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between" }}>
                  <span className="t-body-strong">{row.youth.full_name}</span>
                  <CaseStatusChip status={row.case_status} label={row.case_status_display} />
                </div>
                <div className="t-meta">
                  {row.youth.age} · {row.youth.sex} · {row.woreda} {row.youth.kebele}
                </div>
                <div className="card__rule" />
                <div style={{ fontSize: 13 }}>
                  <strong>{t("cases.nextAction")}:</strong> {row.next_action || "—"}
                </div>
                <div className="t-meta">
                  {t("cases.lastActivity")}: {relativeDays(row.days_since_activity)}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {count > PAGE_SIZE && (
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <Button size="sm" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>
            Previous
          </Button>
          <span className="t-meta">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, count)} of {count}
          </span>
          <Button size="sm" disabled={page * PAGE_SIZE >= count} onClick={() => setParam("page", String(page + 1))}>
            Next
          </Button>
        </div>
      )}

      <CaseFormModal open={formOpen} record={null} onClose={() => setFormOpen(false)} onSaved={() => load()} />
    </div>
  );
}

function FilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" className="chip-filter" aria-pressed={active} onClick={onClick}>
      {children}
    </button>
  );
}

/** "today" reads better than "0 days ago" in the column staff scan. */
function relativeDays(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}
