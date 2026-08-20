/**
 * Types mirroring the DRF serializers.
 *
 * Kept hand-written for now. Generating them from /api/schema/ (drf-spectacular
 * publishes OpenAPI 3.1) is worth doing once the referral entity lands in
 * Sprint 3 and the surface stops moving.
 */

export type Role =
  | "OUTREACH_WORKER"
  | "CASE_MANAGER"
  | "TRAINER"
  | "EMPLOYER_LIAISON"
  | "ENTERPRISE_OFFICER"
  | "PARTNER_STAFF"
  | "SUPERVISOR"
  | "PROGRAMME_MANAGER"
  | "MNE_STAFF"
  | "SYSTEM_ADMIN"
  // WLT group module (PSNP 6 Women's Livelihoods Transformation). A separate
  // programme with a separate subject, so it carries its own roles rather than
  // overloading the supervisor's — see apps/wlt and docs/wlt_module_handoff/.
  | "WLT_FACILITATOR"
  | "WLT_WOREDA_OFFICER"
  | "WLT_REGION_OFFICER"
  | "WLT_FEDERAL_OFFICER";

export type CaseStatus = "ACTIVE" | "STALLED" | "REFERRAL_PENDING" | "PLACED" | "EXITED";

/** The §7 access row the API resolves for the current user. */
export interface AccessMatrix {
  case_scope: string;
  case_write: boolean;
  referral_scope: string;
  referral_write: boolean;
  /** WLT group visibility. "NONE" for every youth-side role. */
  group_scope: string;
  group_write: boolean;
  /**
   * May this account record what a service delivered — a training enrolment, a
   * placement, a retention check. Deliberately not `case_write`: §7 gives an
   * employer liaison no case write and she is the person who makes the calls.
   */
  delivery_write: boolean;
}

export interface CurrentUser {
  id: string;
  username: string;
  work_email: string;
  personal_email: string;
  work_phone: string;
  personal_phone: string;
  full_name: string;
  role: Role;
  role_display: string;
  woreda_assignment: string[];
  partner: string | null;
  partner_name: string | null;
  account_status: string;
  access: AccessMatrix;
  /**
   * Woredas this account may narrow a screen to — its own assignment, or every
   * programme woreda for an ALL scope. `woreda_assignment` cannot serve the
   * purpose: an ALL-scope account carries an empty one.
   */
  scopable_woredas: string[];
}

export interface YouthSummary {
  id: string;
  full_name: string;
  sex: string;
  date_of_birth: string;
  age: number;
  phone_number: string;
  woreda: string;
  kebele: string;
}

export interface CaseListRow {
  id: string;
  youth: YouthSummary;
  case_status: CaseStatus;
  case_status_display: string;
  case_manager: string;
  case_manager_name: string;
  woreda: string;
  opened_date: string;
  last_activity_date: string;
  days_since_activity: number;
  is_stalled_by_threshold: boolean;
  next_action: string;
}

export interface CaseDetail extends Omit<CaseListRow, "youth"> {
  youth: string;
  youth_detail: YouthSummary;
  closed_date: string | null;
  exit_reason: string;
  is_open: boolean;
  next_action_owner: string | null;
  next_action_owner_name: string | null;
  recent_actions: CaseAction[];
  /** Resolved server-side: the one assignment with is_current (spec §4.4). */
  current_pathway: PathwayAssignment | null;
  /** The most recent profiling record — §3's "latest record is current". */
  current_profiling: ProfilingRecord | null;
  created_at: string;
  updated_at: string;
}

export type CaseActionType = "NEXT_ACTION" | "FEEDBACK" | "FOLLOW_UP" | "STATUS_NOTE";
export type CaseActionStatus = "OPEN" | "DONE" | "SUPERSEDED";

