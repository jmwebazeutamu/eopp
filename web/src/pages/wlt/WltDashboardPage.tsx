import { App } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api, errorMessage } from "../../api/client";
import { CapsLabel, Card } from "../../components/ui";
import { useLang } from "../../i18n/LanguageContext";
import WltTierTabs from "./WltTierTabs";
import { WLT_TIERS } from "./wltTiers";

/**
 * Tiers 2 to 4 of `docs/dashboard_handoff_wlt`, in the app.
 *
 * The handoff puts these three in Metabase. The programme overruled the same
 * placement on the youth side, and the same reasons hold: the §7 boundary stays
 * in the ORM where it is tested, every rate goes through one rules module, and
 * Metabase is not deployed.
 *
 * No chart library — the brief's 3G constraint. Bars are divs, distributions are
 * bins with their counts beside them, and **every figure carries its
 * denominator**. A suppressed rate says "too few to assess" and never 0%.
 */
export default function WltDashboardPage() {
  const { tier = "woreda" } = useParams();
  const { message } = App.useApp();
  const { t } = useLang();

  // The payload is held **with the tier it came from**. Each tier answers a
  // different shape, so a bare `data` still holding the previous tab's reply
  // while the next one loads renders the Results cards against the Programme
  // payload — which is not a blank card, it is a crash on the first field.
  const [loaded, setLoaded] = useState<{ tier: string; payload: Record<string, any> } | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await api.get(`/wlt/groups/dashboard/${tier}/`);
      setLoaded({ tier, payload: response.data });
    } catch (error) {
      message.error(errorMessage(error, t("wlt.homeLoadFailed")));
    }
  }, [tier, message, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const meta = WLT_TIERS.find((entry) => entry.path === tier);
  const data = loaded && loaded.tier === tier ? loaded.payload : null;

  if (!data) return <div className="page t-meta">{t("common.loading")}</div>;

  return (
    <div className="page stack">
      <div>
        <h1 className="group-title">{meta ? t(meta.titleKey) : ""}</h1>
        <p className="t-meta" style={{ margin: "4px 0 0" }}>
          {meta ? t(meta.whyKey) : ""} · {t("wlt.asOf", { date: data.as_of })}
        </p>
      </div>

      <WltTierTabs />

      {tier === "woreda" && <Woreda data={data} />}
      {tier === "programme" && <Programme data={data} />}
      {tier === "results" && <Results data={data} />}
    </div>
  );
}

