-- =============================================================================
-- 900_test_seed_and_assertions.sql
--
-- Seeds one full group lifecycle and asserts every invariant the module depends
-- on. Run against a scratch database after 000-004. If any assertion raises,
-- the schema is wrong, not the test.
--
--   createdb wlt_test
--   for f in 000 001 002 003 004 900; do psql -d wlt_test -v ON_ERROR_STOP=1 -f ${f}*.sql; done
--
-- Expected final output: "ALL ASSERTIONS PASSED".
-- =============================================================================

\set ON_ERROR_STOP on

CREATE OR REPLACE FUNCTION pg_temp.assert(cond boolean, msg text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF NOT cond OR cond IS NULL THEN
        RAISE EXCEPTION 'ASSERTION FAILED: %', msg;
    END IF;
    RAISE NOTICE 'ok: %', msg;
END $$;

-- Runs p_sql in a subtransaction and asserts it is rejected. The subtransaction
-- rolls back on failure, so negative tests leave no residue behind them.
CREATE OR REPLACE FUNCTION pg_temp.expect_fail(p_sql text, p_msg text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE p_sql;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'ok: % [rejected: %]', p_msg, left(SQLERRM, 70);
        RETURN;
    END;
    RAISE EXCEPTION 'ASSERTION FAILED: % (the statement was accepted when it should have been rejected)', p_msg;
END $$;

-- =============================================================================
-- SEED
-- =============================================================================

INSERT INTO core.geography (id, parent_id, level, name, code) VALUES
 ('33333333-0000-0000-0000-000000000001','11111111-0000-0000-0000-000000000002','woreda','Test Woreda','TW1'),
 ('33333333-0000-0000-0000-000000000002','33333333-0000-0000-0000-000000000001','kebele','Test Kebele','TK1');

INSERT INTO core.app_user (id, username, role, scope_geo_id) VALUES
 ('44444444-0000-0000-0000-000000000001','fac.hana','wlt_facilitator','33333333-0000-0000-0000-000000000002'),
 ('44444444-0000-0000-0000-000000000002','woreda.ato','woreda_fsco','33333333-0000-0000-0000-000000000001');

-- 20 women, verified, imported from the ELS caseload
INSERT INTO core.person (id, full_name, sex, birth_year, kebele_id)
SELECT ('55555555-0000-0000-0000-0000000000' || lpad(i::text,2,'0'))::uuid,
       'Member ' || i, 'female', 1990, '33333333-0000-0000-0000-000000000002'
  FROM generate_series(1,20) i;

INSERT INTO wlt.beneficiary_profile
 (person_id, psnp_client_id, els_completed_on, els_grant_received_on,
  literacy_level, digital_literacy, has_device, enrolment_route,
  verification_status, verified_on, verified_by)
SELECT p.id, 'PSNP-' || right(p.full_name, 2), '2025-06-01', '2025-08-01',
       CASE WHEN p.full_name IN ('Member 1','Member 2') THEN 'functional' ELSE 'none' END,
       CASE WHEN p.full_name = 'Member 1' THEN 'basic' ELSE 'none' END,
       p.full_name = 'Member 1',
       'import', 'verified', '2025-12-01', '44444444-0000-0000-0000-000000000002'
  FROM core.person p;

-- Mobilisation, then the group
INSERT INTO wlt.mobilisation_event
 (id, kebele_id, held_on, facilitator_id, attendees_potential, attendees_husbands,
  attendees_elders, attendees_leaders, endorsement_obtained)
VALUES ('66666666-0000-0000-0000-000000000001','33333333-0000-0000-0000-000000000002',
        '2026-01-10','44444444-0000-0000-0000-000000000001',28,12,5,3,true);

-- A second mobilisation where the community refused. Recorded deliberately.
INSERT INTO wlt.mobilisation_event
 (kebele_id, held_on, facilitator_id, endorsement_obtained, endorsement_note)
VALUES ('33333333-0000-0000-0000-000000000002','2026-01-12',
        '44444444-0000-0000-0000-000000000001', false, 'elders declined pending clan consultation');

INSERT INTO wlt.group (id, name, kebele_id, mobilisation_event_id, status, drafted_on, created_by)
VALUES ('77777777-0000-0000-0000-000000000001','Tesfa SHG','33333333-0000-0000-0000-000000000002',
        '66666666-0000-0000-0000-000000000001','draft','2026-01-15','44444444-0000-0000-0000-000000000001');

INSERT INTO wlt.bylaw_version
 (id, group_id, version_no, effective_from, meeting_cadence, meeting_day, contribution_etb,
  service_charge_basis, service_charge_rate, service_charge_label, late_penalty_etb,
  officer_rotation_months, loan_quorum_pct, max_concurrent_loans, reserve_buffer_pct, recorded_by)
VALUES ('88888888-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',1,'2026-01-20',
        'weekly','Tuesday',20.00,'flat_per_loan',0.0500,'service_charge',5.00,6,60,5,20,
        '44444444-0000-0000-0000-000000000001');

INSERT INTO wlt.group_membership (group_id, person_id, joined_on)
SELECT '77777777-0000-0000-0000-000000000001', id, '2026-01-20' FROM core.person;

INSERT INTO wlt.office_holder (group_id, person_id, role, from_date) VALUES
 ('77777777-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000001','chair','2026-01-20'),
 ('77777777-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000002','secretary','2026-01-20'),
 ('77777777-0000-0000-0000-000000000001','55555555-0000-0000-0000-000000000003','treasurer','2026-01-20');

UPDATE wlt.group SET status = 'constituted', constituted_on = '2026-01-20'
 WHERE id = '77777777-0000-0000-0000-000000000001';

-- 12 weekly savings meetings, all 20 members present and saving ETB 20
DO $$
DECLARE i integer; mid uuid; d date; opening numeric := 0;
BEGIN
  FOR i IN 1..12 LOOP
    d := date '2026-01-27' + ((i-1) * 7);
    mid := gen_random_uuid();
    INSERT INTO wlt.meeting
      (id, group_id, scheduled_for, held_on, meeting_no, bylaw_version_id,
       opening_cash_etb, social_time_minutes, social_topic, recorded_by, status)
    VALUES (mid,'77777777-0000-0000-0000-000000000001', d, d, i,
            '88888888-0000-0000-0000-000000000001', opening, 20,
            'household decision-making','44444444-0000-0000-0000-000000000001','open');

    INSERT INTO wlt.attendance (meeting_id, person_id, status)
    SELECT mid, person_id, 'present' FROM wlt.roster_on('77777777-0000-0000-0000-000000000001', d);

    INSERT INTO wlt.ledger_entry (group_id, meeting_id, person_id, entry_type, account, amount_etb, created_by)
    SELECT '77777777-0000-0000-0000-000000000001', mid, person_id, 'savings', 'cash', 20.00,
           '44444444-0000-0000-0000-000000000001'
      FROM wlt.roster_on('77777777-0000-0000-0000-000000000001', d);

    opening := opening + 400.00;   -- 20 members x ETB 20
    UPDATE wlt.meeting
       SET status = 'closed', closing_cash_etb = opening, counted_cash_etb = opening, closed_at = now()
     WHERE id = mid;
  END LOOP;
END $$;

UPDATE wlt.group SET status = 'active', current_phase = 'p1', activated_on = '2026-01-27'
 WHERE id = '77777777-0000-0000-0000-000000000001';

-- =============================================================================
-- ASSERTIONS
-- =============================================================================

-- A1. Formation produced the expected shape
SELECT pg_temp.assert(
  (SELECT members_current FROM wlt.v_group_roster
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = 20,
  'A1 roster is 20 members');

SELECT pg_temp.assert(
  (SELECT count(*) FROM wlt.meeting
    WHERE group_id = '77777777-0000-0000-0000-000000000001' AND status = 'closed') = 12,
  'A2 twelve meetings closed');

-- A3. Fund equals 12 meetings x 20 members x ETB 20 = 4,800
SELECT pg_temp.assert(
  (SELECT sum(amount_etb) FROM wlt.ledger_entry
    WHERE group_id = '77777777-0000-0000-0000-000000000001' AND entry_type = 'savings') = 4800.00,
  'A3 savings total is ETB 4,800');

-- A4. Till reconciliation blocks an unbalanced close.
-- Setup and the failing close run together in one subtransaction, so nothing
-- is left behind when it is rejected.
SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.meeting (id, group_id, scheduled_for, held_on, meeting_no,
                             opening_cash_etb, recorded_by, status)
    VALUES ('cccccccc-0000-0000-0000-000000000099','77777777-0000-0000-0000-000000000001',
            '2026-04-21','2026-04-21',99,4800.00,'44444444-0000-0000-0000-000000000001','open');
    INSERT INTO wlt.ledger_entry (group_id, meeting_id, entry_type, account, amount_etb)
    VALUES ('77777777-0000-0000-0000-000000000001','cccccccc-0000-0000-0000-000000000099',
            'savings','cash',400.00);
    UPDATE wlt.meeting SET status='closed', closing_cash_etb=5200.00, counted_cash_etb=5000.00
     WHERE id='cccccccc-0000-0000-0000-000000000099';
$q$, 'A4 unbalanced till rejected on meeting close (ETB 200 short)');

-- A5. Ledger is append-only. Corrections are reversals, never edits.
SELECT pg_temp.expect_fail($q$
    UPDATE wlt.ledger_entry SET amount_etb = 999
     WHERE id = (SELECT id FROM wlt.ledger_entry
                  WHERE group_id = '77777777-0000-0000-0000-000000000001' LIMIT 1);
$q$, 'A5 ledger rejects UPDATE');

SELECT pg_temp.expect_fail($q$
    DELETE FROM wlt.ledger_entry
     WHERE id = (SELECT id FROM wlt.ledger_entry
                  WHERE group_id = '77777777-0000-0000-0000-000000000001' LIMIT 1);
$q$, 'A6 ledger rejects DELETE');

-- A7. One open group membership per person. The hybrid enrolment route makes
-- double assignment a realistic weekly event, so this is enforced in the database.
INSERT INTO wlt.group (id, name, kebele_id, status)
VALUES ('77777777-0000-0000-0000-000000000002','Rival SHG',
        '33333333-0000-0000-0000-000000000002','draft');

SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.group_membership (group_id, person_id, joined_on)
    VALUES ('77777777-0000-0000-0000-000000000002',
            '55555555-0000-0000-0000-000000000001','2026-02-01');
$q$, 'A7 a woman cannot join a second active group');

-- A8. One holder per office at a time
SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.office_holder (group_id, person_id, role, from_date)
    VALUES ('77777777-0000-0000-0000-000000000001',
            '55555555-0000-0000-0000-000000000004','treasurer','2026-03-01');
$q$, 'A8 two concurrent treasurers rejected; close the term first');