export interface CaseAction {
  id: string;
  case: string;
  action_type: CaseActionType;
  action_type_display: string;
  body: string;
  created_by: string | null;
  created_by_name: string | null;
  assigned_to: string | null;
  assigned_to_name: string | null;
  status: CaseActionStatus;
  status_display: string;
  due_date: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Location {
  code: string;
  name: string;
  level: "REGION" | "ZONE" | "WOREDA" | "KEBELE";
  level_display: string;
  parent: string | null;
  parent_name: string | null;
  full_path: string;
  is_active: boolean;
}

export type Pathway = "WAGE_EMPLOYMENT" | "SELF_EMPLOYMENT" | "APPRENTICESHIP" | "TRAINING";

export type PartnerTypeCode =
  | "TVET_INSTITUTION"
  | "EMPLOYER"
  | "ENTERPRISE_DEVELOPMENT_AGENCY"
  | "SAVINGS_GROUP"
  | "HEALTH_SERVICE"
  | "PSYCHOSOCIAL_SERVICE"
  | "LEGAL_AID"
  | "FINANCE_INSTITUTION"
  | "OTHER";

export type MouStatus = "NONE" | "DRAFT" | "SIGNED" | "EXPIRED" | "TERMINATED";

export interface Partner {
  id: string;
  partner_name: string;
  partner_type: PartnerTypeCode;
  partner_type_display: string;
  woreda_coverage: string[];
  contact_name: string;
  phone: string;
  email: string;
  active_status: boolean;
  can_receive_referrals: boolean;
  mou_status: MouStatus;
  mou_status_display: string;
  mou_date: string | null;
  performance_notes: string;
}

export interface ProfilingRecord {
  id: string;
  case: string;
  work_history_summary: string;
  skills_list: string[];
  vulnerability_index_score: string | null;
  eligibility_flags: Pathway[];
  eligibility_flags_display: string[];
  priority_flag: boolean;
  assessed_date: string;
  assessor: string;
  assessor_name: string;
}

export interface PathwayAssignment {
  id: string;
  case: string;
  assessed_interests: string;
  capacities: string;
  barriers: string;
  selected_pathway: Pathway;
  selected_pathway_display: string;
  assessment_date: string;
  assessor: string;
  assessor_name: string;
  is_current: boolean;
  superseded_by: string | null;
  revision_reason: string;
}

export interface ManagedUser {
  id: string;
  username: string;
  work_email: string;
  personal_email: string;
  work_phone: string;
  personal_phone: string;
  full_name: string;
  role: Role;
  role_display: string;
  woreda_assignment: string[];
  partner: string | null;
  partner_name: string | null;
  account_status: "ACTIVE" | "SUSPENDED" | "INACTIVE";
  /** Open cases this account manages — annotated by the viewset. */
  caseload_count: number;
  last_login: string | null;
  date_joined: string;
}

export const PATHWAY_OPTIONS: { value: Pathway; label: string }[] = [
  { value: "WAGE_EMPLOYMENT", label: "Wage Employment" },
  { value: "SELF_EMPLOYMENT", label: "Self-Employment" },
  { value: "APPRENTICESHIP", label: "Apprenticeship" },
  { value: "TRAINING", label: "Training" },
];

/** Spec §7's ten roles, in the order the spec lists them. */
export const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "OUTREACH_WORKER", label: "Outreach worker / community facilitator" },
  { value: "CASE_MANAGER", label: "Youth case manager" },
  { value: "TRAINER", label: "Trainer / training officer" },
  { value: "EMPLOYER_LIAISON", label: "Employer liaison staff" },
  { value: "ENTERPRISE_OFFICER", label: "Enterprise development officer" },
  { value: "PARTNER_STAFF", label: "Referral partner staff" },
  { value: "SUPERVISOR", label: "Woreda / programme supervisor" },
  { value: "PROGRAMME_MANAGER", label: "Programme manager" },
  { value: "MNE_STAFF", label: "M&E staff" },
  { value: "SYSTEM_ADMIN", label: "System administrator" },
];

/** Roles that ScopedQuerySetMixin resolves through woreda_assignment. */
export const WOREDA_SCOPED_ROLES: Role[] = ["OUTREACH_WORKER", "CASE_MANAGER", "SUPERVISOR"];

// --- Sprint 3: referral engine (spec §4.6, §5, §6) -------------------------
export type ReferralStatusCode =
  | "PENDING_CONFIRMATION"
  | "ACTIVE"
  | "COMPLETED"
  | "FAILED"
  | "REPLACED"
  | "CANCELLED";

export type ReferralTriggerCode = "MANUAL" | "ONWARD" | "REPLACEMENT";

/** Taxonomy terms are configuration, not code — served from lookup tables (§9). */
export interface TaxonomyTerm {
  code: string;
  label: string;
  description: string;
  requires_note: boolean;
  is_active: boolean;
}

export interface ReferralCategoryTerm extends TaxonomyTerm {
  exempt_from_parallel_cap: boolean;
}

export interface OutcomeTypeTerm extends TaxonomyTerm {
  /** Empty means the outcome applies to any category (§5.3's "Other"). */
  applies_to: string[];
}

