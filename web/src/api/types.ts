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
  | "SYSTEM_ADMIN";

export type CaseStatus = "ACTIVE" | "STALLED" | "REFERRAL_PENDING" | "PLACED" | "EXITED";

/** The §7 access row the API resolves for the current user. */
export interface AccessMatrix {
  case_scope: string;
  case_write: boolean;
  referral_scope: string;
  referral_write: boolean;
}

export interface CurrentUser {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  role_display: string;
  woreda_assignment: string[];
  partner: string | null;
  partner_name: string | null;
  account_status: string;
  access: AccessMatrix;
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
  /** Resolved server-side: the one assignment with is_current (spec §4.4). */
  current_pathway: PathwayAssignment | null;
  /** The most recent profiling record — §3's "latest record is current". */
  current_profiling: ProfilingRecord | null;
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
  email: string;
  full_name: string;
  role: Role;
  role_display: string;
  woreda_assignment: string[];
  partner: string | null;
  partner_name: string | null;
  account_status: "ACTIVE" | "SUSPENDED" | "INACTIVE";
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
  failure_reason_code: string | null;
  failure_reason_label: string | null;
  failure_date: string | null;
  notes: string;
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

export const ALERT_TYPE_COLOURS: Record<AlertTypeCode, string> = {
  STALL: "red",
  REFERRAL_CONFIRMATION_OVERDUE: "orange",
  FOLLOW_UP_DUE: "blue",
  ONWARD_REFERRAL_PROMPT: "green",
  REPLACEMENT_REFERRAL_PROMPT: "volcano",
  RETENTION_CHECK_DUE: "purple",
};

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
  /** Present only on the create response — §11's age band is unconfirmed, so
   *  an out-of-band registration warns rather than blocks. */
  age_band_warning?: string | null;
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