-- A9. Loan lifecycle and PAR30
INSERT INTO wlt.loan (id, group_id, person_id, cycle_batch, disbursed_on, principal_etb,
                      charge_basis, charge_rate, purpose, due_on, status)
VALUES ('99999999-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',
        '55555555-0000-0000-0000-000000000005',1,'2026-03-03',400.00,
        'flat_per_loan',0.0500,'iga','2026-03-31','disbursed');

-- overdue loan, no repayment
INSERT INTO wlt.loan (id, group_id, person_id, cycle_batch, disbursed_on, principal_etb,
                      charge_basis, charge_rate, purpose, due_on, status)
VALUES ('99999999-0000-0000-0000-000000000002','77777777-0000-0000-0000-000000000001',
        '55555555-0000-0000-0000-000000000006',1,'2026-02-03',600.00,
        'flat_per_loan',0.0500,'emergency','2026-03-03','disbursed');

INSERT INTO wlt.repayment (loan_id, paid_on, principal_etb, charge_etb)
VALUES ('99999999-0000-0000-0000-000000000001','2026-03-24',400.00,20.00);

REFRESH MATERIALIZED VIEW wlt.mv_group_financials;

SELECT pg_temp.assert(
  (SELECT loans_outstanding_etb FROM wlt.mv_group_financials
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = 600.00,
  'A9 outstanding principal is ETB 600 after one loan repaid');

SELECT pg_temp.assert(
  (SELECT par30_pct FROM wlt.mv_group_financials
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = 100.0,
  'A10 PAR30 is 100% when the only outstanding loan is over 30 days past due');

-- A11. A member with an outstanding loan cannot exit. Force settlement,
-- write-off with approval, or transfer of obligation first.
SELECT pg_temp.expect_fail($q$
    UPDATE wlt.group_membership
       SET exited_on = '2026-04-01', exit_reason = 'moved'
     WHERE person_id = '55555555-0000-0000-0000-000000000006';
$q$, 'A11 exit blocked while a loan is outstanding');

-- A12. A member with no outstanding loan can exit
-- exit dated after her last recorded meeting (2026-04-14), as it would be in
-- the field. Dating an exit before a meeting she attended is a data error, and
-- mv_group_compliance will show attendance above 100% when it happens. That is
-- a useful signal, not a bug: investigate it.
UPDATE wlt.group_membership
   SET exited_on = '2026-04-20', exit_reason = 'married_out'
 WHERE person_id = '55555555-0000-0000-0000-000000000020';

SELECT pg_temp.assert(
  (SELECT members_current FROM wlt.v_group_roster
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = 19,
  'A12 roster drops to 19 after a clean exit');

-- A13. Historical indicators use the roster as it stood, not as it stands now
SELECT pg_temp.assert(
  (SELECT count(*) FROM wlt.roster_on('77777777-0000-0000-0000-000000000001','2026-02-10')) = 20,
  'A13 roster_on returns 20 for a date before the exit');

REFRESH MATERIALIZED VIEW wlt.mv_group_compliance;

SELECT pg_temp.assert(
  (SELECT attendance_pct FROM wlt.mv_group_compliance
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = 100.0,
  'A14 attendance is 100% and is not distorted by the later exit');

-- =============================================================================
-- LINKAGE ASSERTIONS  (DECISION D3 + D4)
-- =============================================================================

-- A15. A service linkage is a referral with a group subject
INSERT INTO referrals.referral (id, type_code, provider_id, subject_group_id, status, opened_on)
VALUES ('aaaaaaaa-0000-0000-0000-000000000001','savings_account',
        '22222222-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',
        'proposed','2026-04-05');

SELECT pg_temp.assert(
  (SELECT subject_type FROM referrals.referral
    WHERE id = 'aaaaaaaa-0000-0000-0000-000000000001') = 'group',
  'A15 referral subject_type resolves to group');

-- A16/A17. Exactly one subject. This is the integrity a GenericForeignKey
-- cannot give you.
SELECT pg_temp.expect_fail($q$
    INSERT INTO referrals.referral (type_code, subject_group_id, subject_person_id, status)
    VALUES ('service_referral','77777777-0000-0000-0000-000000000001',
            '55555555-0000-0000-0000-000000000001','proposed');
$q$, 'A16 a referral cannot have two subjects');

SELECT pg_temp.expect_fail($q$
    INSERT INTO referrals.referral (type_code, status) VALUES ('service_referral','proposed');
$q$, 'A17 a referral cannot have zero subjects');

-- A18. SAFEGUARDING: a protection referral cannot be created against a group.
-- Handbook section 3.6 puts GBV on the meeting agenda. This turns the
-- confidentiality norm into a database constraint rather than a convention.
SELECT pg_temp.expect_fail($q$
    INSERT INTO referrals.referral (type_code, subject_group_id, status)
    VALUES ('protection_referral','77777777-0000-0000-0000-000000000001','proposed');
$q$, 'A18 protection referral rejected for a group subject');

-- A19. The same protection referral is permitted for a person
INSERT INTO referrals.referral (type_code, subject_person_id, status)
VALUES ('protection_referral','55555555-0000-0000-0000-000000000007','proposed');

SELECT pg_temp.assert(
  (SELECT count(*) FROM referrals.referral
    WHERE type_code = 'protection_referral' AND subject_type = 'person') = 1,
  'A19 protection referral permitted for a person subject');

-- A20. Credit facility cannot take a group subject. Pilot rule, and the
-- clearest finding in the Ethiopian savings-group literature.
SELECT pg_temp.expect_fail($q$
    INSERT INTO referrals.referral (type_code, subject_group_id, status)
    VALUES ('credit_facility','77777777-0000-0000-0000-000000000001','proposed');
$q$, 'A20 group-level credit facility blocked in the pilot');

-- =============================================================================
-- STRUCTURAL LINKAGE ASSERTIONS
-- =============================================================================

INSERT INTO wlt.cla (id, name, kebele_id, formed_on, meeting_cadence)
VALUES ('bbbbbbbb-0000-0000-0000-000000000001','Test Kebele CLA',
        '33333333-0000-0000-0000-000000000002','2027-02-01','quarterly');

INSERT INTO wlt.structural_membership (parent_type, parent_id, child_type, child_id, joined_on)
VALUES ('cla','bbbbbbbb-0000-0000-0000-000000000001','group',
        '77777777-0000-0000-0000-000000000001','2027-02-01');

-- A21. A group belongs to at most one CLA
INSERT INTO wlt.cla (id, name, kebele_id, formed_on)
VALUES ('bbbbbbbb-0000-0000-0000-000000000002','Second CLA',
        '33333333-0000-0000-0000-000000000002','2027-03-01');

SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.structural_membership (parent_type, parent_id, child_type, child_id, joined_on)
    VALUES ('cla','bbbbbbbb-0000-0000-0000-000000000002','group',
            '77777777-0000-0000-0000-000000000001','2027-03-01');
$q$, 'A21 a group cannot belong to two CLAs at once');

-- A22. Hierarchy is enforced: a federation contains CLAs, never groups directly
INSERT INTO wlt.federation (id, name, woreda_id, formed_on)
VALUES ('dddddddd-0000-0000-0000-000000000001','Test Woreda Federation',
        '33333333-0000-0000-0000-000000000001','2028-01-01');

SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.structural_membership (parent_type, parent_id, child_type, child_id, joined_on)
    VALUES ('federation','dddddddd-0000-0000-0000-000000000001','group',
            '77777777-0000-0000-0000-000000000001','2028-01-01');
$q$, 'A22 a federation cannot contain a group directly, only CLAs');

-- A23. At most two delegates per group per CLA. Handbook section 4, phase 3.
INSERT INTO wlt.delegate (cla_id, group_id, person_id, from_date) VALUES
 ('bbbbbbbb-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',
  '55555555-0000-0000-0000-000000000001','2027-02-01'),
 ('bbbbbbbb-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',
  '55555555-0000-0000-0000-000000000002','2027-02-01');

SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.delegate (cla_id, group_id, person_id, from_date)
    VALUES ('bbbbbbbb-0000-0000-0000-000000000001','77777777-0000-0000-0000-000000000001',
            '55555555-0000-0000-0000-000000000003','2027-02-01');
$q$, 'A23 a group cannot seat three delegates in one CLA');

-- =============================================================================
-- PHASE AND GOVERNANCE ASSERTIONS
-- =============================================================================

-- A24. No self-approval on a phase transition, even in a thin woreda office
SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.phase_event (group_id, from_phase, to_phase, submitted_by, decided_by, gate_snapshot)
    VALUES ('77777777-0000-0000-0000-000000000001','p1','p2',
            '44444444-0000-0000-0000-000000000001','44444444-0000-0000-0000-000000000001','{}'::jsonb);
$q$, 'A24 the submitter cannot also be the approver');