export interface Referral {
  id: string;
  case: string;
  youth_name: string;
  /** Denormalised from the case (§4.2) — the queue lists referrals case-less. */
  woreda: string;
  referral_category: string;
  referral_category_label: string;
  referral_trigger: ReferralTriggerCode;
  trigger_display: string;
  is_parallel: boolean;
  parallel_group_id: string | null;
  counts_toward_parallel_cap: boolean;
  parent_referral: string | null;
  replacement_referral: string | null;
  receiving_partner: string;
  receiving_partner_detail: {
    id: string;
    partner_name: string;
    partner_type_display: string;
  };
  receiving_contact_name: string;
  initiated_date: string;
  initiated_by: string;
  initiated_by_name: string;
  confirmation_status: string;
  confirmation_status_display: string;
  confirmed_date: string | null;
  confirmed_by: string;
  status: ReferralStatusCode;
  status_display: string;
  allowed_transitions: string[];
  outcome_type: string | null;
  outcome_type_label: string | null;
  outcome_date: string | null;
  outcome_verification_method: string;
  /**
   * OQ-2. Anything but self-reported counts as externally verified, which is
   * what §8.3 reports. Moved only by a follow-up that reached the youth.
   */
  verification_source: string;
  failure_reason_code: string | null;
  failure_reason_label: string | null;
  failure_date: string | null;
  notes: string;
  created_at: string;
  /** The timeline closes a Cancelled bar here — §6.2 stamps no date for it. */
  updated_at: string;
}

/** A node of the §6.4 stack: a referral plus the referrals that followed it. */
export interface ReferralStackNode {
  referral: Referral;
  children: ReferralStackNode[];
}

export interface ReferralPrompts {
  onward: Referral[];
  replacement: Referral[];
}

export const REFERRAL_STATUS_COLOURS: Record<ReferralStatusCode, string> = {
  PENDING_CONFIRMATION: "gold",
  ACTIVE: "blue",
  COMPLETED: "green",
  FAILED: "red",
  REPLACED: "purple",
  CANCELLED: "default",
};

// --- Sprint 4: alerts (spec §4.13) -----------------------------------------

export type AlertTypeCode =
  | "STALL"
  | "REFERRAL_CONFIRMATION_OVERDUE"
  | "FOLLOW_UP_DUE"
  | "ONWARD_REFERRAL_PROMPT"
  | "REPLACEMENT_REFERRAL_PROMPT"
  | "RETENTION_CHECK_DUE";

export type AlertStatusCode = "OPEN" | "ACTIONED" | "DISMISSED";

export interface Alert {
  id: string;
  case: string;
  youth_name: string;
  woreda: string;
  referral: string | null;
  alert_type: AlertTypeCode;
  alert_type_display: string;
  summary: string;
  triggered_date: string;
  threshold_days: number;
  age_days: number;
  assigned_to: string;
  assigned_to_name: string;
  status: AlertStatusCode;
  status_display: string;
  actioned_date: string | null;
  actioned_by: string | null;
  actioned_by_name: string | null;
}

export interface AlertSummary {
  open_total: number;
  assigned_to_me: number;
  by_type: { alert_type: AlertTypeCode; label: string; count: number }[];
}

/**
 * Alert types whose detection job arrives with its source entity: Follow-Up
 * (§4.9, Sprint 6) and Placement retention checks (§4.7, Sprint 5). Listed so
 * the summary view can label them as not-yet-generated rather than showing a
 * bare zero that reads as "none outstanding".
 */
export const ALERT_TYPES_PENDING_ENTITIES: AlertTypeCode[] = ["FOLLOW_UP_DUE", "RETENTION_CHECK_DUE"];

// --- Full youth record (spec §4.1) -----------------------------------------

export interface Youth extends YouthSummary {
  national_or_kebele_id: string;
  region: string;
  zone: string;
  household_id: string;
  psnp_status: string;
  education_level: string;
  disability_status: string;
  consent_given: boolean;
  consent_date: string | null;
  registration_date: string;
  registering_worker: string;
  registering_worker_name: string;
  is_age_eligible: boolean;
  /** Annotated by the viewset — drives the registry's open-case pill. */
  has_open_case: boolean;
  /** The case that pill opens; null when there is no open one. */
  open_case_id: string | null;
  sex_display?: string;
  /** Present only on the create response — §11's age band is unconfirmed, so
   *  an out-of-band registration warns rather than blocks. */
  age_band_warning?: string | null;
}

/**
 * One row of a spreadsheet import, as `POST /youth/import/` reports it.
 *
 * `row` is the sheet row number, not an index — the user reads it next to Excel.
 */
export interface YouthImportRow {
  row: number;
  status: "new" | "duplicate" | "error";
  full_name: string;
  /** DRF field errors, keyed by the Youth field the column fills. */
  errors: Record<string, string[]>;
  /** The §11 age-band warning, present only on rows actually written. */
  warning: string;
  /** Id of the youth this row already exists as; null for a repeat within the file. */
  duplicate_of: string | null;
}

export interface YouthImportReport {
  /** False for a preview, and false for a commit refused because a row failed. */
  committed: boolean;
  counts: { total: number; new: number; duplicate: number; error: number };
  rows: YouthImportRow[];
}

// ---------------------------------------------------------------------------
// Programme dashboard — GET /dashboard/
// ---------------------------------------------------------------------------

/**
 * A figure whose source entity exists yet, or does not.
 *
 * Retention needs Placement (§4.7, Sprint 5), so the API reports it absent with
 * a reason rather than as a zero. The discriminated union makes the screen state
 * that case explicitly — there is no way to read `.value` off an absent figure.
 */
