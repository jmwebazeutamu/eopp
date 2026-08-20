import type { Referral, ReferralStatusCode, ReferralTriggerCode } from "../api/types";

/**
 * Referral fixtures for the timeline tests.
 *
 * Shaped like the API's read serializer rather than like the component's needs,
 * so a test that passes here is testing the real payload.
 */

let counter = 0;

export interface ReferralOverrides {
  id?: string;
  status?: ReferralStatusCode;
  referral_trigger?: ReferralTriggerCode;
  initiated_date?: string;
  outcome_date?: string | null;
  failure_date?: string | null;
  updated_at?: string;
  parent_referral?: string | null;
  replacement_referral?: string | null;
  parallel_group_id?: string | null;
  is_parallel?: boolean;
  referral_category_label?: string;
  partner_name?: string;
  counts_toward_parallel_cap?: boolean;
}

export function makeReferral(overrides: ReferralOverrides = {}): Referral {
  counter += 1;
  const id = overrides.id ?? `ref-${counter}`;
  const status = overrides.status ?? "ACTIVE";
  const partnerName = overrides.partner_name ?? "Adama Polytechnic";

  return {
    id,
    case: "case-1",
    youth_name: "Abebe Bekele",
    woreda: "Adama",
    referral_category: "TRAINING",
    referral_category_label: overrides.referral_category_label ?? "Training",
    referral_trigger: overrides.referral_trigger ?? "MANUAL",
    trigger_display: (overrides.referral_trigger ?? "MANUAL") === "MANUAL" ? "Manual" : "Onward",
    is_parallel: overrides.is_parallel ?? overrides.parallel_group_id != null,
    parallel_group_id: overrides.parallel_group_id ?? null,
    counts_toward_parallel_cap: overrides.counts_toward_parallel_cap ?? true,
    parent_referral: overrides.parent_referral ?? null,
    replacement_referral: overrides.replacement_referral ?? null,
    receiving_partner: "partner-1",
    receiving_partner_detail: { id: "partner-1", partner_name: partnerName, partner_type_display: "TVET" },
    receiving_contact_name: "Marta Tesfaye",
    initiated_date: overrides.initiated_date ?? "2026-01-05",
    initiated_by: "user-1",
    initiated_by_name: "Case Manager One",
    confirmation_status: "CONFIRMED",
    confirmation_status_display: "Confirmed",
    confirmed_date: "2026-01-07",
    confirmed_by: "Marta Tesfaye",
    status,
    status_display: status.replace(/_/g, " ").toLowerCase(),
    allowed_transitions: [],
    outcome_type: null,
    outcome_type_label: null,
    outcome_date: overrides.outcome_date ?? null,
    outcome_verification_method: "",
  verification_source: "",
    failure_reason_code: null,
    failure_reason_label: null,
    failure_date: overrides.failure_date ?? null,
    notes: "",
    created_at: "2026-01-05T08:00:00+03:00",
    updated_at: overrides.updated_at ?? "2026-01-05T08:00:00+03:00",
  };
}