-- A25. A legitimate transition writes an immutable evidence snapshot
INSERT INTO wlt.phase_event (group_id, from_phase, to_phase, submitted_by, decided_by, gate_snapshot)
VALUES ('77777777-0000-0000-0000-000000000001','p1','p2',
        '44444444-0000-0000-0000-000000000001','44444444-0000-0000-0000-000000000002',
        '{"attendance_pct":100.0,"savings_compliance_pct":100.0,"meetings_held":12,"par30_pct":0}'::jsonb);

-- the service layer applies the decision to the group after writing the event
UPDATE wlt.group SET current_phase = 'p2'
 WHERE id = '77777777-0000-0000-0000-000000000001';

SELECT pg_temp.assert(
  (SELECT gate_snapshot ->> 'attendance_pct' FROM wlt.phase_event
    WHERE group_id = '77777777-0000-0000-0000-000000000001') = '100.0',
  'A25 the phase decision stored its evidence snapshot');

SELECT pg_temp.expect_fail($q$
    UPDATE wlt.phase_event SET gate_snapshot = '{}'::jsonb
     WHERE group_id = '77777777-0000-0000-0000-000000000001';
$q$, 'A26 a phase decision cannot be rewritten after the fact');

-- A27. Bylaw versioning: only one version in force at a time
SELECT pg_temp.expect_fail($q$
    INSERT INTO wlt.bylaw_version (group_id, version_no, effective_from, meeting_cadence, contribution_etb)
    VALUES ('77777777-0000-0000-0000-000000000001',2,'2026-06-01','weekly',30.00);
$q$, 'A27 close the current bylaw version before opening the next');