export type Maybe<T> = ({ available: true } & T) | { available: false; reason: string };

/** How much weight a figure's denominator can carry. See apps/dashboard/rules.py. */
export type Band = "report" | "provisional" | "suppressed";

/**
 * A percentage that arrives with the counts it came from.
 *
 * There is deliberately no shape in this file carrying a bare percentage: a rate
 * without its denominator is the thing the reporting rules exist to prevent.
 * `percent` is null when the band suppresses it, which the screen must render as
 * "too few to assess" and never as 0%.
 */
export interface Rate {
  percent: number | null;
  n: number;
  d: number;
  band: Band;
  note: string;
}

/** An average, banded the same way — a mean over four cases is as unstable as a rate over four. */
export interface MeanDays {
  days: number | null;
  n: number;
  band: Band;
  note: string;
}

export interface PlacementMetric {
  value: number;
  /** Null when no quarterly target has been agreed (spec §11). */
  target: number | null;
  percent: number | null;
  /** How far through the quarter we are — the target percent is read against this. */
  quarter_elapsed_percent: number;
}

export interface GenderSplit {
  placed_total: number;
  female: Rate;
  male: Rate;
  /** Rendered as its own segment. Never folded into "men" by subtraction. */
  other?: Rate;
  /** The baseline a placement split only means something against. */
  registration_female: Rate;
}

export interface FunnelStage {
  key: string;
  label: string;
  /** What the count counts — youth here, referrals on the partner cards. */
  unit: string;
  /** A stage a youth must pass to reach the next. False for coverage measures. */
  gating: boolean;
  /** The one-line definition of the stage, under its name. */
  sublabel: string;
  count: number | null;
  /** Null for a stage whose source entity does not exist yet. */
  share: Rate | null;
  /**
   * Median days spent in the stage above this one — the most actionable number
   * on the card, and the reason this is a row chart rather than a funnel: no
   * funnel chart can show it.
   */
  median_days_in_prev_stage: number | null;
  /** What was lost leaving this stage. Null on the last drawable row. */
  lost: {
    count: number;
    share: Rate;
    /** The transition this loss describes — the duration below belongs to it. */
    to_stage: string;
    to_label: string;
    median_days: number | null;
  } | null;
  available: boolean;
  reason: string;
}

/**
 * One partner's confirmation lag, exactly as `/dashboard/programme/` and
 * `/dashboard/woreda/` both return it — they share one server-side helper.
 *
 * This used to be `{ partner, lag: MeanDays }` and the server stopped sending
 * that shape without the type being updated, so `row.lag.days` threw and the
 * Programme page rendered blank. The hand-written fixture matched the stale
 * type rather than the API, which is why nothing caught it.
 */
export interface PartnerLag {
  partner: string;
  /** Median over the partner's own answers. Null when the band withholds it. */
  median_days: number | null;
  /** Confirmations the partner entered themselves — what the median is over. */
  n: number;
  /** Confirmations staff recorded on their behalf. Not responsiveness. */
  staff_recorded: number;
  band: Band;
}

export interface WoredaRow {
  woreda: string;
  registered: number;
  placed: number;
  rate: Rate;
}

export interface ProgrammeDashboard {
  period: { label: string; start: string; end: string };
  /** What the reader should understand these numbers to cover, per §7 scope. */
  scope_label: string;
  metrics: {
    placements_this_quarter: Maybe<PlacementMetric>;
    retained_six_months: Maybe<Record<string, never>>;
    gender_split: Maybe<GenderSplit>;
  };
  funnel: FunnelStage[];
  confirmation_lag: { standard_days: number; partners: PartnerLag[] };
  woredas: WoredaRow[];
  alerts: { open_total: number; by_type: { type: string; count: number }[]; stalled_cases: number };
}

/** Name and woredas only — what an assignment picker needs (§7). */
export interface AssignableUser {
  id: string;
  full_name: string;
  woreda_assignment: string[];
}

export const CASE_STATUS_OPTIONS: { value: CaseStatus; label: string }[] = [
  { value: "ACTIVE", label: "Active" },
  { value: "STALLED", label: "Stalled" },
  { value: "REFERRAL_PENDING", label: "Referral Pending" },
  { value: "PLACED", label: "Placed" },
  { value: "EXITED", label: "Exited" },
];

export const PARTNER_TYPE_OPTIONS: { value: PartnerTypeCode; label: string }[] = [
  { value: "TVET_INSTITUTION", label: "TVET Institution" },
  { value: "EMPLOYER", label: "Employer" },
  { value: "ENTERPRISE_DEVELOPMENT_AGENCY", label: "Enterprise Development Agency" },
  { value: "SAVINGS_GROUP", label: "Savings Group" },
  { value: "HEALTH_SERVICE", label: "Health Service" },
  { value: "PSYCHOSOCIAL_SERVICE", label: "Psychosocial Service" },
  { value: "LEGAL_AID", label: "Legal Aid" },
  { value: "FINANCE_INSTITUTION", label: "Finance Institution" },
  { value: "OTHER", label: "Other" },
];

