import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Paginated, Summary, WltBeneficiary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import ListPage from "../../components/ListPage";
import Paginator from "../../components/Paginator";
import { Button, Card } from "../../components/ui";
import { VERIFICATION_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";
import ImportExtractModal from "./ImportExtractModal";
import RegisterWomanModal from "./RegisterWomanModal";

/**
 * The WLT register — step one of the workflow, and the screen that was missing.
 *
 * The module could show a group's roster and a group's readiness, but nothing
 * listed the women themselves, and neither way onto the register had a route:
 * the ELS import had no parser and no endpoint, and the facilitator exception
 * route needed a `youth.Youth` row that no WLT role can create.
 *
 * Both routes are here, side by side, because decision D5 is that they are one
 * hybrid design rather than a main path and a workaround — and because the
 * share taken by each is a number the programme watches.
 */
export default function BeneficiariesPage() {
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<WltBeneficiary[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [registering, setRegistering] = useState(false);
  const [importing, setImporting] = useState(false);

  const verification = params.get("verification_status") ?? "";
  const route = params.get("enrolment_route") ?? "";
  const eligibility = params.get("is_programme_eligible") ?? "";
  const inGroup = params.get("in_group") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? 1));
  const pageSize = 25;

  // Enrolment is not `group_write` — a woreda officer holds the extract and
  // cannot post a ledger entry. `CanEnrolBeneficiaries` is the server's rule;
  // this only avoids offering a button that would 403.
  const canEnrol = Boolean(user?.access.group_write || user?.access.group_scope === "OWN_GEOGRAPHY");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, counters] = await Promise.all([
        api.get<Paginated<WltBeneficiary>>("/wlt/profiles/", {
          params: {
            page,
            page_size: pageSize,
            search,
            verification_status: verification || undefined,
            enrolment_route: route || undefined,
            is_programme_eligible: eligibility || undefined,
            in_group: inGroup || undefined,
          },
        }),
        api.get<Summary>("/wlt/profiles/summary/", {
          params: {
            search,
            enrolment_route: route || undefined,
            is_programme_eligible: eligibility || undefined,
            in_group: inGroup || undefined,
          },
        }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.beneficiariesLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, verification, route, eligibility, page, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setVerification(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("verification_status", next);
    else updated.delete("verification_status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  function setFilter(name: "enrolment_route" | "is_programme_eligible" | "in_group", value: string) {
    const updated = new URLSearchParams(params);
    if (value) updated.set(name, value);
    else updated.delete(name);
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  function clearFilters() {
    const updated = new URLSearchParams(params);
    updated.delete("verification_status");
    updated.delete("enrolment_route");
    updated.delete("is_programme_eligible");
    updated.delete("in_group");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  const filters = [
    { value: "", label: t("wlt.allBeneficiaries"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).map((counter) => ({
      value: counter.value,
      label: counter.label,
      count: counter.count,
    })),
  ];

  return (
    <ListPage
      title={t("wlt.beneficiariesTitle")}
      subtitle={t("wlt.beneficiariesSubtitle", { count: total, scope: user?.role_display ?? "" })}
      searchPlaceholder={t("wlt.beneficiariesSearch")}
      action={
        canEnrol ? (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Button onClick={() => setImporting(true)}>{t("wlt.importExtract")}</Button>
            <Button variant="primary" onClick={() => setRegistering(true)}>
              {t("wlt.registerWoman")}
            </Button>
          </div>
        ) : undefined
      }
      empty={{
        when: !loading && rows.length === 0,
        title: t("wlt.beneficiariesEmpty"),
        body: t("wlt.beneficiariesEmptyBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="card card--muted" aria-label={t("filters.label")} style={{ marginBottom: 20, padding: 16 }}>
            <div className="pill-row" role="group" aria-label={t("wlt.verificationFilter")}>
              {filters.map((filter) => (
                <button
                  key={filter.value || "all"}
                  type="button"
                  className="pill-filter"
                  data-active={filter.value === verification ? "true" : undefined}
                  onClick={() => setVerification(filter.value)}
                >
                  {filter.label}
                  <span className="pill-filter__count">{filter.count}</span>
                </button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginTop: 12 }}>
              <label style={{ minWidth: 190 }}>
                <span className="t-caps">{t("wlt.enrolmentRouteFilter")}</span>
                <select className="input" value={route} onChange={(event) => setFilter("enrolment_route", event.target.value)}>
                  <option value="">{t("filters.all")}</option>
                  <option value="IMPORT">{t("wlt.routeIMPORT")}</option>
                  <option value="FACILITATOR">{t("wlt.routeFACILITATOR")}</option>
                </select>
              </label>
              <label style={{ minWidth: 190 }}>
                <span className="t-caps">{t("wlt.eligibilityFilter")}</span>
                <select className="input" value={eligibility} onChange={(event) => setFilter("is_programme_eligible", event.target.value)}>
                  <option value="">{t("filters.all")}</option>
                  <option value="true">{t("wlt.eligible")}</option>
                  <option value="false">{t("wlt.notEligible")}</option>
                </select>
              </label>
              <label style={{ minWidth: 190 }}>
                <span className="t-caps">{t("wlt.col.group")}</span>
                <select className="input" value={inGroup} onChange={(event) => setFilter("in_group", event.target.value)}>
                  <option value="">{t("filters.all")}</option>
                  <option value="false">{t("wlt.notInAGroupFilter")}</option>
                  <option value="true">{t("wlt.inAGroupFilter")}</option>
                </select>
              </label>
              {(verification || route || eligibility || inGroup) && (
                <Button onClick={clearFilters}>{t("filters.clear")}</Button>
              )}
            </div>
          </div>

          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">{t("wlt.fullName")}</th>
                    <th scope="col">{t("wlt.col.clientId")}</th>
                    <th scope="col">{t("wlt.col.route")}</th>
                    <th scope="col">{t("wlt.status")}</th>
                    <th scope="col">{t("wlt.col.group")}</th>
                    <th scope="col">{t("wlt.col.eligibility")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} onClick={() => navigate(`/wlt/beneficiaries/${row.id}`)}>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate(`/wlt/beneficiaries/${row.id}`);
                          }}
                        >
                          {row.full_name}
                        </button>
                      </td>
                      <td>{row.psnp_client_id || "—"}</td>
                      <td>{t(`wlt.route${row.enrolment_route}`)}</td>
                      <td>
                        <VerificationChip row={row} />
                      </td>
                      <td>
                        <GroupCell row={row} />
                      </td>
                      <td>{row.is_programme_eligible ? t("wlt.eligible") : t("wlt.notEligible")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="only-phone">
            <div className="stack">
              {rows.map((row) => (
                <Card key={row.id} onClick={() => navigate(`/wlt/beneficiaries/${row.id}`)}>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <strong>{row.full_name}</strong>
                    <VerificationChip row={row} />
                  </div>
                  <div className="t-meta">
                    {row.psnp_client_id || t("wlt.noClientId")} · {t(`wlt.route${row.enrolment_route}`)} ·{" "}
                    {row.is_programme_eligible ? t("wlt.eligible") : t("wlt.notEligible")}
                  </div>
                  <div style={{ marginTop: 4 }}>
                    <GroupCell row={row} />
                  </div>
                </Card>
              ))}
            </div>
          </div>

          <Paginator total={total} pageSize={pageSize} label={t("wlt.beneficiariesPages")} />

          <RegisterWomanModal open={registering} onClose={() => setRegistering(false)} onDone={load} />
          <ImportExtractModal open={importing} onClose={() => setImporting(false)} onDone={load} />
        </>
      )}
    </ListPage>
  );
}

/**
 * Which group she is in, or that she is in none.
 *
 * "Not in a group" is written out rather than left as a dash. A dash in this
 * column would read as missing data, and the whole point of the column is that
 * *no group* is a definite, actionable answer — she is who a facilitator is
 * looking for when she is seating a new group.
 *
 * Not a status chip: she is not in one of a fixed set of states, and giving
 * this a colour would compete with the verification chip beside it, which is
 * the column that does carry a status.
 */
function GroupCell({ row }: { row: WltBeneficiary }) {
  const { t } = useLang();
  if (!row.current_group) {
    return <span style={{ color: "var(--ink-400)" }}>{t("wlt.notInAGroup")}</span>;
  }
  return (
    <span>
      {row.current_group.name}
      <span className="t-meta" style={{ display: "block" }}>
        {t("wlt.joinedOn", { date: row.current_group.joined_on })}
      </span>
    </span>
  );
}

function VerificationChip({ row }: { row: WltBeneficiary }) {
  const { t } = useLang();
  const tone = VERIFICATION_TONE[row.verification_status];
  return (
    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
      <span className="chip__mark" aria-hidden>
        {tone.mark}
      </span>
      {t(`wlt.verification${row.verification_status}`)}
    </span>
  );
}
