import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import type { Paginated, Summary, WltGroup } from "../../api/types";
import ListPage from "../../components/ListPage";
import { Card } from "../../components/ui";
import { PHASE_LABEL, WLT_GROUP_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The SHG register — the way into everything else in the module.
 *
 * Scoped server-side: a facilitator sees the groups she runs, a woreda officer
 * her woreda's, a region officer her region's. The counter row is the server's
 * (`/wlt/groups/summary/`), so a count cannot drift from the list it filters to.
 */
export default function GroupsPage() {
  const { message } = App.useApp();
  const { t } = useLang();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const [rows, setRows] = useState<WltGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  const status = params.get("status") ?? "";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const search = params.get("q") || undefined;
      const [list, counters] = await Promise.all([
        api.get<Paginated<WltGroup>>("/wlt/groups/", {
          params: { page_size: 200, search, status: status || undefined },
        }),
        api.get<Summary>("/wlt/groups/summary/", { params: { search } }),
      ]);
      setRows(list.data.results);
      setTotal(list.data.count);
      setSummary(counters.data);
    } catch (error) {
      message.error(errorMessage(error, t("wlt.groupsLoadFailed")));
    } finally {
      setLoading(false);
    }
  }, [params, status, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  function setStatus(next: string) {
    const updated = new URLSearchParams(params);
    if (next) updated.set("status", next);
    else updated.delete("status");
    updated.delete("page");
    setParams(updated, { replace: true });
  }

  const filters = [
    { value: "", label: t("wlt.allGroups"), count: summary?.total ?? 0 },
    ...(summary?.counters ?? []).map((counter) => ({
      value: counter.value,
      label: counter.label,
      count: counter.count,
    })),
  ];

  return (
    <ListPage
      title={t("wlt.groupsTitle")}
      subtitle={t("wlt.groupsSubtitle", { count: total })}
      searchPlaceholder={t("wlt.groupsSearch")}
      empty={{
        when: !loading && rows.length === 0,
        title: t("wlt.noGroups"),
        body: t("wlt.noGroupsBody"),
      }}
    >
      {(density) => (
        <>
          {loading && <div className="t-meta">{t("common.loading")}</div>}

          <div className="pill-row" role="group" aria-label={t("filters.label")} style={{ marginBottom: 20 }}>
            {filters.map((filter) => (
              <button
                key={filter.value || "all"}
                type="button"
                className="pill-filter"
                data-active={filter.value === status ? "true" : undefined}
                onClick={() => setStatus(filter.value)}
              >
                {filter.label}
                <span className="pill-filter__count">{filter.count}</span>
              </button>
            ))}
          </div>

          <div className="only-laptop">
            <Card className="table-card">
              <table className={`table ${density}`}>
                <thead>
                  <tr>
                    <th scope="col">{t("wlt.group")}</th>
                    <th scope="col">{t("wlt.kebele")}</th>
                    <th scope="col">{t("wlt.members")}</th>
                    <th scope="col">{t("wlt.status")}</th>
                    <th scope="col">{t("wlt.phase")}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((group) => (
                    <tr key={group.id} onClick={() => navigate(`/wlt/groups/${group.id}`)}>
                      <td>
                        <button
                          type="button"
                          className="row-link"
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate(`/wlt/groups/${group.id}`);
                          }}
                        >
                          {group.name}
                        </button>
                        <div style={{ color: "var(--ink-400)" }}>{group.facilitator_name}</div>
                      </td>
                      <td>{group.kebele_name}</td>
                      <td>{group.members_current}</td>
                      <td>
                        <StatusChip group={group} />
                      </td>
                      {/* The short label. `phase_display` explains what a phase
                          is, which belongs on the readiness card and not in a
                          column read down six rows. */}
                      <td>{group.current_phase ? PHASE_LABEL[group.current_phase] : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div className="only-phone">
            <div className="stack">
              {rows.map((group) => (
                <Card key={group.id} onClick={() => navigate(`/wlt/groups/${group.id}`)}>
                  <div style={{ display: "flex", gap: 12, alignItems: "baseline", justifyContent: "space-between" }}>
                    <strong>{group.name}</strong>
                    <StatusChip group={group} />
                  </div>
                  <div className="t-meta">
                    {group.kebele_name} · {t("wlt.membersCount", { count: group.members_current })} ·{" "}
                    {group.current_phase ? PHASE_LABEL[group.current_phase] : t("wlt.noPhase")}
                  </div>
                </Card>
              ))}
            </div>
          </div>
        </>
      )}
    </ListPage>
  );
}

function StatusChip({ group }: { group: WltGroup }) {
  const tone = WLT_GROUP_TONE[group.status];
  return (
    <span className="chip" style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}>
      <span className="chip__mark" aria-hidden>
        {tone.mark}
      </span>
      {group.status_display}
    </span>
  );
}
