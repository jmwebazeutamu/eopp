import type { GateCondition, GateResult } from "../../api/types";

/**
 * The arithmetic and wording behind the readiness card, as a pure module.
 *
 * Same reason `timelineLayout.ts` and `dashboardLayout.ts` are pure: the part
 * worth testing is what the card *says*, not how a `<div>` draws. jsdom applies
 * no stylesheet, so a test asserting on the rendered card asserts on nothing —
 * but "a condition with no denominator reads 'not measurable yet' rather than
 * '0 (need 80)'" is a real claim, and it can be tested here.
 *
 * One rule runs through all of it, from the handoff's §8: **the actual value
 * always travels with the threshold**. "Attendance 74% (need 80%)" changes what
 * a facilitator does next week; a red dot does not.
 */

export type ConditionState = "met" | "unmet" | "unmeasurable";

export interface ConditionLine {
  code: string;
  label: string;
  state: ConditionState;
  /** What the group has now, formatted for reading. */
  actual: string;
  /** What it needs, formatted for reading. */
  threshold: string;
  /** The whole line, for a phone card where the two columns do not fit. */
  sentence: string;
}

function formatValue(value: GateCondition["actual"]): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return String(value);
  // Percentages arrive as decimal strings — "100.0", "74.5" — because a rate
  // that travelled as a float would round differently in two places.
  return value;
}

export function conditionState(condition: GateCondition): ConditionState {
  if (condition.met) return "met";
  return condition.unmeasurable ? "unmeasurable" : "unmet";
}

export function conditionLine(condition: GateCondition): ConditionLine {
  const state = conditionState(condition);
  const unit = condition.unit ?? "";
  // The unit rides on the value, not on the label: "74% (need 80%)" is the
  // handoff's own wording, and "74 (need 80)" invites reading a rate as a count.
  const withUnit = (value: string) => (value === "—" || !unit ? value : `${value}${unit}`);
  const actual = withUnit(formatValue(condition.actual));
  const threshold = withUnit(formatValue(condition.threshold));

  // "Not measurable yet" is not "below the threshold", and a facilitator does
  // something different about each: one means hold more meetings, the other
  // means the group has none to measure. Showing both as a red dash told her
  // the wrong thing.
  const sentence =
    state === "unmeasurable"
      ? `${condition.label}: not measurable yet (need ${threshold})`
      : `${condition.label}: ${actual} (need ${threshold})`;

  return { code: condition.code, label: condition.label, state, actual, threshold, sentence };
}

export interface ReadinessSummary {
  passed: boolean;
  met: number;
  total: number;
  lines: ConditionLine[];
  /** The conditions still in the way, worst first: unmet before unmeasurable. */
  outstanding: ConditionLine[];
}

export function summarise(gate: GateResult | null): ReadinessSummary | null {
  if (!gate) return null;

  const lines = gate.conditions.map(conditionLine);
  const met = lines.filter((line) => line.state === "met").length;

  // Unmet before unmeasurable: a condition the group is short on is something
  // it can act on this month, and one it cannot measure yet usually means
  // "keep meeting". The actionable ones belong at the top.
  const rank = { unmet: 0, unmeasurable: 1, met: 2 } as const;
  const outstanding = lines
    .filter((line) => line.state !== "met")
    .sort((left, right) => rank[left.state] - rank[right.state]);

  return { passed: gate.passed, met, total: lines.length, lines, outstanding };
}

/**
 * How stale the card is, in words.
 *
 * The readiness card has to work offline from the last sync, and a stale card
 * that is honest about its age beats a fresh one that is wrong. Rendered
 * whenever the data is not from today.
 */
export function freshness(computedAt: string, today: string): string | null {
  if (!computedAt) return null;
  const computed = computedAt.slice(0, 10);
  if (computed === today) return null;
  return `As at ${computed}`;
}