function Woreda({ data }: { data: Record<string, any> }) {
  const { t } = useLang();
  return (
    <div className="record-overview">
      <div className="stack">
        <Card>
          {/* Card one, because it is the officer's job. Age, not just count:
              a phase transition sitting eighteen days is the finding, and an
              average of four days hides it entirely. */}
          <CapsLabel>{t("wlt.woApprovalQueue")}</CapsLabel>
          <div className="queue-counts" style={{ marginTop: 10 }}>
            {data.approval_queue.map((row: any) => (
              <div key={row.label} className="queue-count" data-tone={row.count ? "due" : "calm"}>
                <strong className="tabular">{row.count}</strong>
                <span className="t-meta">
                  {row.label}
                  {row.oldest_days !== null && ` · ${t("wlt.woOldest", { days: row.oldest_days })}`}
                </span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          {/* The coaching card. "Meeting adherence: 14 groups short" is a
              training plan; a count of blocked groups is not. */}
          <CapsLabel>{t("wlt.woBlocking")}</CapsLabel>
          <Bars
            rows={data.blocking_p2.rows.map((row: any) => ({
              label: row.condition,
              value: row.groups_short,
              text: t("wlt.woGroupsShort", { count: row.groups_short }),
            }))}
          />
          <p className="t-meta" style={{ margin: "10px 0 0" }}>{data.blocking_p2.note}</p>
        </Card>

        <Card>
          <CapsLabel>{t("wlt.woRisk")}</CapsLabel>
          <Rows
            rows={data.risk_register.map((row: any) => ({
              key: `${row.group}-${row.reason}`,
              title: row.group_name,
              meta: row.reason,
              right: t("wlt.daysOpen", { days: row.days_open }),
              tone: "due" as const,
            }))}
          />
        </Card>
      </div>

      <div className="stack">
        <Card>
          {/* Phase is ordered, so the count rides on the row: a 100% bar over
              three groups and one over thirty look identical and are not. */}
          <CapsLabel>{t("wlt.woByPhase")}</CapsLabel>
          <Rows
            rows={data.groups_by_phase.map((row: any) => ({
              key: row.kebele,
              title: row.kebele,
              meta: `Forming ${row.FORMING} · P1 ${row.P1} · P2 ${row.P2} · P3+ ${row["P3+"]}`,
              right: t("wlt.groupsN", { count: row.total }),
              tone: "calm" as const,
            }))}
          />
        </Card>

        <Card>
          {/* Counts only, never a rate ranking: at five to ten groups a rate is
              noise and creates pressure to stop recording bad news. */}
          <CapsLabel>{t("wlt.woLoad")}</CapsLabel>
          <Rows
            rows={data.facilitator_load.map((row: any) => ({
              key: row.facilitator,
              title: row.facilitator,
              meta: `${row.meetings_recorded} meeting(s) recorded`,
              right: t("wlt.groupsN", { count: row.groups }),
              tone: "calm" as const,
            }))}
          />
        </Card>

        <Unavailable card={data.cla_readiness} title="CLA readiness" />
      </div>
    </div>
  );
}

function Programme({ data }: { data: Record<string, any> }) {
  const { t } = useLang();
  return (
    <div className="record-overview">
      <div className="stack">
        <Card>
          {/* Binned at the gate, in weeks. The count under twelve is the number
              of groups the P2 gate is currently holding. Never a mean — that
              would be carried by the largest group and would name nobody. */}
          <CapsLabel>{t("wlt.pgFund")}</CapsLabel>
          <p className="t-meta" style={{ margin: "2px 0 0" }}>{t("wlt.pgFundUnit")}</p>
          <Bars
            rows={data.fund_adequacy.bins.map((bin: any) => ({
              label: bin.band,
              value: bin.groups,
              text: String(bin.groups),
            }))}
          />
          {data.fund_adequacy.not_measured > 0 && (
            <p className="t-meta" style={{ margin: "8px 0 0" }}>
              {data.fund_adequacy.not_measured} {t("wlt.notMeasured")}
            </p>
          )}
        </Card>

        <Card>
          <CapsLabel>{t("wlt.pgCompliance")}</CapsLabel>
          <Bars
            rows={data.savings_compliance.bins.map((bin: any) => ({
              label: `${bin.band}%`,
              value: bin.groups,
              text: String(bin.groups),
            }))}
          />
          {data.savings_compliance.not_measured > 0 && (
            <p className="t-meta" style={{ margin: "8px 0 0" }}>
              {data.savings_compliance.not_measured} {t("wlt.notMeasured")}
            </p>
          )}
        </Card>

        <Card>
          <CapsLabel>{t("wlt.pgHealth")}</CapsLabel>
          <div className="tablewrap">
            <Rows
              rows={data.data_health.rows.map((row: any) => ({
                key: row.issue,
                title: row.issue,
                // The consequence column: a list of data problems is a chore, a
                // list saying what each costs is a work queue.
                meta: row.consequence,
                right: String(row.count),
                tone: row.count ? ("due" as const) : ("calm" as const),
              }))}
            />
          </div>
        </Card>
      </div>

      <div className="stack">
        <Card>
          {/* Sorted by birr outstanding, never by PAR: ranking on PAR at these
              denominators sorts by luck and cannot be withdrawn once published. */}
          <CapsLabel>{t("wlt.pgPortfolio")}</CapsLabel>
          <Rows
            rows={data.portfolio_quality.rows.map((row: any) => ({
              key: row.place,
              title: row.place,
              meta: `${row.groups_lending} lending · ${row.at_risk_etb} ETB at risk`,
              right: `${row.outstanding_etb} ETB`,
              tone: "calm" as const,
            }))}
          />
          <p className="t-meta" style={{ margin: "10px 0 0" }}>{data.portfolio_quality.note}</p>
        </Card>

        <Card>
          {/* Median, never mean, with n — and the maturation guard beside it. */}
          <CapsLabel>{t("wlt.pgProgression")}</CapsLabel>
          <Figure
            value={
              data.phase_progression.median_weeks !== null
                ? t("wlt.medianWeeks", { weeks: data.phase_progression.median_weeks })
                : t("wlt.notMeasured")
            }
            meta={`n=${data.phase_progression.n} · ${t("wlt.notEligibleCount", {
              count: data.phase_progression.not_yet_eligible,
            })}`}
          />
        </Card>

        <Card>
          <CapsLabel>{t("wlt.pgSurvival")}</CapsLabel>
          <Rows
            rows={data.cohort_survival.map((row: any) => ({
              key: row.cohort_month,
              title: row.cohort_month,
              meta: `${row.surviving}/${row.size} surviving · ${row.dormant} dormant · ${row.ended} ended`,
              right: row.survival.percent === null ? row.survival.note : `${row.survival.percent}%`,
              tone: "calm" as const,
            }))}
          />
        </Card>
      </div>
    </div>
  );
}

function Results({ data }: { data: Record<string, any> }) {
  const { t } = useLang();
  const money = data.savings_and_portfolio;
  const maturity = data.group_maturity;

  return (
    <div className="record-overview">
      <div className="stack">
        <Card>
          {/* The maturation guard, made visible. "31 of 88 eligible; 162 not
              yet eligible" is the honest sentence; "31 of 250" is the false
              negative the handoff warns about. */}
          <CapsLabel>{t("wlt.meMaturity")}</CapsLabel>
          <Figure
            value={`${maturity.attained} / ${maturity.eligible}`}
            meta={`${t("wlt.notEligibleCount", { count: maturity.not_yet_eligible })} · ${
              maturity.rate.percent === null ? maturity.rate.note : `${maturity.rate.percent}%`
            }`}
          />
        </Card>

        <Unavailable card={data.results_framework} title={t("wlt.meFramework")} />
      </div>

      <div className="stack">
        <Card>
          <CapsLabel>{t("wlt.meSavings")}</CapsLabel>
          <div className="money-well">
            <div className="t-meta">{money.label}</div>
            <div className="tabular money-well__figure">
              {money.fund_etb} <span className="money-well__unit">ETB</span>
            </div>
          </div>
          <div className="stat-wells">
            <div className="stat-well">
              <strong className="tabular">{money.members}</strong>
              <span className="t-meta">members</span>
            </div>
            <div className="stat-well">
              <strong className="tabular">{money.fund_per_member_etb ?? "—"}</strong>
              <span className="t-meta">per member (ETB)</span>
            </div>
            <div className="stat-well">
              <strong className="tabular">{money.groups_lending}</strong>
              <span className="t-meta">groups lending</span>
            </div>
          </div>
          {/* OQ-1 is undecided, so part of this may be a pending distribution
              rather than an accumulated asset. Said on the card, not in a note
              somebody has to find. */}
          <p className="t-meta" style={{ margin: "12px 0 0" }}>{money.caveat}</p>
        </Card>
      </div>
    </div>
  );
}

/** Hand-built bars — no chart library, per the brief's 3G constraint. */
function Bars({ rows }: { rows: { label: string; value: number; text: string }[] }) {
  const max = Math.max(1, ...rows.map((row) => row.value));
  return (
    <div className="stack" style={{ gap: 8, marginTop: 10 }}>
      {rows.map((row) => (
        <div key={row.label}>
          <div className="indicator-row">
            <span>{row.label}</span>
            <strong className="tabular">{row.text}</strong>
          </div>
          <div className="dist">
            {/* A non-zero value always gets a visible sliver; a true zero draws
                nothing, so "none" and "a few" never look alike. */}
            <span
              className="dist__fill"
              style={{ width: row.value === 0 ? 0 : `${Math.max(4, (row.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function Rows({
  rows,
}: {
  rows: { key: string; title: string; meta: string; right: string; tone: "late" | "due" | "calm" }[];
}) {
  const { t } = useLang();
  if (rows.length === 0) return <p className="t-meta" style={{ margin: "8px 0 0" }}>{t("wlt.nothingHere")}</p>;
  return (
    <div style={{ marginTop: 8 }}>
      {rows.map((row) => (
        <div key={row.key} className="queue-row" style={{ cursor: "default" }}>
          <span style={{ minWidth: 0 }}>
            <span className="t-body-strong" style={{ display: "block" }}>{row.title}</span>
            <span className="t-meta" style={{ display: "block" }}>{row.meta}</span>
          </span>
          <span className="due-cell" data-tone={row.tone}>{row.right}</span>
        </div>
      ))}
    </div>
  );
}

function Figure({ value, meta }: { value: string; meta: string }) {
  return (
    <div style={{ marginTop: 8 }}>
      <div className="tabular t-metric-sm">{value}</div>
      <div className="t-meta">{meta}</div>
    </div>
  );
}

/**
 * A card with no source in this build.
 *
 * **Not zero.** A zero is a finding; this is an absence of evidence, and the
 * two must not render alike.
 */
function Unavailable({ card, title }: { card: { available: boolean; note: string }; title: string }) {
  const { t } = useLang();
  if (card.available) return null;
  return (
    <Card>
      <CapsLabel>{title}</CapsLabel>
      <p className="t-meta" style={{ margin: "8px 0 0" }}>
        <strong>{t("wlt.notAvailable")}</strong> — {card.note}
      </p>
    </Card>
  );
}