export const MOU_STATUS_OPTIONS: { value: MouStatus; label: string }[] = [
  { value: "NONE", label: "No MOU" },
  { value: "DRAFT", label: "Draft" },
  { value: "SIGNED", label: "Signed" },
  { value: "EXPIRED", label: "Expired" },
  { value: "TERMINATED", label: "Terminated" },
];

/** Spec §4.12 account states. Deactivation replaces deletion throughout. */
export const ACCOUNT_STATUS_OPTIONS = [
  { value: "ACTIVE", label: "Active" },
  { value: "SUSPENDED", label: "Suspended" },
  { value: "INACTIVE", label: "Inactive" },
];

/** Programme rules the UI must state rather than assume — served by /referrals/rules/. */
export interface ProgrammeRules {
  parallel_limit: number;
  stall_alert_threshold_days: number;
  referral_confirmation_overdue_days: number;
  complementary_service_exempt: boolean;
}

/** A counter on a screen's mini dashboard: a count that is also its own filter. */
export interface SummaryCounter {
  /** The query parameter clicking this counter sets. */
  param: string;
  value: string;
  label: string;
  count: number;
}

export interface Summary {
  total: number;
  counters: SummaryCounter[];
}

// ---------------------------------------------------------------------------
// The four dashboard tiers — dashboard_handoff_youth_employment/README.md §1
// ---------------------------------------------------------------------------

/** A card whose source entity does not exist yet. Never rendered as a zero. */
export type Maybe2<T> = ({ available: true } & T) | { available: false; reason: string };

export interface MyWorkAlert {
  id: string;
  case: string;
  youth_name: string;
  reason: string;
  days_overdue: number;
}

export interface MyWorkReferral {
  id: string;
  case: string;
  youth_name: string;
  partner: string;
  days_waiting: number;
}

export interface MyWork {
  needs_action: MyWorkAlert[];
  needs_action_count: number;
  awaiting_partner: MyWorkReferral[];
  awaiting_partner_count: number;
  /** How many of those waits are past the configured threshold. */
  awaiting_over_threshold: number;
  /** Open alerts on cases in scope, whoever they are assigned to. */
  open_alerts_in_scope: number;
  /** Drives the badge and the footnote — never hardcode 7. */
  confirmation_threshold: number;
  active: { referrals: number; youth: number };
  woredas: string[];
  generated_at: string;
  at_risk: { case: string; youth_name: string; reason: string; badge: string }[];
  at_risk_count: number;
  uninstrumented_risk: string[];
  caseload_by_status: { status: string; label: string; n: number; oldest_days: number; slug: string }[];
  week: { opened: number; closed: number };
  /** Verified is a subset of recorded. Showing one without the other overstated it. */
  outcomes_verified: { verified: number; recorded: number };
}

export interface TeamRow {
  case_manager: string | null;
  name: string;
  total: number;
  segments: Record<string, number>;
  overdue: number;
  /** Above CASELOAD_CEILING — the parameter that was configured and unread. */
  over_ceiling: boolean;
}

export interface CompletenessRow {
  field: string;
  missing: number;
  of: number;
  /** False when the denominator is zero: "no records to check", not "complete". */
  has_records: boolean;
  cost: string;
}

export interface PartnerResponse {
  partner: string;
  /** Median over the partner's own answers only. */
  median_days: number | null;
  /** Confirmations the partner entered themselves. */
  n: number;
  /** Confirmations staff recorded on the partner's behalf — not responsiveness. */
  staff_recorded: number;
  band: Band;
}

export interface WoredaDashboard {
  scope_label: string;
  as_of: string;
  confirmation_threshold: number;
  awaiting_partner_alerts: number;
  tiles: {
    open_cases: number;
    registered_without_case: number;
    overdue_actions: number;
    median_days_to_confirm: number | null;
    outcomes_verified: number;
    outcomes_recorded: number;
    over_ceiling: number;
    caseload_ceiling: number;
  };
  team_caseload: TeamRow[];
  segments: { key: string; label: string }[];
  unassigned_youth: { available: false; reason: string };
  registered_without_case: number;
  partner_response: PartnerResponse[];
  data_completeness: CompletenessRow[];
}

export type Verdict = "above" | "below" | "as_expected" | "too_few";

export interface PartnerPerformanceRow {
  partner: string;
  partner_type: string;
  closed: number;
  completed: number;
  rate: Rate;
  ci: { lower: number; upper: number } | null;
  verdict: Verdict;
  verdict_label: string;
}

