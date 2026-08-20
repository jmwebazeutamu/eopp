-- =============================================================================
-- 003_policy_seed.sql
-- Seed policy parameters, referral types, and pre-pilot allocations.
--
-- Values marked NEEDS FSCO are placeholders taken from the handbook where it is
-- self-consistent, and from the more conservative reading where it is not.
-- Do not treat them as agreed. See OPEN_QUESTIONS.md.
-- =============================================================================

-- Geography for the five pre-pilot regions
INSERT INTO core.geography (id, level, name, code) VALUES
  ('11111111-0000-0000-0000-000000000001','region','Somali','ET-SO'),
  ('11111111-0000-0000-0000-000000000002','region','Amhara','ET-AM'),
  ('11111111-0000-0000-0000-000000000003','region','Afar','ET-AF'),
  ('11111111-0000-0000-0000-000000000004','region','Central Ethiopia','ET-CE'),
  ('11111111-0000-0000-0000-000000000005','region','Dire Dawa','ET-DD');

-- Pre-pilot allocation. Handbook section 3.1. Hard ceiling of 5,000.
INSERT INTO wlt.enrolment_allocation (geography_id, phase_label, target_members, target_groups, effective_from) VALUES
  ('11111111-0000-0000-0000-000000000001','pre_pilot',1600,80,'2026-01-01'),
  ('11111111-0000-0000-0000-000000000002','pre_pilot',1200,60,'2026-01-01'),
  ('11111111-0000-0000-0000-000000000003','pre_pilot',1000,50,'2026-01-01'),
  ('11111111-0000-0000-0000-000000000004','pre_pilot', 908,45,'2026-01-01'),
  ('11111111-0000-0000-0000-000000000005','pre_pilot', 292,15,'2026-01-01');

-- ---------------------------------------------------------------------------
-- Policy parameters. Global scope. Region overrides are inserted with a
-- scope_geo_id and take precedence.
-- ---------------------------------------------------------------------------
INSERT INTO wlt.policy_parameter (key, value, effective_from, note) VALUES

-- Group composition. Handbook states 15-20 (S2), 15-25 (S3.4) and 20 (target
-- table). Outer range is the hard block, inner range the soft warning.
 ('group.size.hard_min',            '15'::jsonb,   '2026-01-01', 'NEEDS FSCO: handbook inconsistent'),
 ('group.size.hard_max',            '25'::jsonb,   '2026-01-01', 'NEEDS FSCO: handbook inconsistent'),
 ('group.size.warn_min',            '18'::jsonb,   '2026-01-01', 'soft warning only'),
 ('group.size.warn_max',            '22'::jsonb,   '2026-01-01', 'soft warning only'),

-- Formation lifecycle
 ('formation.draft_expiry_days',        '60'::jsonb, '2026-01-01', ''),
 ('formation.constituted_expiry_days',  '30'::jsonb, '2026-01-01', 'never held a savings meeting'),
 ('formation.event_expiry_days',        '90'::jsonb, '2026-01-01', 'CLA/federation formation events'),

-- Phase 1 exit gate
 ('gate.p1.meeting_adherence_pct',  '90'::jsonb,   '2026-01-01', 'against the group own bylaw cadence'),
 ('gate.p1.attendance_pct',         '80'::jsonb,   '2026-01-01', 'handbook S4 phase 1'),
 ('gate.p1.savings_compliance_pct', '80'::jsonb,   '2026-01-01', 'NEEDS FSCO: undefined in handbook'),
 ('gate.p1.min_savings_meetings',   '10'::jsonb,   '2026-01-01', 'handbook S3.5 lending gate'),
 ('gate.p1.max_par30_pct',          '0'::jsonb,    '2026-01-01', ''),

-- Phase 2 exit gate
 ('gate.p2.fund_adequacy_weeks',    '12'::jsonb,   '2026-01-01',
  'REPLACES handbook "2-3 months of contributions", which sits below the natural accumulation floor'),
 ('gate.p2.completed_loan_cycles',  '1'::jsonb,    '2026-01-01', ''),
 ('gate.p2.max_par30_pct',          '0'::jsonb,    '2026-01-01', ''),
 ('gate.p2.social_fund_required',   'true'::jsonb, '2026-01-01', 'NEEDS FSCO: social fund is never defined'),
 ('gate.p2.min_weeks_since_p1',     '52'::jsonb,   '2026-01-01', ''),

