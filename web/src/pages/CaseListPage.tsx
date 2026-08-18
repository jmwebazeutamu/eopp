import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { CaseListRow, Paginated } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import CaseFormModal from "../components/CaseFormModal";
import ListPage from "../components/ListPage";
import { scopeParam, useScope } from "../components/shell/ScopeContext";
import { Button, CaseStatusChip, Card } from "../components/ui";
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
/**
 * The chip palette, taken whole.
 *
 * This used to hand the counter cards `{ fg: tone.fg }` alone. `CASE_TONE` is a
 * *chip* palette — `PLACED.fg` is white, meant to sit on `--green-700` — so the
 * Placed count was painted white on a white card and rendered invisible while
 * the other four showed. A tone is a background and a foreground together.
 */
const CASE_COUNTER_TONES = CASE_TONE;

export default function CaseListPage() {
  const scope = useScope();
  const { user } = useAuth();
  const seesNoCaseRecords = user?.access.case_scope === "LINKED";
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<CaseListRow[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);

  // The chip row writes whatever parameter the server names on its counters,
  // which is `case_status__in` — a comma-separated list, because the chips
  // multi-select. Reading `case_status` here meant the URL changed, the chip
  // lit up, and the list never filtered.
  const status = params.get("case_status__in") ?? "";
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


  const canOpenCase = (user?.access.case_write ?? false) && user?.access.case_scope !== "OWN_CASELOAD";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.get<Paginated<CaseListRow>>("/cases/", {
        params: {
          page,
          page_size: PAGE_SIZE,
          case_status__in: status || undefined,
          ...scopeParam(scope.woreda),
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
  }, [page, status, scope.woreda, query, message]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <ListPage
      title={t("cases.title")}
      subtitle={t("cases.subtitle", { count, scope: scope.label })}
      action={
        canOpenCase ? (
          <Button variant="primary" onClick={() => setFormOpen(true)}>
            {t("cases.new")}
          </Button>
        ) : undefined
      }
      searchPlaceholder={t("cases.search")}
      resource="/cases"
      chipParams={scopeParam(scope.woreda)}
      chipTones={CASE_COUNTER_TONES}
      empty={{
        when: !loading && rows.length === 0,
        title: t(seesNoCaseRecords ? "empty.casesLinked" : "empty.cases"),
        body: t(seesNoCaseRecords ? "empty.casesLinkedBody" : "empty.casesBody"),
        action: canOpenCase ? (
          <Button variant="primary" onClick={() => setFormOpen(true)}>
            {t("cases.new")}
          </Button>
        ) : undefined,
      }}
    >
      {(density) => (
        <>
      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {rows.length > 0 && (
        <>
          {/* Laptop: a table. Phone: purpose-built cards, not a shrunken table. */}
          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">{t("cases.col.name")}</th>
                    <th scope="col">{t("cases.col.status")}</th>
                    <th scope="col">{t("cases.col.woreda")}</th>
                    <th scope="col">{t("cases.col.manager")}</th>
                    <th scope="col">{t("cases.col.activity")}</th>
                    <th scope="col">{t("cases.col.next")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} onClick={() => navigate(`/cases/${row.id}`)}>
                      <td>
                        <Link className="row-link" to={`/cases/${row.id}`} onClick={(e) => e.stopPropagation()}>
                          {row.youth.full_name}
                        </Link>
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
                  {row.youth.age} · {row.youth.sex} · {row.woreda} · {row.youth.kebele}
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
        </>
      )}
    </ListPage>
  );
}

/** "today" reads better than "0 days ago" in the column staff scan. */
function relativeDays(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}
