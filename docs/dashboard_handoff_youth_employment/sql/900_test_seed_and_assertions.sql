-- =============================================================================
-- 900_test_seed_and_assertions.sql
--
-- TEST ONLY. Never run against staging or production.
--
-- Seeds a small, fully-controlled dataset with hand-computed expected values,
-- refreshes the reporting layer, and asserts each view returns what it should.
-- Every assertion raises an exception on failure, so `psql -v ON_ERROR_STOP=1`
-- exits non-zero and CI fails.
--
-- Run order:  000, 001, 002, 003, 004, 005, then this file.
-- (rpt.refresh_all() is defined in 005; running without it fails at the CALL below.)
--
-- The scenarios below are chosen to exercise the traps, not the happy path:
--   - a partner with n below the suppression floor
--   - a partner with n in the provisional band
--   - a cohort whose checkpoint has not yet arrived (censoring)
--   - a placement inside the maturation window (must not count as a failure)
--   - a referral raised inside the maturation window (must not count as unclosed)
--   - a voluntary exit (must not be classified as involuntary)
-- =============================================================================

SET client_min_messages = NOTICE;

TRUNCATE alerts_alert, grievances_grievance, followups_followup,
         enterprises_enterprise, placements_placement, training_trainingenrolment,
         referrals_referral, cases_pathwayassignment, cases_profilingrecord,
         cases_case, youth_youth, partners_partner, users_user CASCADE;

-- Freeze "today" for the test. Every expected value below is computed against it.
-- rpt.is_mature() defaults to current_date, so the seed dates are expressed
-- relative to current_date rather than hard-coded.

-- -----------------------------------------------------------------------------
-- Users
-- -----------------------------------------------------------------------------
INSERT INTO users_user (user_id, full_name, role) VALUES
    ('11111111-0000-0000-0000-000000000001', 'CM One',   'youth_case_manager'),
    ('11111111-0000-0000-0000-000000000002', 'CM Two',   'youth_case_manager'),
    ('11111111-0000-0000-0000-000000000003', 'Supervisor','woreda_supervisor');

-- -----------------------------------------------------------------------------
-- Partners: one high-volume, one provisional-band, one suppressed
-- -----------------------------------------------------------------------------
INSERT INTO partners_partner (partner_id, partner_name, partner_type) VALUES
    ('22222222-0000-0000-0000-000000000001', 'Big TVET College',   'tvet_institution'),
    ('22222222-0000-0000-0000-000000000002', 'Mid Employer',       'employer'),
    ('22222222-0000-0000-0000-000000000003', 'Tiny Legal Aid Desk','legal_aid');

-- -----------------------------------------------------------------------------
-- Youth + cases: 100 in Woreda A, 20 in Woreda B
-- -----------------------------------------------------------------------------
INSERT INTO youth_youth (
    youth_id, full_name, sex, date_of_birth, phone_number, region, zone, woreda,
    psnp_status, psnp_client_category, disability_status,
    consent_given, consent_date, registration_date, registering_worker_id)