export interface OutcomeMatrix {
  categories: { code: string; label: string }[];
  outcomes: { code: string; label: string }[];
  cells: { category: string; outcome: string; n_referrals: number; n_youth: number }[];
  not_recorded: number;
  /** "category:outcome" pairs §5.3 permits. A forbidden cell is not an empty one. */
  permitted: string[];
  /** False when the taxonomy admits one outcome per category, so no crossover can appear. */
  crossovers_possible: boolean;
  /** Share of completed referrals recorded as "Other". */
  other: Rate;
}

/** Tier 3 = the programme dashboard plus the analytical cards. */
export interface ProgrammeTier extends ProgrammeDashboard {
  as_of: string;
  outcome_matrix: OutcomeMatrix;
  partner_performance: { overall_rate: Rate; partners: PartnerPerformanceRow[] };
  parallel_load: { cases_with_parallel: number; breaches_cap: number; cases_total: number };
  data_completeness: CompletenessRow[];
  cohort_retention: { available: false; reason: string };
  disposition_90_day: { available: false; reason: string };
}

export interface Indicator {
  code: string;
  label: string;
  framework: string;
  kind: "count" | "rate";
  value: number | null;
  /** The primary figure. For loop closure this is the *verified* rate. */
  rate: Rate | null;
  /** Every outcome, verified or not. Shown beside the primary, never instead of it. */
  recorded?: Rate | null;
  unit?: string;
  available: boolean;
  reason: string;
}

export interface DisaggregationCut {
  label: string;
  rows: { value: string; registered: number; placed: number; rate: Rate }[];
}

export interface DonorDashboard {
  scope_label: string;
  indicators: Indicator[];
  cumulative: {
    series: { month: string; placed: number; cumulative: number; unit: string }[];
    /** Placements older than the window, carried in rather than dropped. */
    opening_balance: number;
    unit: string;
  };
  disaggregation: DisaggregationCut[];
  retention: { available: false; reason: string };
  caveats: string[];
  as_of: string;
}

// ---------------------------------------------------------------------------
// WLT group module
// ---------------------------------------------------------------------------

export type WltGroupStatus =
  "DRAFT" | "CONSTITUTED" | "ACTIVE" | "AT_RISK" | "DORMANT" | "SPLIT" | "MERGED" | "DISSOLVED" | "ABANDONED";

export type WltPhase = "P1" | "P2" | "P3" | "P4" | "";

export type LinkageStatus =
  | "PROPOSED"
  | "SCREENED"
  | "BLOCKED"
  | "PENDING_APPROVAL"
  | "RETURNED"
  | "APPROVED"
  | "REJECTED"
  | "LAPSED"
  | "ACTIVE"
  | "DISTRESSED"
  | "DEFAULTED"
  | "CLOSED";

export interface WltGroup {
  id: string;
  name: string;
  kebele: string;
  kebele_name: string;
  facilitator: string;
  facilitator_name: string;
  status: WltGroupStatus;
  status_display: string;
  current_phase: WltPhase;
  phase_display: string;
  drafted_on: string;
  constituted_on: string | null;
  activated_on: string | null;
  phase_entered_on: string | null;
  members_current: number;
}

/** Why a woman left a group — `wlt.ExitReason`. */
export type WltExitReason =
  "MOVED" | "MARRIED_OUT" | "DIED" | "WITHDREW" | "EXPELLED" | "PSNP_EXIT" | "GROUP_SPLIT" | "";

/**
 * One membership: a dated range, never a flag.
 *
 * `exited_on === null` is the only definition of "current" — there is no
 * `is_active` here for the same reason there is none on the model. Every
 * indicator computes against the roster as it stood on a given date, and a
 * boolean drifts from the dates within a month.
 */
export interface WltGroupMembership {
  id: string;
  group: string;
  person: string;
  full_name: string;
  joined_on: string;
  exited_on: string | null;
  exit_reason: WltExitReason;
  exit_reason_display: string;
  exit_note: string;
}

/**
 * A woman the facilitator may add — eligible, verified and not currently in a
 * group. The pool carries literacy and device access because the "at least one
 * member with a device" rule is unenforceable if the screen cannot show who
 * has one.
 */
export interface WltCandidate {
  id: string;
  person: string;
  full_name: string;
  psnp_client_id: string;
  primary_iga: string;
  literacy_level: string;
  has_device: boolean;
  is_programme_eligible: boolean;
  is_assignable: boolean;
}

/** How far a woman has come, and what the next step needs. */
export type JourneyStageCode = "REGISTERED" | "VERIFIED" | "GROUPED" | "LINKED";

/**
 * Four states, not two.
 *
 * `blocked` and `waiting` call for different things from the facilitator most
 * likely to be reading the screen: one is her move, the other is a woreda
 * officer's. Only `ready` carries a button.
 */
