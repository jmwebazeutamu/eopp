/**
 * Beneficiary profile — API types.
 * Mirrors GET /api/wlt/beneficiaries/{id}/ (see api/beneficiary-detail.example.json).
 *
 * Every field the record may not hold is `| null`. The UI must render a
 * "+ Add" control for null, never an empty cell and never "N/A".
 */

export type BeneficiaryStatus = "active" | "inactive" | "exited";

export type MaritalStatus =
  | "single"
  | "married"
  | "widowed"
  | "divorced"
  | "separated";

export type DisabilityType =
  | "none"
  | "physical"
  | "visual"
  | "hearing"
  | "intellectual"
  | "multiple";

export type EducationLevel =
  | "none"
  | "adult_literacy"
  | "primary"
  | "secondary"
  | "tvet"
  | "tertiary";

export type StageKey = "registered" | "verified" | "in_group" | "linked";

export type CheckValue = { label: string; value: string; passed: boolean };

export interface PathwayStage {
  key: StageKey;
  label: string;
  /** stage is complete only when every check passes */
  complete: boolean;
  /** short line shown on the collapsed row, e.g. "Consent + PSNP kebele recorded" */
  summary: string;
  checks: CheckValue[];
}

export interface Identity {
  full_name: string;
  /** internal registry code, always present */
  reference_code: string;
  /** national PSNP client number; null until captured */
  psnp_client_number: string | null;
  photo_url: string | null;
  date_of_birth: string | null;      // ISO date
  /** server-computed from date_of_birth, or estimated_age when DOB is unknown */
  age: number | null;
  age_is_estimated: boolean;
  phone: string | null;              // E.164, e.g. +251912345678
  woreda: { id: string; name: string } | null;
  kebele: { id: string; name: string } | null;
  household_size: number | null;
  registered_on: string;             // ISO date
  status: BeneficiaryStatus;
  exited_on: string | null;
  exit_reason: string | null;
  /** count of null fields in the header set — drives the "N details missing" chip */
  missing_field_count: number;
}

export interface Household {
  is_head_of_household: boolean | null;
  marital_status: MaritalStatus | null;
  dependants_count: number | null;
  dependants_under_5: number | null;
  disability_type: DisabilityType | null;
  disability_notes: string | null;
  education_level: EducationLevel | null;
  education_grade: number | null;
}

export interface CaseInfo {
  development_agent: { id: string; name: string } | null;
  last_contact_on: string | null;    // ISO date, derived from contact log
  enterprise: { id: string; name: string; status: string } | null;
  open_grievance_count: number;      // derived, 0 when none
}

export interface SavingsGroup {
  id: string;
  name: string;
  phase_label: string;               // "Phase 2 — internal lending"
  member_count: number;
  facilitator_name: string | null;
  joined_on: string;
  status: "active" | "dormant" | "closed";
  logo_url: string | null;
  meetings_attended: number | null;
  meetings_held: number | null;
}

export interface Finance {
  currency: string;                  // "ETB"
  savings_total: string;             // decimal string, never float
  loans_received_total: string;
  loan_count: number;
  repayments_total: string;
  repayments_principal: string;
  repayments_service_charge: string;
  principal_outstanding: string;
}

export interface Linkage {
  id: string;
  type_label: string;                // "Group savings account"
  partner_name: string;
  active_since: string | null;
  status: "active" | "lapsed" | "pending";
  /** for linkages the group cannot reach yet */
  blocked_reason: string | null;     // "Needs Phase 3 — cluster level association"
}

export interface BeneficiaryDetail {
  id: string;
  identity: Identity;
  household: Household;
  case: CaseInfo;
  pathway: { stages: PathwayStage[]; complete_count: number; total_count: number };
  savings_group: SavingsGroup | null;
  finance: Finance;
  linkages: Linkage[];
  permissions: { can_edit: boolean; can_log_contact: boolean };
}
