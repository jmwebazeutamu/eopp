import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../api/client";
import type { Paginated, Youth } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import MiniDashboard, { SearchBox } from "../components/MiniDashboard";
import { scopeParam, useScope } from "../components/shell/ScopeContext";
import YouthDetailModal from "../components/YouthDetailModal";
import YouthFormModal from "../components/YouthFormModal";
import YouthImportModal from "../components/YouthImportModal";
import { Button, Card, MutedChip, PageHeader, maskPhone } from "../components/ui";
import { useLang } from "../i18n/LanguageContext";

/**
 * The youth registry — a table on laptop, cards on a phone.
 *
 * Phone numbers are masked here with **no reveal**. The case screen has a
 * deliberate per-view reveal because a case manager working one youth has a
 * reason to see it; a registry of thousands does not, and an unmasked column
 * scrolling past in a shared office is the exact exposure the brief names.
 */

const PAGE_SIZE = 24;

export default function YouthListPage() {
  const scope = useScope();
  const { user } = useAuth();
  const { message } = App.useApp();
  const { t } = useLang();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const [rows, setRows] = useState<Youth[]>([]);
  const [count, setCount] = useState(0);
  const [withCase, setWithCase] = useState(0);
  const [loading, setLoading] = useState(true);
  const [viewing, setViewing] = useState<Youth | null>(null);
  const [editing, setEditing] = useState<Youth | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const query = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1);
  const canWrite = user?.access.case_write ?? false;

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(params);
      if (value) next.set(key, value);
      else next.delete(key);
      if (key !== "page") next.delete("page");
      setParams(next, { replace: true });
    },
    [params, setParams],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, uncased] = await Promise.all([
        api.get<Paginated<Youth>>("/youth/", {
          params: {
          page,
          page_size: PAGE_SIZE,
          search: query || undefined,
          without_case: params.get("without_case") ?? undefined,
        },
        }),
        // Only the count is wanted, so ask for the smallest page the API will
        // serve rather than pulling every uncased youth to length an array.
        api.get<Paginated<Youth>>("/youth/", { params: { without_case: true, page_size: 1 } }),
      ]);
      setRows(list.data.results);
      setCount(list.data.count);
      setWithCase(list.data.count - uncased.data.count);
    } catch (error) {
      message.error(errorMessage(error, "Could not load youth records."));
    } finally {
      setLoading(false);
    }
  }, [page, query, params, message]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Selecting a youth shows the record; it does not put it into a form. */
  function openRecord(youth: Youth) {
    setViewing(youth);
  }

  function editFromRecord(youth: Youth) {
    setViewing(null);
    setEditing(youth);
    setFormOpen(true);
  }

  return (
    <div className="page stack">
      <PageHeader
        title={t("registry.title")}
        subtitle={t("registry.subtitle", { registered: count, withCase, scope: scope.label })}
        action={
          canWrite ? (
            // Import is secondary to registering one youth: the single form is
            // the daily path, and a register arrives a few times a season.
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button onClick={() => setImportOpen(true)}>{t("registry.import")}</Button>
              <Button
                variant="primary"
                onClick={() => {
                  setEditing(null);
                  setFormOpen(true);
                }}
              >
                {t("registry.register")}
              </Button>
            </div>
          ) : undefined
        }
      />

      <SearchBox placeholder={t("cases.search")} />

      <MiniDashboard resource="/youth" params={scopeParam(scope.woreda)} />

      {loading && <div className="t-meta">{t("common.loading")}</div>}

      {/* Laptop: a table, same shape as the caseload. Phone: cards. */}
      <div className="only-laptop">
        <Card style={{ padding: 0, overflow: "hidden" }}>
          <table className="table">
            <thead>
              <tr>
                <th>{t("cases.col.name")}</th>
                <th>{t("registry.col.id")}</th>
                <th>{t("cases.col.woreda")}</th>
                <th>{t("case.phone")}</th>
                <th>{t("registry.consent")}</th>
                <th>{t("registry.col.case")}</th>
              </tr>
            </thead>
            <tbody>
              {/* Every role may open a record; only some may then edit it. */}
              {rows.map((youth) => (
                <tr key={youth.id} onClick={() => openRecord(youth)}>
                  <td>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{youth.full_name}</div>
                    <div style={{ color: "var(--ink-400)" }}>
                      {youth.age} · {youth.sex}
                    </div>
                  </td>
                  <td className="tabular">{youth.national_or_kebele_id || "—"}</td>
                  <td>
                    {youth.woreda} · {youth.kebele}
                  </td>
                  {/* Masked with no reveal anywhere on this screen. */}
                  <td className="tabular">
                    {youth.phone_number ? maskPhone(youth.phone_number) : t("common.none")}
                  </td>
                  <td>{youth.consent_date ?? t("common.none")}</td>
                  <td>
                    <CasePill youth={youth} onOpenCase={(id) => navigate(`/cases/${id}`)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <div className="only-phone">
        {rows.map((youth) => (
          <Card key={youth.id} onClick={() => openRecord(youth)}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-start", justifyContent: "space-between" }}>
              <span className="t-body-strong">{youth.full_name}</span>
              <CasePill youth={youth} onOpenCase={(id) => navigate(`/cases/${id}`)} />
            </div>

            <div className="t-meta">
              {youth.national_or_kebele_id || "—"} · {youth.age} · {youth.sex} · {youth.woreda} {youth.kebele}
            </div>

            <div className="card__rule" />

            <div style={{ fontSize: 13 }} className="tabular">
              {t("case.phone")}: {youth.phone_number ? maskPhone(youth.phone_number) : t("common.none")}
            </div>
            <div style={{ fontSize: 13 }}>
              {t("registry.consent")}: {youth.consent_date ?? t("common.none")}
            </div>
          </Card>
        ))}
      </div>

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

      <YouthDetailModal
        youth={viewing}
        canEdit={canWrite}
        onClose={() => setViewing(null)}
        onEdit={editFromRecord}
      />

      <YouthFormModal
        open={formOpen}
        youth={editing}
        onClose={() => setFormOpen(false)}
        onSaved={() => {
          setFormOpen(false);
          void load();
        }}
      />

      <YouthImportModal open={importOpen} onClose={() => setImportOpen(false)} onImported={() => void load()} />
    </div>
  );
}

/**
 * The case pill, which opens the case rather than the youth record.
 *
 * It reads as a link to the case, so it behaves as one: clicking it navigates
 * there and stops the row's own handler, which would otherwise open the youth
 * record on top of the navigation.
 */
function CasePill({ youth, onOpenCase }: { youth: Youth; onOpenCase: (caseId: string) => void }) {
  const { t } = useLang();

  if (!youth.has_open_case || !youth.open_case_id) return <MutedChip>{t("registry.noCase")}</MutedChip>;

  return (
    <button
      type="button"
      className="chip"
      title={t("registry.goToCase")}
      style={{
        color: "var(--green-ink)",
        background: "var(--green-100)",
        borderColor: "var(--green-border)",
        cursor: "pointer",
        font: "inherit",
        fontSize: 13,
        fontWeight: 600,
        fontFamily: "var(--font-body)",
      }}
      onClick={(event) => {
        event.stopPropagation();
        onOpenCase(youth.open_case_id!);
      }}
    >
      {t("registry.openCase")} →
    </button>
  );
}