export type JourneyStageState = "done" | "ready" | "waiting" | "blocked";

export interface JourneyCondition {
  code: string;
  label: string;
  threshold: string | null;
  actual: string | null;
  met: boolean;
  unit: string;
  unmeasurable: boolean;
}

export interface JourneyStage {
  code: JourneyStageCode;
  label: string;
  state: JourneyStageState;
  conditions: JourneyCondition[];
  detail: Record<string, unknown>;
}

export interface Journey {
  person: string;
  profile: string;
  full_name: string;
  stages: JourneyStage[];
  stages_done: number;
  stages_total: number;
  /** The first stage that is not done — what the screen leads with. Null when all four are. */
  next_action: JourneyStage | null;
}

export type WltVerificationStatus = "PENDING" | "VERIFIED" | "REJECTED";

export type WltEnrolmentRoute = "IMPORT" | "FACILITATOR";

/** A row on the WLT register. `person` is the `youth.Youth` id (handoff D1: one identity). */
export interface WltBeneficiary {
  id: string;
  person: string;
  full_name: string;
  psnp_client_id: string;
  // Integer primary keys, not codes: this serializer emits the FK directly,
  // unlike the locations API which is keyed on `code` throughout.
  psnp_woreda: number | null;
  psnp_kebele: number | null;
  els_completed_on: string | null;
  els_grant_received_on: string | null;
  primary_iga: string;
  literacy_level: string;
  digital_literacy: string;
  has_device: boolean;
  household_head: boolean;
  enrolment_route: WltEnrolmentRoute;
  verification_status: WltVerificationStatus;
  verification_note: string;
  verified_on: string | null;
  is_programme_eligible: boolean;
  is_assignable: boolean;
}

/** What `POST /wlt/profiles/import/` reports back. Not all-or-nothing, by design. */
export interface WltImportReport {
  batch: string;
  outcomes: { linked: number; queued: number; created: number; skipped: number };
  errors: { row: number; error: string }[];
  /** Rows whose cells could not be read at all — never imported, named by sheet row. */
  unreadable: { row: number; errors: Record<string, string[]> }[];
}

/**
 * One gate condition.
 *
 * `threshold` and `actual` always travel together — that is the rule the
 * readiness card exists for. "Attendance 74% (need 80%)" changes what a
 * facilitator does next week; a red dot does not. `unmeasurable` separates
 * "below the line" from "no denominator yet", which are different instructions.
 */
export interface GateCondition {
  code: string;
  label: string;
  threshold: string | number | boolean | null;
  actual: string | number | boolean | null;
  met: boolean;
  unmeasurable: boolean;
  /** "%" or empty. The handoff's own example carries the sign. */
  unit: string;
}

export interface GateResult {
  gate_set: string;
  passed: boolean;
  conditions: GateCondition[];
  policy_version_id: string;
  computed_at: string;
}

export interface WltRiskFlag {
  id: string;
  subject_type: string;
  subject_id: string;
  reason_code: string;
  raised_on: string;
  cleared_on: string | null;
}

export interface WltReadiness {
  group: WltGroup;
  gate: GateResult | null;
  indicators: Record<string, string | number | boolean | null | string[]>;
  risk_flags: WltRiskFlag[];
  computed_at: string;
}

export interface ServiceLinkage {
  id: string;
  linkage_type: string;
  type_label: string;
  provider: string | null;
  provider_name: string | null;
  subject_type: string;
  subject_name: string | null;
  status: LinkageStatus;
  status_display: string;
  opened_on: string;
  activated_on: string | null;
  /** What the subject still needs, in sentences. Empty unless BLOCKED. */
  block_reasons: string[];
}

export interface ClaReadinessRow {
  kebele_id: number;
  kebele: string;
  eligible_groups: number;
  threshold: number;
  groups_short: number;
}

// ---------------------------------------------------------------------------
// Sprint 5 — Training Enrolment (§4.5) and Placement (§4.7)
// ---------------------------------------------------------------------------

export type TrainingType = "LIFE_SKILLS" | "TVET";

export type TrainingCompletionStatus = "ENROLLED" | "COMPLETED" | "DROPPED_OUT" | "FAILED_ASSESSMENT";

export interface TrainingEnrolment {
  id: string;
  case: string;
  youth_name: string;
  woreda: string;
  training_type: TrainingType;
  training_type_display: string;
  trade_or_skill_area: string;
  training_provider: string;
  provider_name: string;
  enrolment_date: string;
  start_date: string;
  end_date: string;
  attendance_rate: string | null;
  completion_status: TrainingCompletionStatus;
  completion_status_display: string;
  completion_date: string | null;
  assessment_result: string;
  certificate_status: string;
  dropout_flag: boolean;
  dropout_date: string | null;
  dropout_reason: string;
  source_referral: string | null;
  /** §4.5, System-set on completion. What raises the onward-referral prompt. */
  triggers_onward_referral: boolean;
  onward_referral: string | null;
  recorded_by_name: string;
  /** Still open past its scheduled end date — what the trainer's queue sorts on. */
  is_overdue: boolean;
  days_in_training: number;
  notes: string;
}

