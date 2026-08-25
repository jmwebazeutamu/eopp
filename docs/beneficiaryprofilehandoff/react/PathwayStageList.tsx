import { useState } from "react";
import type { PathwayStage, StageKey } from "./types";

interface Props {
  stages: PathwayStage[];
  completeCount: number;
  totalCount: number;
  /** stage opened on first render; defaults to the first incomplete one */
  defaultOpen?: StageKey;
}

/**
 * Replaces BOTH the old summary list at the top of the page and the four
 * repeated check cards at the bottom. One list, rows expand in place.
 *
 * Delete the old <StageSummary /> and the four <StageChecklistCard />
 * blocks when this lands — keeping either reintroduces the duplication.
 */
export function PathwayStageList({ stages, completeCount, totalCount, defaultOpen }: Props) {
  const firstIncomplete = stages.find((s) => !s.complete)?.key;
  const [open, setOpen] = useState<StageKey | null>(defaultOpen ?? firstIncomplete ?? null);

  const checkTotal = stages.reduce((n, s) => n + s.checks.length, 0);
  const checkPassed = stages.reduce((n, s) => n + s.checks.filter((c) => c.passed).length, 0);

  return (
    <section className="card" aria-labelledby="pathway-heading">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--s3)" }}>
        <div className="t-caps" id="pathway-heading">Pathway</div>
        <span className="chip" style={{ background: "var(--green-100)", borderColor: "var(--green-border)", color: "var(--green-ink)" }}>
          {completeCount} of {totalCount} stages
        </span>
      </div>

      <p style={{ margin: "4px 0 14px" }}>
        {summaryLine(stages)} {checkPassed === checkTotal
          ? `All ${checkTotal} checks pass.`
          : `${checkPassed} of ${checkTotal} checks pass.`}
      </p>

      <div className="progress" style={{ marginBottom: "var(--s4)" }} role="img"
           aria-label={`${completeCount} of ${totalCount} stages complete`}>
        <span className="progress__fill"
              data-complete={completeCount === totalCount}
              style={{ width: `${(completeCount / totalCount) * 100}%` }} />
      </div>

      <div className="stage-list">
        {stages.map((stage) => {
          const isOpen = open === stage.key;
          return (
            <div className="stage" key={stage.key}>
              <button
                type="button"
                className="stage__summary"
                aria-expanded={isOpen}
                aria-controls={`stage-detail-${stage.key}`}
                onClick={() => setOpen(isOpen ? null : stage.key)}
              >
                <span className={markClass(stage)} aria-hidden="true">
                  {stage.complete ? <TickIcon /> : null}
                </span>
                <span className="stage__label">{stage.label}</span>
                <span className="t-meta">{stage.summary}</span>
                <ChevronIcon open={isOpen} />
              </button>

              {isOpen && (
                <div className="stage__detail" id={`stage-detail-${stage.key}`}>
                  {stage.checks.map((check) => (
                    <div className="indicator-row" key={check.label}>
                      <span style={{ color: "var(--ink-600)" }}>{check.label}</span>
                      <span style={{ fontWeight: 600, color: check.passed ? "var(--green-ink)" : "var(--gold-700)" }}>
                        {check.value}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function markClass(stage: PathwayStage) {
  if (stage.complete) return "stage__mark";
  const anyPassed = stage.checks.some((c) => c.passed);
  return anyPassed ? "stage__mark stage__mark--blocked" : "stage__mark stage__mark--pending";
}

function summaryLine(stages: PathwayStage[]) {
  const done = stages.filter((s) => s.complete).map((s) => s.label.toLowerCase());
  if (done.length === stages.length) return "Registered, verified, in a group and linked.";
  if (done.length === 0) return "No stage complete yet.";
  return `${done.slice(0, -1).join(", ")} and ${done[done.length - 1]}.`;
}

function TickIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 12.5l5 5L20 6.5" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--ink-400)"
         strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={open ? "M18 15l-6-6-6 6" : "M6 9l6 6 6-6"} />
    </svg>
  );
}
