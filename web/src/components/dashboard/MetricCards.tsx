import type { CSSProperties } from "react";

import type { GenderSplit, ProgrammeDashboard } from "../../api/types";
import { useLang } from "../../i18n/LanguageContext";
import { CapsLabel, Card } from "../ui";
import { compositionSegments } from "./dashboardLayout";
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

/**
 * A segment narrower than this gets no label inside it.
 *
 * Was 18, which silently dropped the label from a 16% segment that measured
 * 50px — ample for "16%". The other two segments on that bar were labelled, so
 * the third read as an error rather than as a segment.
 */
const LABEL_INSIDE_MIN_PERCENT = 12;

export function MetricCards({ metrics }: { metrics: ProgrammeDashboard["metrics"] }) {
  const { t } = useLang();
  const placements = metrics.placements_this_quarter;
  const retained = metrics.retained_six_months;
  const gender = metrics.gender_split;

  return (
    <div className="grid-panels">
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
          <GenderBar split={gender} />
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
 * Every category the server returns gets a segment, and anything it did not
 * account for gets its own. The bar used to draw women from the API and derive
 * men as `100 - women`, which absorbed a fifth of the placements — every youth
 * whose sex is "Other" or unrecorded — into the male segment without trace.
 *
 * Labels sit inside their own segment in `--ink-900`. `--gold-500` is documented
 * as fill-only because it is 2.6:1 against paper; that is the ratio for gold
 * *as* text. Ink on gold is 5.9:1, which clears AA, and it is what the handoff's
 * own mockup shows. Do not "fix" this to white.
 */
const SEX_FILL: Record<string, string> = {
  FEMALE: "var(--gold-500)",
  MALE: "var(--green-700)",
  OTHER: "var(--green-500)",
  unaccounted: "var(--cancelled-bar)",
};

const SEX_INK: Record<string, string> = {
  FEMALE: "var(--ink-900)",
  MALE: "var(--on-dark)",
  OTHER: "var(--on-dark)",
  unaccounted: "var(--on-dark)",
};

function GenderBar({ split }: { split: GenderSplit }) {
  const { t } = useLang();

  // Below the reporting floor the split is not drawn at all: a bar off three
  // placements invites a parity conclusion three cases cannot support, and a
  // bar is more persuasive than the asterisk beside it.
  if (split.female.percent === null) {
    return (
      <div className="t-meta" style={{ marginTop: 10 }}>
        {t("dash.splitTooFew", { n: split.female.d })}
      </div>
    );
  }

  const segments = compositionSegments(
    [
      { key: "FEMALE", label: t("dash.womenLabel"), n: split.female.n },
      { key: "MALE", label: t("dash.menLabel"), n: split.male.n },
      { key: "OTHER", label: t("dash.otherLabel"), n: split.other?.n ?? 0 },
    ],
    split.placed_total,
  );

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
        {segments.map((segment) => (
          <span
            key={segment.key}
            title={`${segment.label}: ${segment.n}`}
            style={{
              width: `${segment.percent}%`,
              background: SEX_FILL[segment.key] ?? "var(--fill-muted-2)",
              color: SEX_INK[segment.key] ?? "var(--ink-900)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
              whiteSpace: "nowrap",
            }}
          >
            {segment.percent >= LABEL_INSIDE_MIN_PERCENT ? `${segment.percent}%` : ""}
          </span>
        ))}
      </div>

      {/* Every segment named with its own count, so nothing rests on the bar. */}
      <div className="t-meta" style={{ marginTop: 8 }}>
        {segments.map((segment) => `${segment.label} ${segment.percent}% (${segment.n})`).join(" · ")}
      </div>
      <div className="t-meta">{t("dash.splitBase", { n: split.placed_total })}</div>
      {split.registration_female.percent !== null && (
        <div className="t-meta">
          {t("dash.registrationBaseline", { percent: split.registration_female.percent })}
        </div>
      )}
      {split.female.band === "provisional" && <div className="t-meta">{t("dash.provisionalNote")}</div>}
    </>
  );
}
