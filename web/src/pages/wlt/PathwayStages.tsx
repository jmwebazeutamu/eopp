import { useState } from "react";

import type { JourneyStage, JourneyStageState } from "../../api/types";
import { CapsLabel } from "../../components/ui";
import { STAGE_TONE } from "../../design/wltStatus";
import { useLang } from "../../i18n/LanguageContext";

/**
 * The four stages, once.
 *
 * The page used to draw them twice: a summary sequence at the top and then a
 * full card per stage below it, so the ten gate conditions rendered in full,
 * twice, on one 2,000px column. A reader who spotted a failing check at the top
 * met the same check again two screens later with no way to know it was the
 * same one.
 *
 * One list now, rows expanding in place. The row itself is the disclosure
 * control — a `<button>` with `aria-expanded`, not a div with a click handler —
 * so it reaches the keyboard and announces its own state.
 *
 * **The first incomplete stage opens on load.** That is the one the screen was
 * built to answer, and it is the same choice `next_action` makes in the payload;
 * making the reader open it would put a click in front of the only thing most
 * visits are for. Everything done, nothing open.
 */
export default function PathwayStages({
  stages,
  done,
  total,
  nextAction,
  children,
}: {
  stages: JourneyStage[];
  done: number;
  total: number;
  /** The server's answer to "what is outstanding". Null when nothing is. */
  nextAction: JourneyStage | null;
  /** Per-stage actions — verify, add to a group — rendered inside the open row. */
  children?: (stage: JourneyStage) => React.ReactNode;
}) {
  const { t } = useLang();
  // `next_action` rather than the first non-done row: the server decides what
  // is outstanding, and it is the same value the payload leads with. Recomputing
  // it here would give the screen a second opinion that could disagree with the
  // one the API published.
  const [open, setOpen] = useState<string | null>(nextAction?.code ?? null);

  return (
    <section className="card" aria-labelledby="pathway-title">
      <div className="chip-row">
        <CapsLabel id="pathway-title">{t("wlt.pathwayTitle")}</CapsLabel>
        <span className="t-meta">{t("wlt.pathwayProgress", { done, total })}</span>
      </div>

      {/* The summary line the old page carried, kept: opening the first
          outstanding row says which stage is next only to somebody who reads
          the marks. This says it. */}
      <p className="t-meta pathway__lead">
        {nextAction ? t("wlt.journeyNext", { stage: nextAction.label }) : t("wlt.journeyComplete")}
      </p>

      <div
        className="progress"
        role="progressbar"
        aria-valuenow={done}
        aria-valuemin={0}
        aria-valuemax={total}
        aria-label={t("wlt.pathwayProgress", { done, total })}
      >
        <span
          className="progress__fill"
          data-complete={done === total ? "true" : undefined}
          style={{ width: `${total === 0 ? 0 : (done / total) * 100}%` }}
        />
      </div>

      <ol className="pathway" aria-label={t("wlt.journeySequence")}>
        {stages.map((stage) => {
          const tone = STAGE_TONE[stage.state];
          const expanded = open === stage.code;
          const met = stage.conditions.filter((condition) => condition.met).length;
          const panelId = `stage-${stage.code}`;
          return (
            <li key={stage.code} className="pathway__stage">
              <button
                type="button"
                className="pathway__row"
                aria-expanded={expanded}
                aria-controls={panelId}
                onClick={() => setOpen(expanded ? null : stage.code)}
              >
                <span
                  className="pathway__mark"
                  aria-hidden
                  style={{ color: tone.fg, background: tone.bg, borderColor: tone.bd }}
                >
                  {tone.mark}
                </span>
                <span className="pathway__label">{stage.label}</span>
                <span className="t-meta pathway__summary">
                  {stage.conditions.length > 0
                    ? t("wlt.checksComplete", { done: met, total: stage.conditions.length })
                    : t(STATE_LABEL[stage.state])}
                </span>
                <span className="pathway__chevron" aria-hidden data-open={expanded ? "true" : undefined}>
                  ›
                </span>
              </button>

              {expanded && (
                <div id={panelId} className="pathway__detail">
                  <ul className="indicator-cols">
                    {stage.conditions.map((condition) => {
                      const conditionTone = condition.met ? STAGE_TONE.done : STAGE_TONE.blocked;
                      return (
                        <li key={condition.code} className="indicator-row">
                          <span>
                            <span aria-hidden style={{ color: conditionTone.fg }}>
                              {conditionTone.mark}
                            </span>{" "}
                            {condition.label}
                          </span>
                          {/* What she has, then what she still needs — and the
                              threshold only where it is still wanted. Most
                              conditions here are yes/no, and "Yes (need Yes)"
                              says nothing while wrapping the rows that do need
                              reading at 360px. */}
                          <span style={{ whiteSpace: "nowrap" }}>
                            <strong style={{ color: conditionTone.fg }}>{condition.actual || "—"}</strong>
                            {!condition.met && <span className="t-meta"> (need {condition.threshold})</span>}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  {children?.(stage)}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

const STATE_LABEL = {
  done: "wlt.stateDone",
  ready: "wlt.stateReady",
  waiting: "wlt.stateWaiting",
  blocked: "wlt.stateBlocked",
} as const satisfies Record<JourneyStageState, string>;