SELECT
    ('33333333-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'Youth ' || i,
    CASE WHEN i % 2 = 0 THEN 'female' ELSE 'male' END,
    -- age bands: mix of 15-17, 18-24, 25-29
    (current_date - ((16 + (i % 13)) * 365 + 100))::date,
    CASE WHEN i % 10 = 0 THEN NULL ELSE '+2519' || lpad(i::text, 8, '0') END,  -- 12 missing phones
    'Oromia', 'East Shewa',
    CASE WHEN i <= 100 THEN 'Woreda A' ELSE 'Woreda B' END,
    'enrolled',
    CASE WHEN i % 3 = 0 THEN 'PW' ELSE 'PDS' END,
    CASE WHEN i % 25 = 0 THEN 'physical' ELSE 'none' END,
    true, current_date - 300, current_date - 300,
    '11111111-0000-0000-0000-000000000001'
FROM generate_series(1, 120) i;

INSERT INTO cases_case (
    case_id, youth_id, case_status, case_manager_id, woreda,
    opened_date, last_activity_date, closed_date)
SELECT
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('33333333-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    CASE
        WHEN i % 10 = 1 THEN 'stalled'
        WHEN i % 10 = 2 THEN 'referral_pending'
        WHEN i % 10 = 3 THEN 'placed'
        ELSE 'active'
    END,
    CASE WHEN i <= 60 THEN '11111111-0000-0000-0000-000000000001'::uuid
                      ELSE '11111111-0000-0000-0000-000000000002'::uuid END,
    CASE WHEN i <= 100 THEN 'Woreda A' ELSE 'Woreda B' END,
    current_date - 290,
    current_date - (i % 40),
    NULL
FROM generate_series(1, 120) i;

-- Programme exit for the M1 placement cohort, 190 days ago. This is what the
-- EXIT-ANCHORED retention measure (ME-4) and the UPSNJP 3-month indicator read.
-- Note the fixture keeps closed_date (programme exit) distinct from case_status:
-- a case can have exited the programme while its operational status is still
-- being worked, and the two anchors must not be conflated.
UPDATE cases_case
   SET closed_date = current_date - 190
 WHERE case_id IN (
    SELECT ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid
    FROM generate_series(1, 20) i
 );

-- One exited case with NO closed_date. closed_date is nullable, and a naive
-- WHERE clause on mv_caseload_status makes this row vanish without trace.
UPDATE cases_case
   SET case_status = 'exited', closed_date = NULL
 WHERE case_id = '44444444-0000-0000-0000-000000000119'::uuid;

-- Parallel referral load fixture (PM-7 / OQ-7): one case carrying THREE active
-- non-complementary referrals plus one active complementary referral. Under the
-- working default the complementary referral sits outside the two-referral cap,
-- so this case breaches the cap on 3, not on 4.
INSERT INTO referrals_referral (
    referral_id, case_id, referral_category, referral_trigger,
    receiving_partner_id, initiated_date, confirmed_date,
    confirmation_status, status)
VALUES
    ('7777777a-0000-0000-0000-000000000001', '44444444-0000-0000-0000-000000000001',
     'training', 'manual', '22222222-0000-0000-0000-000000000001',
     current_date - 60, current_date - 58, 'confirmed', 'active'),
    ('7777777a-0000-0000-0000-000000000002', '44444444-0000-0000-0000-000000000001',
     'employment_placement', 'manual', '22222222-0000-0000-0000-000000000002',
     current_date - 55, current_date - 54, 'confirmed', 'active'),
    ('7777777a-0000-0000-0000-000000000003', '44444444-0000-0000-0000-000000000001',
     'apprenticeship', 'manual', '22222222-0000-0000-0000-000000000002',
     current_date - 50, current_date - 49, 'confirmed', 'active'),
    ('7777777a-0000-0000-0000-000000000004', '44444444-0000-0000-0000-000000000001',
     'complementary_service', 'manual', '22222222-0000-0000-0000-000000000003',
     current_date - 45, current_date - 44, 'confirmed', 'active');

-- Profiling: 110 of 120 profiled  →  10 missing_profile
INSERT INTO cases_profilingrecord (profiling_id, case_id, assessed_date, assessor_id)
SELECT
    ('55555555-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    current_date - 280,
    '11111111-0000-0000-0000-000000000001'
FROM generate_series(1, 110) i;

-- Pathway: 100 of 120
INSERT INTO cases_pathwayassignment (pathway_assignment_id, case_id, selected_pathway, assessment_date, is_current)
SELECT
    ('66666666-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'wage_employment', current_date - 270, true
FROM generate_series(1, 100) i;

-- -----------------------------------------------------------------------------
-- Referrals
-- -----------------------------------------------------------------------------
-- Big TVET College: 40 closed and mature: 30 completed, 10 failed → 75%
INSERT INTO referrals_referral (
    referral_id, case_id, referral_category, referral_trigger,
    receiving_partner_id, initiated_date, confirmed_date, service_start_date,
    confirmation_status, status, outcome_type, outcome_date, outcome_verified_by_id,
    verification_source, failure_reason_code, failure_date)
SELECT
    ('77777777-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'training', 'manual',
    '22222222-0000-0000-0000-000000000001',
    current_date - 150,
    current_date - 147,                                  -- 3 days, inside the 7-day threshold
    current_date - 140,
    'confirmed',
    CASE WHEN i <= 30 THEN 'completed' ELSE 'failed' END,
    CASE WHEN i <= 30 THEN 'training_completion' END,
    CASE WHEN i <= 30 THEN current_date - 100 END,
    CASE WHEN i <= 30 THEN '11111111-0000-0000-0000-000000000001'::uuid END,
    CASE WHEN i <= 30 THEN 'provider_confirmed' END,
    CASE WHEN i > 30 THEN 'YOUTH_NO_SHOW' END,
    CASE WHEN i > 30 THEN current_date - 100 END
FROM generate_series(1, 40) i;

-- Mid Employer: 20 closed and mature: 8 completed, 12 failed → 40%
INSERT INTO referrals_referral (
    referral_id, case_id, referral_category, referral_trigger,
    receiving_partner_id, initiated_date, confirmed_date, service_start_date,
    confirmation_status, status, outcome_type, outcome_date, outcome_verified_by_id,
    verification_source, failure_reason_code, failure_date)
SELECT
    ('77777777-0000-0000-0001-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad((40 + i)::text, 12, '0'))::uuid,
    'employment_placement', 'manual',
    '22222222-0000-0000-0000-000000000002',
    current_date - 140,
    current_date - 125,                                  -- 15 days, breaches the threshold
    current_date - 120,
    'confirmed',
    CASE WHEN i <= 8 THEN 'completed' ELSE 'failed' END,
    CASE WHEN i <= 8 THEN 'job_placement' END,
    CASE WHEN i <= 8 THEN current_date - 120 END,
    CASE WHEN i <= 8 THEN '11111111-0000-0000-0000-000000000001'::uuid END,
    CASE WHEN i <= 8 THEN 'employer_confirmed' END,
    CASE WHEN i > 8 THEN 'PARTNER_CAPACITY' END,
    CASE WHEN i > 8 THEN current_date - 120 END
FROM generate_series(1, 20) i;

-- Tiny Legal Aid Desk: 6 closed: below the suppression floor of 10
INSERT INTO referrals_referral (
    referral_id, case_id, referral_category, referral_trigger,
    receiving_partner_id, initiated_date, confirmed_date, service_start_date,
    confirmation_status, status, outcome_type, outcome_date, outcome_verified_by_id,
    verification_source, failure_reason_code, failure_date)
SELECT
    ('77777777-0000-0000-0002-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad((70 + i)::text, 12, '0'))::uuid,
    'complementary_service', 'manual',
    '22222222-0000-0000-0000-000000000003',
    current_date - 130, current_date - 129, current_date - 125,
    'confirmed',
    CASE WHEN i <= 4 THEN 'completed' ELSE 'failed' END,
    CASE WHEN i <= 4 THEN 'service_uptake' END,
    CASE WHEN i <= 4 THEN current_date - 130 END,
    CASE WHEN i <= 4 THEN '11111111-0000-0000-0000-000000000001'::uuid END,
    CASE WHEN i <= 4 THEN 'provider_confirmed' END,
    CASE WHEN i > 4 THEN 'ELIGIBILITY_MISMATCH' END,
    CASE WHEN i > 4 THEN current_date - 130 END
FROM generate_series(1, 6) i;

-- THE MATURATION TRAP: 5 referrals raised 3 days ago and already failed.
-- These must be EXCLUDED from every rate denominator by rpt.is_mature().
INSERT INTO referrals_referral (
    referral_id, case_id, referral_category, referral_trigger,
    receiving_partner_id, initiated_date, confirmation_status, status,
    failure_reason_code, failure_date)
SELECT
    ('77777777-0000-0000-0003-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad((90 + i)::text, 12, '0'))::uuid,
    'training', 'manual',
    '22222222-0000-0000-0000-000000000001',
    current_date - 3, 'declined', 'failed', 'PARTNER_NON_RESPONSIVE', current_date - 1
FROM generate_series(1, 5) i;

-- -----------------------------------------------------------------------------
-- Training enrolments: 20 enrolled, 15 completed → 75%
-- -----------------------------------------------------------------------------
INSERT INTO training_trainingenrolment (
    training_id, case_id, training_type, training_provider_id,
    enrolment_date, completion_status)
SELECT
    ('88888888-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'tvet', '22222222-0000-0000-0000-000000000001',
    current_date - 200,
    CASE WHEN i <= 15 THEN 'completed' ELSE 'dropped_out' END
FROM generate_series(1, 20) i;

-- -----------------------------------------------------------------------------
-- Placements: the cohort/censoring scenarios
-- -----------------------------------------------------------------------------
-- Cohort M1: placed 200 days ago, 20 placements, ALL checkpoints mature.
--   15 still employed, 3 involuntary exits at day 40, 2 voluntary exits at day 50.
--   → 30d retention 20/20 = 100%; 60d and 90d = 15/20 = 75%
INSERT INTO placements_placement (
    placement_id, case_id, employer_name, placement_type, placement_date,
    is_subsidised, exit_date, exit_reason, retention_check_90_status)
SELECT
    ('99999999-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'Employer ' || i, 'job', current_date - 200, false,
    CASE WHEN i BETWEEN 16 AND 18 THEN current_date - 160
         WHEN i BETWEEN 19 AND 20 THEN current_date - 150 END,
    CASE WHEN i BETWEEN 16 AND 18 THEN 'dismissed'
         WHEN i BETWEEN 19 AND 20 THEN 'better_job' END,
    -- youth 14 and 15: unreachable at the 90-day check, NO exit_date recorded.
    -- The classic optimistic-default trap.
    CASE WHEN i IN (14, 15) THEN 'unreachable' ELSE 'reached' END
FROM generate_series(1, 20) i;

-- Cohort M2: placed 45 days ago, 10 placements. 30d mature, 60d and 90d NOT.
--   → 30d 10/10; 60d and 90d cells must be CENSORED, not 0%.
INSERT INTO placements_placement (
    placement_id, case_id, employer_name, placement_type, placement_date, is_subsidised)
SELECT
    ('99999999-0000-0000-0001-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad((30 + i)::text, 12, '0'))::uuid,
    'Employer B' || i, 'job', current_date - 45, false
FROM generate_series(1, 10) i;

-- Cohort M3: placed 10 days ago, 8 placements. NOTHING is mature.
--   → every cell censored. This is the trap that reads as programme collapse.
INSERT INTO placements_placement (
    placement_id, case_id, employer_name, placement_type, placement_date, is_subsidised)
SELECT
    ('99999999-0000-0000-0002-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad((50 + i)::text, 12, '0'))::uuid,
    'Employer C' || i, 'job', current_date - 10, false
FROM generate_series(1, 8) i;

-- -----------------------------------------------------------------------------
-- Alerts
-- -----------------------------------------------------------------------------
INSERT INTO alerts_alert (
    alert_id, case_id, alert_type, triggered_date, threshold_days,
    assigned_to_id, status)
SELECT
    ('aaaaaaaa-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    ('44444444-0000-0000-0000-' || lpad(i::text, 12, '0'))::uuid,
    'stall_alert',
    current_date - (10 + i), 7,
    '11111111-0000-0000-0000-000000000001',
    'open'
FROM generate_series(1, 12) i;

-- =============================================================================
-- Refresh, then assert
-- =============================================================================
CALL rpt.refresh_all();

DO $$
DECLARE
    v_int    integer;
    v_int2   integer;
    v_num    numeric;
    v_text   text;
    v_bool   boolean;
    v_has_date boolean;
BEGIN
    ----------------------------------------------------------------------------
    RAISE NOTICE 'A. Suppression policy';
    ----------------------------------------------------------------------------
    SELECT completion_rate INTO v_num
    FROM rpt.mv_partner_performance WHERE partner_name = 'Big TVET College';
    IF v_num IS DISTINCT FROM 75 THEN
        RAISE EXCEPTION 'A1 FAIL: Big TVET completion rate expected 75, got %', v_num;
    END IF;

    SELECT completion_rate, band INTO v_num, v_text
    FROM rpt.mv_partner_performance WHERE partner_name = 'Tiny Legal Aid Desk';
    IF v_num IS NOT NULL THEN
        RAISE EXCEPTION 'A2 FAIL: n=6 partner must have a NULL rate, got %', v_num;
    END IF;
    IF v_text <> 'suppress' THEN
        RAISE EXCEPTION 'A3 FAIL: n=6 partner band expected suppress, got %', v_text;
    END IF;

    SELECT band INTO v_text
    FROM rpt.mv_partner_performance WHERE partner_name = 'Mid Employer';
    IF v_text <> 'provisional' THEN
        RAISE EXCEPTION 'A4 FAIL: n=20 partner band expected provisional, got %', v_text;
    END IF;

    SELECT verdict INTO v_text
    FROM rpt.mv_partner_performance WHERE partner_name = 'Tiny Legal Aid Desk';
    IF v_text <> 'too_few' THEN
        RAISE EXCEPTION 'A5 FAIL: suppressed partner must return verdict too_few, got %', v_text;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'B. Maturation guard';
    ----------------------------------------------------------------------------
    -- 5 referrals failed 1 day ago, raised 3 days ago. They must not appear in
    -- the closed-and-mature denominator for Big TVET (40, not 45).
    SELECT n_closed INTO v_int
    FROM rpt.mv_partner_performance WHERE partner_name = 'Big TVET College';
    IF v_int <> 40 THEN
        RAISE EXCEPTION 'B1 FAIL: immature referrals leaked into the denominator; expected 40, got %', v_int;
    END IF;

    -- Same guard on the loop-closure indicator: 66 closed and mature
    -- (40 + 20 + 6), NOT 71.
    SELECT den INTO v_int FROM rpt.mv_results_framework WHERE ord = 7;
    IF v_int <> 66 THEN
        RAISE EXCEPTION 'B2 FAIL: loop-closure denominator expected 66, got %', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'C. Cohort censoring';
    ----------------------------------------------------------------------------
    -- Cohort M2 (45 days old): the 30-day cell is scoreable...
    SELECT retention_rate, is_censored INTO v_num, v_bool
    FROM rpt.mv_cohort_retention
    WHERE anchor = 'placement' AND checkpoint_days = 30 AND n_placed = 10;
    IF v_bool THEN RAISE EXCEPTION 'C1 FAIL: 30d cell for a 45-day-old cohort must not be censored'; END IF;
    IF v_num IS DISTINCT FROM 100 THEN
        RAISE EXCEPTION 'C2 FAIL: 30d retention expected 100, got %', v_num;
    END IF;

    -- ...but the 90-day cell must be censored with a NULL rate and a real date.
    SELECT retention_rate, is_censored, (matures_on IS NOT NULL)
      INTO v_num, v_bool, v_has_date
    FROM rpt.mv_cohort_retention
    WHERE anchor = 'placement' AND checkpoint_days = 90 AND n_placed = 10;
    IF NOT v_bool THEN RAISE EXCEPTION 'C3 FAIL: 90d cell for a 45-day-old cohort must be censored'; END IF;
    IF NOT v_has_date THEN
        RAISE EXCEPTION 'C3b FAIL: a censored cell must carry a matures_on date, not a blank';
    END IF;
    IF v_num IS NOT NULL THEN
        RAISE EXCEPTION 'C4 FAIL: censored cell must return NULL, not %. A 0 here reads as programme collapse.', v_num;
    END IF;

    -- Cohort M1 (200 days old): 15 of 20 retained at 90 days.
    SELECT retention_rate INTO v_num
    FROM rpt.mv_cohort_retention
    WHERE anchor = 'placement' AND checkpoint_days = 90 AND n_placed = 20;
    IF v_num IS DISTINCT FROM 75 THEN
        RAISE EXCEPTION 'C5 FAIL: 90d retention for the mature cohort expected 75, got %', v_num;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'D. Disposition: voluntary exits are not failures';
    ----------------------------------------------------------------------------
    SELECT n INTO v_int FROM rpt.mv_placement_disposition WHERE disposition = 'left_for_better';
    IF v_int <> 2 THEN
        RAISE EXCEPTION 'D1 FAIL: expected 2 voluntary exits classified separately, got %', v_int;
    END IF;
    SELECT n INTO v_int FROM rpt.mv_placement_disposition WHERE disposition = 'left_involuntarily';
    IF v_int <> 3 THEN
        RAISE EXCEPTION 'D2 FAIL: expected 3 involuntary exits, got %', v_int;
    END IF;
    SELECT n INTO v_int FROM rpt.mv_placement_disposition WHERE disposition = 'still_placed';
    IF v_int <> 13 THEN
        RAISE EXCEPTION 'D3 FAIL: expected 13 still placed, got %', v_int;
    END IF;

    -- The optimistic-default trap: two youth are unreachable at the 90-day check
    -- and have no exit_date. They must NOT be counted as still placed.
    SELECT n INTO v_int FROM rpt.mv_placement_disposition WHERE disposition = 'outcome_unknown';
    IF v_int IS DISTINCT FROM 2 THEN
        RAISE EXCEPTION 'D3b FAIL: expected 2 unreachable youth in outcome_unknown, got %. '
                        'An unverified outcome must never be counted as a success.', v_int;
    END IF;

    -- PM-6 is a four-segment stacked bar; the view must never emit a fifth.
    SELECT count(DISTINCT disposition) INTO v_int FROM rpt.mv_placement_disposition;
    IF v_int > 4 THEN
        RAISE EXCEPTION 'D3c FAIL: % disposition segments; PM-6 caps at 4', v_int;
    END IF;
    -- The 45-day and 10-day cohorts must not appear at all: not yet due.
    SELECT sum(n) INTO v_int FROM rpt.mv_placement_disposition;
    IF v_int <> 20 THEN
        RAISE EXCEPTION 'D4 FAIL: immature placements leaked into the disposition; expected 20, got %', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'E. Pipeline';
    ----------------------------------------------------------------------------
    SELECT n_reached INTO v_int FROM rpt.mv_pipeline_summary
    WHERE stage_order = 1 AND woreda = 'Woreda A';
    IF v_int <> 100 THEN RAISE EXCEPTION 'E1 FAIL: Woreda A registered expected 100, got %', v_int; END IF;

    SELECT sum(n_reached) INTO v_int FROM rpt.mv_pipeline_summary WHERE stage_order = 2;
    IF v_int <> 110 THEN RAISE EXCEPTION 'E2 FAIL: profiled expected 110, got %', v_int; END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'F. Timeliness -- percent within threshold, not a mean';
    ----------------------------------------------------------------------------
    -- Big TVET confirms in 3 days (on time), Mid Employer in 15 (late).
    SELECT pct_confirmed_on_time INTO v_num
    FROM rpt.mv_partner_performance WHERE partner_name = 'Big TVET College';
    IF v_num IS DISTINCT FROM 100 THEN
        RAISE EXCEPTION 'F1 FAIL: Big TVET on-time rate expected 100, got %', v_num;
    END IF;
    SELECT median_days_to_confirm INTO v_int
    FROM rpt.mv_partner_performance WHERE partner_name = 'Mid Employer';
    IF v_int <> 15 THEN
        RAISE EXCEPTION 'F2 FAIL: Mid Employer median days to confirm expected 15, got %', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'G. PII must not reach the reporting layer';
    ----------------------------------------------------------------------------
    SELECT count(*) INTO v_int
    FROM information_schema.columns
    WHERE table_schema = 'rpt'
      AND column_name IN ('full_name','phone_number','national_or_kebele_id')
      AND table_name NOT IN ('mv_caseload_status','mv_alert_load');  -- staff names only
    IF v_int <> 0 THEN
        RAISE EXCEPTION 'G1 FAIL: % PII column(s) exposed in the rpt schema', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'H. Data completeness';
    ----------------------------------------------------------------------------
    SELECT sum(n_missing) INTO v_int
    FROM rpt.mv_data_completeness WHERE field_label = 'Phone number';
    IF v_int <> 12 THEN RAISE EXCEPTION 'H1 FAIL: expected 12 missing phone numbers, got %', v_int; END IF;

    SELECT sum(n_missing) INTO v_int
    FROM rpt.mv_data_completeness WHERE field_label = 'Profiling record';
    IF v_int <> 10 THEN RAISE EXCEPTION 'H2 FAIL: expected 10 missing profiles, got %', v_int; END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'I. Results framework';
    ----------------------------------------------------------------------------
    SELECT actual INTO v_num FROM rpt.mv_results_framework WHERE ord = 3;   -- training completion
    IF v_num IS DISTINCT FROM 75 THEN
        RAISE EXCEPTION 'I1 FAIL: training completion rate expected 75, got %', v_num;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'J. Parallel referral cap (PM-7 / OQ-7)';
    ----------------------------------------------------------------------------
    SELECT n_active_capped, n_active_complementary, breaches_cap
      INTO v_int, v_int2, v_bool
    FROM rpt.mv_parallel_load
    WHERE case_id = '44444444-0000-0000-0000-000000000001'::uuid;
    IF v_int <> 3 THEN
        RAISE EXCEPTION 'J1 FAIL: expected 3 capped active referrals, got %', v_int;
    END IF;
    IF v_int2 <> 1 THEN
        RAISE EXCEPTION 'J2 FAIL: expected 1 complementary active referral, got %', v_int2;
    END IF;
    IF NOT v_bool THEN
        RAISE EXCEPTION 'J3 FAIL: 3 capped active referrals must breach the two-referral cap';
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'K. Caseload: exited cases with a NULL closed_date';
    ----------------------------------------------------------------------------
    SELECT sum(n_cases) INTO v_int FROM rpt.mv_caseload_status;
    IF v_int <> 120 THEN
        RAISE EXCEPTION 'K1 FAIL: expected all 120 cases in the caseload view, got %. '
                        'An exited case with a NULL closed_date is being dropped.', v_int;
    END IF;
    SELECT count(DISTINCT display_segment) INTO v_int FROM rpt.mv_caseload_status;
    IF v_int > 4 THEN
        RAISE EXCEPTION 'K2 FAIL: % display segments; WS-1 caps at 4', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'L. Outcome matrix must contain explicit zero cells';
    ----------------------------------------------------------------------------
    SELECT count(*) INTO v_int
    FROM rpt.mv_referral_outcome_matrix
    WHERE n_referrals = 0;
    IF v_int = 0 THEN
        RAISE EXCEPTION 'L1 FAIL: no zero cells. A plain GROUP BY omits absent combinations, '
                        'and the absent combinations are the finding on PM-3.';
    END IF;
    -- training -> job_placement is the specific empty cell the card exists to expose
    SELECT n_referrals INTO v_int
    FROM rpt.mv_referral_outcome_matrix
    WHERE referral_category = 'training' AND outcome_type = 'job_placement'
    LIMIT 1;
    IF v_int IS NULL THEN
        RAISE EXCEPTION 'L2 FAIL: training -> job_placement cell is absent, not zero';
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'M. Pipeline medians must never be negative';
    ----------------------------------------------------------------------------
    SELECT count(*) INTO v_int
    FROM rpt.mv_pipeline_summary
    WHERE median_days_in_prev_stage < 0;
    IF v_int > 0 THEN
        RAISE EXCEPTION 'M1 FAIL: % pipeline stages report a negative median days-in-stage', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'N. Suppressed cells must not leak their numerator';
    ----------------------------------------------------------------------------
    SELECT completion_rate_label INTO v_text
    FROM rpt.mv_partner_performance WHERE partner_name = 'Tiny Legal Aid Desk';
    IF v_text ~ '[0-9]+/[0-9]+' THEN
        RAISE EXCEPTION 'N1 FAIL: suppressed label "%" still publishes the counts the '
                        'suppression was meant to hide', v_text;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'O. Provisional band is never given a comparison verdict';
    ----------------------------------------------------------------------------
    SELECT verdict INTO v_text
    FROM rpt.mv_partner_performance WHERE partner_name = 'Mid Employer';   -- n = 20
    IF v_text <> 'too_few' THEN
        RAISE EXCEPTION 'O1 FAIL: provisional-band partner given verdict "%". A funnel verdict '
                        'is a comparison, and the provisional band is never compared.', v_text;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'P. Both retention anchors are computed (ME-4)';
    ----------------------------------------------------------------------------
    SELECT count(DISTINCT anchor) INTO v_int FROM rpt.mv_cohort_retention;
    IF v_int <> 2 THEN
        RAISE EXCEPTION 'P1 FAIL: expected both placement and exit anchors, got % distinct', v_int;
    END IF;

    ----------------------------------------------------------------------------
    RAISE NOTICE 'Q. Freshness stamp is populated';
    ----------------------------------------------------------------------------
    SELECT count(*) INTO v_int FROM rpt.v_freshness WHERE scope IN ('operational','donor');
    IF v_int <> 2 THEN
        RAISE EXCEPTION 'Q1 FAIL: rpt.v_freshness must report both scopes, got %', v_int;
    END IF;

    RAISE NOTICE '=======================================';
    RAISE NOTICE 'ALL REPORTING LAYER ASSERTIONS PASSED';
    RAISE NOTICE '=======================================';
END
$$;
