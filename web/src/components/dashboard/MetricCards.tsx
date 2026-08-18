import type { CSSProperties } from "react";

import type { ProgrammeDashboard } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { CapsLabel, Card } from "../ui";
import type { Rate } from "../../api/types";
import { splitSegments } from "./dashboardLayout";
import { NotYet } from "./panels";

/**
 * The three cards across the top of the handoff's screen 8.
 *
 * The first is the goal, so it is the only element on the screen carrying
 * `--green-900` — the handoff reserves that weight for the thing the programme
 * is actually for. The other two are white cards of equal size beside it.
 */

const BIG_NUMBER: CSSProperties = {
  fontSize: 44,
  lineHeight: 1.05,
  fontWeight: 700,
  fontVariantNumeric: "tabular-nums",
  marginTop: 6,
};

export function MetricCards({ metrics }: { metrics: ProgrammeDashboard["metrics"] }) {
  const { t } = useLang();
  const placements = metrics.placements_this_quarter;
  const retained = metrics.retained_six_months;
  const gender = metrics.gender_split;

  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
      {/* The goal card. */}
      <Card style={{ background: "var(--green-900)", borderColor: "var(--green-900)" }}>
        <CapsLabel style={{ color: "var(--gold-300)" }}>{t("dash.placements")}</CapsLabel>
        {placements.available ? (
          <>
            <div style={{ ...BIG_NUMBER, color: "var(--on-dark)" }}>{placements.value.toLocaleString()}</div>
            {placements.target !== null ? (
              <>
                <div className="t-meta" style={{ color: "var(--on-dark-2)", marginTop: 6 }}>
                  {t("dash.ofTarget", { target: placements.target, percent: placements.percent ?? 0 })}
                </div>
                <div
                  className="track"
                  style={{ height: 8, marginTop: 10, background: "rgba(255,255,255,0.18)", position: "relative" }}
                >
                  <div
                    className="track__fill"
                    style={{
                      width: `${Math.min(100, placements.percent ?? 0)}%`,
                      background: "var(--gold-500)",
                    }}
                  />
                  {/* Elapsed time as a mark on the same track. Progress against a
                      quarterly target is meaningless without it: 3% on day three
                      is on track, and the same figure on day eighty is not. */}
                  <span
                    aria-hidden
                    style={{
                      position: "absolute",
                      insetBlock: -2,
                      insetInlineStart: `${Math.min(100, placements.quarter_elapsed_percent)}%`,
                      width: 2,
                      background: "var(--on-dark)",
                    }}
                  />
                </div>
                <div className="t-meta" style={{ color: "var(--on-dark-3)", marginTop: 6 }}>
                  {t("dash.quarterElapsed", { percent: placements.quarter_elapsed_percent })}
                </div>
              </>
            ) : (
              // §11: no quarterly target has been agreed, so the count stands
              // alone rather than being measured against a number we invented.
              <div className="t-meta" style={{ color: "var(--on-dark-3)", marginTop: 6 }}>
                {t("dash.noTarget")}
              </div>
            )}
          </>
        ) : (
          <div className="t-meta" style={{ color: "var(--on-dark-2)", marginTop: 8 }}>{placements.reason}</div>
        )}
      </Card>

      <Card>
        <CapsLabel>{t("dash.retained")}</CapsLabel>
        <div style={{ marginTop: 8 }}>
          {retained.available ? null : <NotYet reason={retained.reason} />}
        </div>
      </Card>

      <Card>
        <CapsLabel>{t("dash.genderSplit")}</CapsLabel>
        {gender.available ? (
          <GenderBar female={gender.female} male={gender.male} baseline={gender.registration_female} />
        ) : (
          <div className="t-meta" style={{ marginTop: 10 }}>
            {t("dash.noPlacementsYet")}
          </div>
        )}
      </Card>
    </div>
  );
}

/**
 * A single 34px stacked bar, per the handoff.
 *
 * Both labels sit inside their own segment in `--ink-900`. `--gold-500` is
 * documented as fill-only because it is 2.6:1 against paper — but that is the
 * ratio for gold *as* text. Ink on gold is 5.9:1, which clears AA, and it is
 * what the handoff's own dashboard mockup shows. Do not "fix" this to white.
 */
function GenderBar({ female, male, baseline }: { female: Rate; male: Rate; baseline: Rate }) {
  const { t } = useLang();

  // Below the reporting floor the split is not drawn at all. A 67/33 bar off
  // three placements invites exactly the parity conclusion three cases cannot
  // support, and a bar is more persuasive than the asterisk beside it.
  if (female.percent === null || male.percent === null) {
    return (
      <div className="t-meta" style={{ marginTop: 10 }}>
        {t("dash.splitTooFew", { n: female.d })}
      </div>
    );
  }

  const segments = splitSegments(female.percent, male.percent);

  return (
    <>
      <div
        style={{
          display: "flex",
          height: 34,
          marginTop: 10,
          borderRadius: "var(--r-group)",
          overflow: "hidden",
          fontSize: 13,
          fontWeight: 600,
        }}
      >
        <span
          style={{
            width: `${segments.female}%`,
            background: "var(--gold-500)",
            color: "var(--ink-900)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            // The label is dropped rather than allowed to overflow into the
            // neighbouring segment; the figure below still states both shares.
            overflow: "hidden",
            whiteSpace: "nowrap",
          }}
        >
          {segments.female >= 22 ? t("dash.women", { percent: segments.female }) : ""}
        </span>
        <span
          style={{
            width: `${segments.male}%`,
            background: "var(--green-700)",
            color: "var(--on-dark)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            whiteSpace: "nowrap",
          }}
        >
          {segments.male >= 22 ? t("dash.men", { percent: segments.male }) : ""}
        </span>
      </div>
      <div className="t-meta" style={{ marginTop: 8 }}>
        {t("dash.women", { percent: segments.female })} · {t("dash.men", { percent: segments.male })} ·{" "}
        {t("dash.ofCount", { n: female.n + male.n, d: female.d })}
        {female.band === "provisional" && "*"}
      </div>
      {baseline.percent !== null && (
        <div className="t-meta">{t("dash.registrationBaseline", { percent: baseline.percent })}</div>
      )}
      {female.band === "provisional" && <div className="t-meta">{t("dash.provisionalNote")}</div>}
    </>
  );
}