-- A28. Correct bylaw supersession works, and v1 is retained
UPDATE wlt.bylaw_version SET effective_to = '2026-06-01'
 WHERE id = '88888888-0000-0000-0000-000000000001';
INSERT INTO wlt.bylaw_version (group_id, version_no, effective_from, meeting_cadence, contribution_etb)
VALUES ('77777777-0000-0000-0000-000000000001',2,'2026-06-01','weekly',30.00);

SELECT pg_temp.assert(
  (SELECT contribution_etb FROM wlt.bylaw_version
    WHERE group_id = '77777777-0000-0000-0000-000000000001' AND effective_to IS NULL) = 30.00,
  'A28 bylaw v2 in force, v1 retained for historical compliance');

-- =============================================================================
-- REPORTING ASSERTIONS
-- =============================================================================

CALL wlt.refresh_reporting();

SELECT pg_temp.assert(
  (SELECT groups_short FROM wlt.mv_cla_readiness
    WHERE kebele_id = '33333333-0000-0000-0000-000000000002') = 7,
  'A29 CLA readiness shows 7 more P2+ groups needed against a threshold of 8');

SELECT pg_temp.assert(
  (SELECT endorsement_refused FROM wlt.mv_formation_attrition
    WHERE kebele_id = '33333333-0000-0000-0000-000000000002') = 1,
  'A30 a refused community endorsement is visible in formation attrition');

SELECT pg_temp.assert(
  (SELECT target_members FROM wlt.mv_enrolment_vs_allocation WHERE region = 'Amhara') = 1200,
  'A31 Amhara pre-pilot allocation is 1,200');

SELECT pg_temp.assert(
  (SELECT count(*) FROM wlt.mv_linkage_funnel WHERE type_code = 'savings_account') = 1,
  'A32 the linkage funnel picks up the savings account referral');

DO $$ BEGIN RAISE NOTICE E'\n==============================\nALL ASSERTIONS PASSED\n=============================='; END $$;
