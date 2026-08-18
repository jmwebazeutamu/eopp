-- =============================================================================
-- 001_reporting_schema.sql
--
-- Creates the reporting schema and the read-only role Metabase connects as.
-- Run once per environment, before 002-005.
--
-- The reporting layer is a separate schema on purpose. Metabase never sees the
-- application tables directly, so a Metabase misconfiguration cannot expose
-- per-youth PII, and the operational schema can be refactored without breaking
-- every saved question.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS rpt;

COMMENT ON SCHEMA rpt IS
  'Reporting layer. Read-only to Metabase. Refreshed by Celery beat; see 005_refresh.sql. '
  'Contains no youth names, phone numbers, or national IDs.';

-- -----------------------------------------------------------------------------
-- Read-only role for Metabase
-- -----------------------------------------------------------------------------
-- Replace the password before running. Store it in the deployment secret store,
-- not in this file and not in the Compose file.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'metabase_ro') THEN
    CREATE ROLE metabase_ro LOGIN PASSWORD 'CHANGE_ME_BEFORE_RUNNING';
  END IF;
END
$$;

REVOKE ALL ON SCHEMA public FROM metabase_ro;
GRANT USAGE ON SCHEMA rpt TO metabase_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA rpt TO metabase_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA rpt GRANT SELECT ON TABLES TO metabase_ro;

-- Belt and braces: metabase_ro must never reach the application tables.
-- Adjust the grantee list if the Django role is not named 'yep_app'.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM metabase_ro;

-- -----------------------------------------------------------------------------
-- Reporting parameters
-- -----------------------------------------------------------------------------
-- Every threshold the dashboards depend on lives here, in one row, editable
-- through the Django admin. Nothing below hard-codes a number that programme
-- management might want to change. See DEV_SPEC §11 open questions.

CREATE TABLE IF NOT EXISTS rpt.reporting_parameters (
    id                          integer PRIMARY KEY DEFAULT 1,
    -- small-numbers policy (README §8.1)
    suppress_below_n            integer NOT NULL DEFAULT 10,
    provisional_below_n         integer NOT NULL DEFAULT 30,
    -- funnel-plot control limits: 3.09 ≈ 99.8%, 1.96 ≈ 95%
    funnel_z                    numeric NOT NULL DEFAULT 3.09,
    -- referral operations
    confirmation_threshold_days integer NOT NULL DEFAULT 7,
    -- rolling window for the partner performance card
    partner_lookback_days       integer NOT NULL DEFAULT 180,
    stall_threshold_days        integer NOT NULL DEFAULT 30,
    -- a referral raised inside this window is not yet scoreable (README §8.2)
    referral_maturation_days    integer NOT NULL DEFAULT 30,
    -- OQ-13: a referral with no partner answer after this many days auto-fails
    -- with PARTNER_NON_RESPONSIVE. NULL disables the rule. Dev Spec §6.2 has no
    -- other exit from Pending Confirmation, so without this a stranded referral
    -- holds a parallel-cap slot and drags the loop-closure denominator forever.
    referral_abandonment_days   integer NULL DEFAULT NULL,
    -- caseload ceiling above which a case manager is flagged on the supervisor view
    caseload_ceiling            integer NOT NULL DEFAULT 120,
    -- Ethiopian youth definition; see README §6.2
    youth_age_min               integer NOT NULL DEFAULT 15,
    youth_age_max               integer NOT NULL DEFAULT 29,
    CONSTRAINT reporting_parameters_singleton CHECK (id = 1)
);

INSERT INTO rpt.reporting_parameters (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE rpt.reporting_parameters IS
  'Single-row configuration for the reporting layer. Edited through Django admin. '
  'Changing a value here changes every dashboard consistently; never hard-code these in a Metabase question.';

CREATE OR REPLACE FUNCTION rpt.param(p_name text)
RETURNS numeric
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v numeric;
BEGIN
    EXECUTE format('SELECT %I FROM rpt.reporting_parameters WHERE id = 1', p_name) INTO v;
    IF v IS NULL THEN
        RAISE EXCEPTION 'rpt.param: unknown or null parameter %', p_name;
    END IF;
    RETURN v;
END;
$$;

COMMENT ON FUNCTION rpt.param(text) IS
  'Reads one reporting parameter by name. Use in application code and ad-hoc queries. '
  'The materialised views in 003 use the inline (SELECT col FROM rpt.reporting_parameters WHERE id = 1) '
  'form instead, because rpt.param() is only STABLE and would be re-evaluated per row inside a view body. '
  'Both read the same single row; never hard-code a threshold in either place.';


-- -----------------------------------------------------------------------------
-- Taxonomy lookups
-- -----------------------------------------------------------------------------
-- DEV_SPEC §5.1 and §5.3. These exist so rpt.mv_referral_outcome_matrix can
-- render EVERY combination, including the empty ones. A plain GROUP BY omits
-- absent combinations, and the absent combinations are the finding on card PM-3
-- (training referrals that never convert to a job). That is also the whole
-- argument against a Sankey, which draws only the ribbons that exist.
--
-- DEV_SPEC §9 makes taxonomy configuration data owned by the system
-- administrator, not code. Once the Django `referrals` app owns these lists,
-- point the two views below at the Django tables and drop these.

CREATE TABLE IF NOT EXISTS rpt.ref_referral_category (
    code       text PRIMARY KEY,
    label      text NOT NULL,
    sort_order integer NOT NULL
);

INSERT INTO rpt.ref_referral_category (code, label, sort_order) VALUES
    ('training',              'Training',              1),
    ('employment_placement',  'Employment / placement',2),
    ('apprenticeship',        'Apprenticeship',        3),
    ('enterprise',            'Enterprise',            4),
    ('finance_access',        'Finance access',        5),
    ('market_linkage',        'Market linkage',        6),
    ('complementary_service', 'Complementary service', 7),
    ('coaching',              'Coaching',              8),
    ('other',                 'Other',                 9)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS rpt.ref_outcome_type (
    code       text PRIMARY KEY,
    label      text NOT NULL,
    sort_order integer NOT NULL
);

INSERT INTO rpt.ref_outcome_type (code, label, sort_order) VALUES
    ('service_uptake',            'Service uptake',            1),
    ('training_completion',       'Training completion',       2),
    ('job_placement',             'Job placement',             3),
    ('apprenticeship_start',      'Apprenticeship start',      4),
    ('enterprise_enrolment',      'Enterprise enrolment',      5),
    ('finance_access',            'Finance access',            6),
    ('market_linkage_established','Market linkage established',7),
    ('other',                     'Other',                     8)
ON CONFLICT (code) DO NOTHING;