export type PlacementTypeCode = "JOB" | "APPRENTICESHIP";

export type RetentionStatusCode = "PENDING" | "RETAINED" | "EXITED" | "UNREACHABLE";

export interface RetentionCheck {
  id: string;
  placement: string;
  /** 30, 60 or 90 — §4.7's three checkpoints. */
  checkpoint: number;
  due_date: string;
  status: RetentionStatusCode;
  status_display: string;
  checked_on: string | null;
  checked_by_name: string | null;
  note: string;
  is_overdue: boolean;
}

export interface Placement {
  id: string;
  case: string;
  youth_name: string;
  woreda: string;
  source_referral: string | null;
  employer_name: string;
  sector: string;
  placement_type: PlacementTypeCode;
  placement_type_display: string;
  placement_date: string;
  wage_amount: string | null;
  contract_type: string;
  contract_duration: string;
  /** OQ-3. A subsidised placement is excluded from the reported retention anchor. */
  is_subsidised: boolean;
  exit_date: string | null;
  exit_reason: string;
  exit_reason_display: string;
  exit_note: string;
  recorded_by_name: string;
  retention_checks: RetentionCheck[];
  days_held: number;
  is_open: boolean;
  notes: string;
}

// ---------------------------------------------------------------------------
// Sprint 6 — Enterprise (§4.8), Follow-Up (§4.9), Grievance (§4.10)
// ---------------------------------------------------------------------------

export type BusinessPlanStatus =
  "NOT_STARTED" | "DRAFTED" | "UNDER_REVIEW" | "REVISION_REQUESTED" | "APPROVED" | "REJECTED";

export type MilestoneStatusCode = "PENDING" | "ACHIEVED" | "MISSED" | "CANCELLED";

export interface EnterpriseMilestone {
  id: string;
  enterprise: string;
  milestone_name: string;
  target_date: string;
  completion_date: string | null;
  status: MilestoneStatusCode;
  status_display: string;
  note: string;
  is_overdue: boolean;
}

export interface Enterprise {
  id: string;
  case: string;
  youth_name: string;
  woreda: string;
  source_referral: string | null;
  business_name: string;
  sector: string;
  business_plan_status: BusinessPlanStatus;
  plan_status_display: string;
  support_type: string;
  support_type_display: string;
  grant_or_loan_amount: string | null;
  disbursement_date: string | null;
  mentorship_sessions_count: number;
  business_registration_status: string;
  market_linkage_status: string;
  market_linkage_display: string;
  started_trading_on: string | null;
  closed_on: string | null;
  closure_reason: string;
  recorded_by_name: string;
  milestones: EnterpriseMilestone[];
  milestones_achieved: number;
  milestones_overdue: number;
  /** Money or goods actually reached her. Not the same as an approved plan. */
  has_support: boolean;
  is_open: boolean;
  notes: string;
}

export type ContactOutcomeCode = "REACHED_ENGAGED" | "REACHED_NOT_ENGAGED" | "NO_RESPONSE" | "UNREACHABLE";

export interface FollowUp {
  id: string;
  case: string;
  youth_name: string;
  woreda: string;
  related_referral: string | null;
  attempt_date: string;
  contact_method: string;
  contact_method_display: string;
  contact_outcome: ContactOutcomeCode;
  contact_outcome_display: string;
  re_engagement_status: string;
  pathway_revision_flag: boolean;
  conducted_by_name: string;
  reached_the_youth: boolean;
  notes: string;
}

export type GrievanceStatus = "OPEN" | "IN_PROGRESS" | "RESOLVED" | "CLOSED";

export interface Grievance {
  id: string;
  case: string | null;
  youth_name: string | null;
  related_referral: string | null;
  about_partner: string | null;
  partner_name: string | null;
  woreda: string;
  complaint_type: string;
  complaint_type_display: string;
  raised_by: string;
  raised_by_display: string;
  complainant_name: string;
  complainant_contact: string;
  summary: string;
  date_raised: string;
  assigned_staff: string;
  assigned_staff_name: string;
  resolution_status: GrievanceStatus;
  status_display: string;
  resolution_date: string | null;
  resolution_notes: string;
  /** Feeds the partner performance panel — §4.11's qualitative counterpart. */
  referral_quality_feedback_flag: boolean;
  days_open: number;
  is_open: boolean;
  /** Safeguarding or staff conduct: visible to the assignee and the admin only. */
  is_sensitive: boolean;
}
