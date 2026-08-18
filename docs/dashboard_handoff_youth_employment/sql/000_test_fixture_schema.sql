-- =============================================================================
-- 000_test_fixture_schema.sql
--
-- TEST FIXTURE ONLY. DO NOT RUN IN STAGING OR PRODUCTION.
--
-- Django owns these tables via migrations. This file exists so the reporting
-- layer in 001-005 can be parsed and unit-tested against a scratch database
-- before the Django apps exist. It is a minimal stub of the columns the
-- reporting layer reads, matching YOUTH_EMPLOYMENT_PLATFORM_DEV_SPEC.md §4.
--
-- If a column here disagrees with the Django model, the Django model wins.
-- Fix this file, not the model.
-- =============================================================================

CREATE TABLE users_user (
    user_id             uuid PRIMARY KEY,
    full_name           text NOT NULL,
    role                text NOT NULL,
    partner_id          uuid NULL,
    account_status      text NOT NULL DEFAULT 'active',
    last_login          timestamptz NULL
);

CREATE TABLE partners_partner (
    partner_id          uuid PRIMARY KEY,
    partner_name        text NOT NULL,
    partner_type        text NOT NULL,
    contact_name        text NULL,
    phone               text NULL,
    email               text NULL,
    active_status       boolean NOT NULL DEFAULT true,
    mou_status          text NULL,
    mou_date            date NULL,
    performance_notes   text NULL
);

CREATE TABLE youth_youth (
    youth_id            uuid PRIMARY KEY,
    full_name           text NOT NULL,
    sex                 text NOT NULL,
    date_of_birth       date NOT NULL,
    phone_number        text NULL,
    national_or_kebele_id text NULL,
    region              text NOT NULL,
    zone                text NOT NULL,
    woreda              text NOT NULL,
    kebele              text NULL,
    household_id        text NULL,
    psnp_status         text NULL,
    psnp_client_category text NULL,   -- PW / PDS / TDS; see open question OQ-4
    education_level     text NULL,
    disability_status   text NULL,
    consent_given       boolean NOT NULL DEFAULT false,
    consent_date        date NULL,
    registration_date   date NOT NULL,
    registering_worker_id uuid NULL REFERENCES users_user(user_id)
);

CREATE TABLE cases_case (
    case_id             uuid PRIMARY KEY,
    youth_id            uuid NOT NULL UNIQUE REFERENCES youth_youth(youth_id),
    case_status         text NOT NULL,
    case_manager_id     uuid NULL REFERENCES users_user(user_id),
    woreda              text NOT NULL,
    opened_date         date NOT NULL,
    closed_date         date NULL,
    exit_reason         text NULL,
    last_activity_date  date NOT NULL,
    current_pathway_assignment_id uuid NULL,
    next_action         text NULL,
    next_action_owner_id uuid NULL REFERENCES users_user(user_id)
);

CREATE TABLE cases_profilingrecord (
    profiling_id        uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    work_history_summary text NULL,
    vulnerability_index_score numeric NULL,
    priority_flag       boolean NOT NULL DEFAULT false,
    assessed_date       date NOT NULL,
    assessor_id         uuid NULL REFERENCES users_user(user_id)
);

CREATE TABLE cases_pathwayassignment (
    pathway_assignment_id uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    selected_pathway    text NOT NULL,
    assessment_date     date NOT NULL,
    assessor_id         uuid NULL REFERENCES users_user(user_id),
    is_current          boolean NOT NULL DEFAULT true,
    superseded_by_id    uuid NULL,
    revision_reason     text NULL
);

