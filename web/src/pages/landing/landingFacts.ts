/**
 * The landing page's numbers, and where each one comes from.
 *
 * Kept apart from the component for the reason `timelineLayout.ts` is: this is
 * the part worth unit testing, and it is the part a reviewer has to check
 * against `wlt_module_handoff/DEFINITIONS.md` §2.
 *
 * **Nothing here invents a figure.** Every value arrives from
 * `GET /wlt/public-parameters/`, which resolves it from `wlt.PolicyParameter`.
 * The build prompt's rule 2 and the WLT UI handoff's rule 6 say the same thing:
 * a threshold typed into a template is a threshold that will contradict the
 * application the first time the programme moves it. Several of these are
 * marked NEEDS FSCO in the seed and two are disputed in the source handbook,
 * so "the first time" is not hypothetical.
 *
 * A parameter that has not arrived yet renders as an em dash, never as a zero
 * — the platform's standing rule that absent is not the same as none.
 */

import type { Translate } from "../../i18n/LanguageContext";
import type { StringKey } from "../../i18n/strings";

export type Parameters = Record<string, number | string | boolean | null>;

/** An em dash, so a missing parameter reads as unknown rather than as zero. */
export const ABSENT = "—";

function num(parameters: Parameters, key: string): string {
  const value = parameters[key];
  return typeof value === "number" ? String(value) : ABSENT;
}

/** `15–25`, from the two ends of the group-size rule. En dash, not a hyphen. */
export function groupSizeRange(parameters: Parameters): string {
  const min = num(parameters, "group.size.hard_min");
  const max = num(parameters, "group.size.hard_max");
  if (min === ABSENT || max === ABSENT) return ABSENT;
  return `${min}–${max}`;
}

export interface Stat {
  key: string;
  value: string;
  labelKey: StringKey;
}

/**
 * The four figures in the strip under the hero.
 *
 * The fourth is **not** the mock's "33 linkage steps". That number appears
 * nowhere in the linkage workflows document: only W1 carries a numbered step
 * table, of eight rows, and W2 to W8 are prose. Rule 2 forbids shipping a
 * figure that cannot be traced, so it is replaced by one that can be — the
 * twelve states of `wlt.LinkageStatus`, which is the gated lifecycle the
 * sentence was reaching for.
 */
export function statStrip(parameters: Parameters, linkageStates: number): Stat[] {
  return [
    { key: "groupSize", value: groupSizeRange(parameters), labelKey: "landing.statGroupSize" },
    { key: "cla", value: num(parameters, "gate.cla.min_groups"), labelKey: "landing.statCla" },
    { key: "federation", value: num(parameters, "gate.federation.min_clas"), labelKey: "landing.statFederation" },
    { key: "linkage", value: String(linkageStates), labelKey: "landing.statLinkage" },
  ];
}

export interface Condition {
  /** Rendered text, already carrying its threshold. */
  text: string;
  /**
   * `stop` and `warn` colour a pill. The design system never uses colour alone,
   * so a tone only ever reinforces wording that already says the same thing.
   */
  tone?: "stop" | "warn";
}

export interface PhaseStep {
  key: string;
  titleKey: StringKey;
  bodyKey: StringKey;
  conditions: Condition[];
}

/**
 * The five steps of the phase rail, with the **complete** gate condition set.
 *
 * The mock abridges each list — Phase 1 drops savings compliance, Phase 2 drops
 * the social fund and the 52-week minimum, and both structural gates drop their
 * constitution. Its own section heading promises "the conditions below ... when
 * they are all met", so an abridged list read as a complete one. The build
 * prompt settles it: where the mock and a spec disagree, the spec wins and the
 * mock is the bug.
 *
 * `t` is passed in rather than imported so this module stays pure and its test
 * can assert on keys and thresholds rather than on English.
 */
export function phaseRail(parameters: Parameters, t: Translate): PhaseStep[] {
  const size = groupSizeRange(parameters);
  return [
    {
      key: "forming",
      titleKey: "landing.phaseFormingTitle",
      bodyKey: "landing.phaseFormingBody",
      conditions: [
        { text: t("landing.condRoster", { range: size }) },
        { text: t("landing.condCommittee") },
        { text: t("landing.condBylaws") },
        { text: t("landing.condBalancedTill") },
      ],
    },
    {
      key: "p1",
      titleKey: "landing.phaseOneTitle",
      bodyKey: "landing.phaseOneBody",
      conditions: [
        { text: t("landing.condAdherence", { pct: num(parameters, "gate.p1.meeting_adherence_pct") }) },
        { text: t("landing.condAttendance", { pct: num(parameters, "gate.p1.attendance_pct") }) },
        { text: t("landing.condSavings", { pct: num(parameters, "gate.p1.savings_compliance_pct") }) },
        { text: t("landing.condMeetings", { n: num(parameters, "gate.p1.min_savings_meetings") }) },
        { text: t("landing.condPar30", { pct: num(parameters, "gate.p1.max_par30_pct") }), tone: "stop" },
      ],
    },
    {
      key: "p2",
      titleKey: "landing.phaseTwoTitle",
      bodyKey: "landing.phaseTwoBody",
      conditions: [
        { text: t("landing.condFund", { weeks: num(parameters, "gate.p2.fund_adequacy_weeks") }) },
        { text: t("landing.condCycles", { n: num(parameters, "gate.p2.completed_loan_cycles") }) },
        { text: t("landing.condSocialFund") },
        { text: t("landing.condSincePhaseOne", { weeks: num(parameters, "gate.p2.min_weeks_since_p1") }) },
        { text: t("landing.condPar30", { pct: num(parameters, "gate.p2.max_par30_pct") }), tone: "stop" },
      ],
    },
    {
      key: "cla",
      titleKey: "landing.phaseThreeTitle",
      bodyKey: "landing.phaseThreeBody",
      conditions: [
        { text: t("landing.condEligibleGroups", { n: num(parameters, "gate.cla.min_groups") }) },
        { text: t("landing.condDelegates", { n: num(parameters, "gate.cla.delegates_per_group") }) },
        { text: t("landing.condClaConstitution") },
        { text: t("landing.condWoredaApproval"), tone: "warn" },
      ],
    },
    {
      key: "federation",
      titleKey: "landing.phaseFourTitle",
      bodyKey: "landing.phaseFourBody",
      conditions: [
        { text: t("landing.condMinClas", { n: num(parameters, "gate.federation.min_clas") }) },
        { text: t("landing.condClaMonths", { n: num(parameters, "gate.federation.min_cla_months") }) },
        { text: t("landing.condFederationConstitution") },
        { text: t("landing.condWoredaApproval"), tone: "warn" },
      ],
    },
  ];
}