-- CLA formation. Handbook says 8 in the text and "around 6" in the indicator.
-- Kindernothilfe source says 8-10. Seeded at 8, the conservative reading.
 ('gate.cla.min_groups',            '8'::jsonb,    '2026-01-01', 'NEEDS FSCO: handbook says 8 and 6'),
 ('gate.cla.delegates_per_group',   '2'::jsonb,    '2026-01-01', ''),

-- Federation. Handbook says "5-10 CLAs" in text and "at least 10" in indicator.
 ('gate.federation.min_clas',       '10'::jsonb,   '2026-01-01', 'NEEDS FSCO: handbook says 5-10 and 10+'),
 ('gate.federation.min_cla_months', '12'::jsonb,   '2026-01-01', ''),

-- Credit facility. Deliberately restrictive.
 ('gate.credit.min_phase',          '"p4"'::jsonb, '2026-01-01', ''),
 ('gate.credit.allow_group_subject','false'::jsonb,'2026-01-01', 'block group-level credit in the pilot'),
 ('gate.credit.savings_account_months','12'::jsonb,'2026-01-01', ''),
 ('gate.credit.min_completed_cycles','2'::jsonb,   '2026-01-01', ''),
 ('gate.credit.max_leverage_ratio', '1.0'::jsonb,  '2026-01-01', 'facility <= 1.0 x own funds'),

-- Risk and dormancy
 ('risk.dormant_cadence_multiple',  '3'::jsonb,    '2026-01-01', ''),
 ('risk.dormant_floor_days',        '60'::jsonb,   '2026-01-01', ''),
 ('risk.attendance_floor_pct',      '60'::jsonb,   '2026-01-01', ''),
 ('risk.par30_ceiling_pct',         '20'::jsonb,   '2026-01-01', ''),

-- Loan discipline. Handbook S3.5.
 ('loan.default_days_past_due',     '30'::jsonb,   '2026-01-01', 'NEEDS FSCO: standard MFI convention'),
 ('loan.delinquent_days_past_due',  '1'::jsonb,    '2026-01-01', ''),

-- Indicator windows
 ('indicator.rolling_meetings',     '12'::jsonb,   '2026-01-01', ''),

-- Enrolment controls
 ('enrolment.allocation_warn_pct',  '90'::jsonb,   '2026-01-01', ''),
 ('enrolment.exception_route_alert_pct','10'::jsonb,'2026-01-01',
  'if facilitator-route enrolments exceed this share in a woreda, the extract is the problem'),

-- Meeting content. Handbook S3.6 requires 15-30 minutes of social discussion.
 ('meeting.social_minutes_min',     '15'::jsonb,   '2026-01-01', '');

-- ---------------------------------------------------------------------------
-- Referral types. This is where service linkage becomes configuration.
-- allowed_subject_types is the safeguarding control.
-- ---------------------------------------------------------------------------
INSERT INTO referrals.referral_type (code, label, allowed_subject_types, restricted, approval_chain) VALUES
 ('savings_account',        'Group savings account',   ARRAY['group','cla','federation'], false,
    ARRAY['woreda_fsco']),
 ('market_offtake',         'Market / offtake agreement', ARRAY['group','cla','federation'], false,
    ARRAY['woreda_fsco']),
 ('service_referral',       'Service referral',        ARRAY['person','group'], false,
    ARRAY[]::text[]),
 ('cooperative_membership', 'Cooperative membership',  ARRAY['group','cla'], false,
    ARRAY['woreda_fsco','region_fsco']),
 ('cooperative_registration','Cooperative registration', ARRAY['federation'], false,
    ARRAY['region_fsco','federal_fsco']),
 ('credit_facility',        'External credit facility', ARRAY['cla','federation'], false,
    ARRAY['woreda_fsco','region_fsco','federal_fsco']),

-- Protection: person only, restricted store, never on a group timeline.
-- Handbook S3.6 puts GBV on the meeting agenda. This type is how that stays safe.
 ('protection_referral',    'Protection / GBV referral', ARRAY['person'], true,
    ARRAY['woreda_fsco']);

INSERT INTO referrals.provider (id, name, provider_type, status) VALUES
 ('22222222-0000-0000-0000-000000000001','Example Rural Bank','bank','active'),
 ('22222222-0000-0000-0000-000000000002','Example RUSACCO','rusacco','active'),
 ('22222222-0000-0000-0000-000000000003','Example MFI','mfi','active');