CREATE TABLE referrals_referral (
    referral_id         uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    referral_category   text NOT NULL,
    referral_trigger    text NOT NULL,
    is_parallel         boolean NOT NULL DEFAULT false,
    parallel_group_id   uuid NULL,
    parent_referral_id  uuid NULL REFERENCES referrals_referral(referral_id),
    replacement_referral_id uuid NULL REFERENCES referrals_referral(referral_id),
    receiving_partner_id uuid NOT NULL REFERENCES partners_partner(partner_id),
    receiving_contact_name text NULL,
    initiated_date      date NOT NULL,
    initiated_by_id     uuid NULL REFERENCES users_user(user_id),
    confirmation_status text NOT NULL,
    confirmed_date      date NULL,
    confirmed_by        text NULL,
    status              text NOT NULL,
    outcome_type        text NULL,
    outcome_date        date NULL,
    outcome_verified_by_id uuid NULL REFERENCES users_user(user_id),
    outcome_verification_method text NULL,
    verification_source text NULL,   -- see OQ-2; self_reported / provider_confirmed / employer_confirmed / document_verified
    service_start_date  date NULL,   -- see OQ-1; the date the youth presented to the partner
    failure_reason_code text NULL,
    failure_date        date NULL,
    notes               text NULL
);

CREATE TABLE training_trainingenrolment (
    training_id         uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    training_type       text NOT NULL,
    trade_or_skill_area text NULL,
    training_provider_id uuid NOT NULL REFERENCES partners_partner(partner_id),
    enrolment_date      date NOT NULL,
    start_date          date NULL,
    end_date            date NULL,
    attendance_rate     numeric NULL,
    completion_status   text NOT NULL,
    assessment_result   text NULL,
    certificate_status  text NULL,
    dropout_flag        boolean NOT NULL DEFAULT false,
    dropout_date        date NULL,
    dropout_reason      text NULL,
    source_referral_id  uuid NULL REFERENCES referrals_referral(referral_id),
    triggers_onward_referral boolean NOT NULL DEFAULT false
);

CREATE TABLE placements_placement (
    placement_id        uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    source_referral_id  uuid NULL REFERENCES referrals_referral(referral_id),
    employer_name       text NOT NULL,
    sector              text NULL,
    placement_type      text NOT NULL,
    placement_date      date NOT NULL,
    wage_amount         numeric NULL,
    contract_type       text NULL,
    contract_duration   text NULL,
    is_subsidised       boolean NOT NULL DEFAULT false,  -- see OQ-3
    retention_check_30_status text NULL,
    retention_check_30_date   date NULL,
    retention_check_60_status text NULL,
    retention_check_60_date   date NULL,
    retention_check_90_status text NULL,
    retention_check_90_date   date NULL,
    exit_date           date NULL,
    exit_reason         text NULL
);

CREATE TABLE enterprises_enterprise (
    enterprise_id       uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    source_referral_id  uuid NULL REFERENCES referrals_referral(referral_id),
    business_plan_status text NOT NULL,
    grant_or_loan_amount numeric NULL,
    disbursement_date   date NULL,
    mentorship_sessions_count integer NULL,
    business_registration_status text NULL,
    business_registration_number text NULL,
    market_linkage_status text NULL
);

CREATE TABLE followups_followup (
    followup_id         uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    related_referral_id uuid NULL REFERENCES referrals_referral(referral_id),
    attempt_date        date NOT NULL,
    contact_method      text NOT NULL,
    contact_outcome     text NOT NULL,
    re_engagement_status text NULL,
    pathway_revision_flag boolean NOT NULL DEFAULT false,
    conducted_by_id     uuid NULL REFERENCES users_user(user_id)
);

CREATE TABLE grievances_grievance (
    grievance_id        uuid PRIMARY KEY,
    case_id             uuid NULL REFERENCES cases_case(case_id),
    related_referral_id uuid NULL REFERENCES referrals_referral(referral_id),
    complaint_type      text NOT NULL,
    raised_by           text NOT NULL,
    date_raised         date NOT NULL,
    assigned_staff_id   uuid NULL REFERENCES users_user(user_id),
    resolution_status   text NOT NULL,
    resolution_date     date NULL,
    resolution_notes    text NULL,
    referral_quality_feedback_flag boolean NOT NULL DEFAULT false
);

CREATE TABLE alerts_alert (
    alert_id            uuid PRIMARY KEY,
    case_id             uuid NOT NULL REFERENCES cases_case(case_id),
    alert_type          text NOT NULL,
    triggered_date      date NOT NULL,
    threshold_days      integer NOT NULL,
    assigned_to_id      uuid NULL REFERENCES users_user(user_id),
    status              text NOT NULL,
    actioned_date       date NULL,
    actioned_by_id      uuid NULL REFERENCES users_user(user_id)
);
