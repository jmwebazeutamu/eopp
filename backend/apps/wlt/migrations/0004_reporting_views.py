"""WLT reporting layer — the eight views of the handoff's `sql/004`.

Adapted rather than transcribed, because `sql/000_core_stubs.sql` models a core
platform this one is not: it assumes a `core.person` with a kebele FK, a
`referrals.referral` with a `type_code` and a provider, and lowercase status
codes. The Django models are the source of truth, so the shapes here are the
handoff's and the columns are this database's.

Four deliberate departures from `sql/004`, each of which changes a number:

* **PAR30 uses the earliest unpaid instalment**, not `loan.due_on`. The bundle
  flags this as a known limitation of its own view and puts the fix in its
  punch list; the Python indicator service already does it this way, and two
  definitions of PAR30 in one system is exactly what `DEFINITIONS.md` forbids.
* **Fund adequacy is converted to weeks by the group's own cadence.** The bundle
  divides the fund by one period's contributions and labels the result weeks,
  which for a monthly group reports months. A threshold stated in weeks has to
  mean weeks for every group.
* **A completed loan cycle requires every loan in the batch to be settled.** The
  bundle counts distinct `cycle_batch` among repaid loans, which credits a cycle
  whose other loans are still outstanding.
* **The linkage funnel is a union of two tables.** Gated linkage lives in
  `wlt_servicelinkage` and plain service referrals ride `referrals_referral`;
  the funnel reports both, with a `source` column saying which, so the block
  reasons stay in one place.

`refresh_wlt_reporting()` is called by the Celery task and by the management
command. Two views refresh CONCURRENTLY because the facilitator UI reads them
and a refresh must never block a read; that needs a unique index on each, which
is why both carry one.
"""

from django.db import migrations

HELPERS = """
-- The roster as it stood on a date. Every historical indicator depends on it.
CREATE OR REPLACE FUNCTION wlt_roster_on(p_group_id uuid, p_date date)
RETURNS TABLE (person_id uuid)
LANGUAGE sql STABLE AS $$
    SELECT m.person_id
      FROM wlt_groupmembership m
     WHERE m.group_id = p_group_id
       AND m.joined_on <= p_date
       AND (m.exited_on IS NULL OR m.exited_on > p_date)
$$;

-- The global value of a policy parameter, for the reporting layer. Geography
-- overrides are resolved in Python (`wlt.policy.PolicySet`); a view that
-- aggregates across woredas has no single place to resolve them against, so it
-- reports against the global rule and says so.
CREATE OR REPLACE FUNCTION wlt_policy_int(p_key text, p_default integer DEFAULT NULL)
RETURNS integer LANGUAGE sql STABLE AS $$
    SELECT coalesce(
        (SELECT (value #>> '{}')::integer
           FROM wlt_policyparameter
          WHERE key = p_key
            AND scope_location_id IS NULL
            AND effective_from <= current_date
            AND (effective_to IS NULL OR effective_to > current_date)
          ORDER BY effective_from DESC LIMIT 1),
        p_default)
$$;

CREATE OR REPLACE FUNCTION wlt_cadence_days(p_cadence text)
RETURNS integer LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_cadence WHEN 'WEEKLY' THEN 7 WHEN 'FORTNIGHTLY' THEN 14 WHEN 'MONTHLY' THEN 30 ELSE 7 END
$$;

CREATE OR REPLACE VIEW wlt_v_group_roster AS
SELECT g.id AS group_id,
       g.name,
       g.kebele_id,
       g.status,
       g.current_phase,
       count(m.id) FILTER (WHERE m.exited_on IS NULL) AS members_current
  FROM wlt_group g
  LEFT JOIN wlt_groupmembership m ON m.group_id = g.id
 GROUP BY g.id;
"""

HELPERS_REVERSE = """
DROP VIEW IF EXISTS wlt_v_group_roster;
DROP FUNCTION IF EXISTS wlt_cadence_days(text);
DROP FUNCTION IF EXISTS wlt_policy_int(text, integer);
DROP FUNCTION IF EXISTS wlt_roster_on(uuid, date);
"""

COMPLIANCE = """
CREATE MATERIALIZED VIEW wlt_mv_group_compliance AS
WITH windowed AS (
    SELECT m.*, row_number() OVER (PARTITION BY m.group_id ORDER BY m.held_on DESC) AS rn
      FROM wlt_meeting m
     WHERE m.status = 'CLOSED'
), recent AS (
    SELECT * FROM windowed WHERE rn <= wlt_policy_int('indicator.rolling_meetings', 12)
), expected AS (
    -- The denominator is the roster as it stood at EACH meeting, not the roster
    -- today. A woman who joined in month 6 must not make months 1 to 5 look
    -- worse, and a woman who left must not make them look better.
    SELECT r.group_id, r.id AS meeting_id, r.held_on,
           (SELECT count(*) FROM wlt_roster_on(r.group_id, r.held_on)) AS roster_n
      FROM recent r
), denom AS (
    -- Summed before any join, so join fan-out cannot inflate it.
    SELECT group_id, sum(roster_n) AS expected_n FROM expected GROUP BY group_id
), pres AS (
    SELECT e.group_id, count(*) AS present_n
      FROM expected e
      JOIN wlt_attendance a ON a.meeting_id = e.meeting_id
     WHERE a.status IN ('PRESENT','LATE')
     GROUP BY e.group_id
), sav AS (
    SELECT e.group_id, count(DISTINCT (l.meeting_id, l.person_id)) AS saved_n
      FROM expected e
      JOIN wlt_ledgerentry l ON l.meeting_id = e.meeting_id
     WHERE l.entry_type = 'SAVINGS' AND l.amount_etb > 0 AND l.person_id IS NOT NULL
     GROUP BY e.group_id
)
SELECT g.id AS group_id,
       g.kebele_id,
       g.current_phase,
       coalesce(pres.present_n, 0)  AS attendances_present,
       coalesce(d.expected_n, 0)    AS attendances_expected,
       -- Above 100% is a data-quality alarm, not a rounding artefact: it means
       -- attendance was recorded for somebody off the roster that day. Reported
       -- as it comes out, never clamped.
       CASE WHEN coalesce(d.expected_n,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(pres.present_n,0) / d.expected_n, 1) END AS attendance_pct,
       CASE WHEN coalesce(d.expected_n,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(sav.saved_n,0) / d.expected_n, 1) END    AS savings_contribution_pct,
       (SELECT count(*) FROM wlt_meeting mm WHERE mm.group_id = g.id AND mm.status = 'CLOSED')
                                    AS meetings_held_total,
       (SELECT max(mm.held_on) FROM wlt_meeting mm WHERE mm.group_id = g.id AND mm.status = 'CLOSED')
                                    AS last_meeting_on
  FROM wlt_group g
  LEFT JOIN denom d ON d.group_id = g.id
  LEFT JOIN pres    ON pres.group_id = g.id
  LEFT JOIN sav     ON sav.group_id = g.id;

CREATE UNIQUE INDEX wlt_mv_group_compliance_pk ON wlt_mv_group_compliance (group_id);
"""

FINANCIALS = """
CREATE MATERIALIZED VIEW wlt_mv_group_financials AS
WITH fund AS (
    SELECT group_id,
           sum(CASE WHEN entry_type IN ('SAVINGS','FINE','LOAN_PRINCIPAL_REPAYMENT','LOAN_CHARGE_REPAYMENT')
                        THEN amount_etb
                    WHEN entry_type = 'LOAN_DISBURSEMENT' THEN -amount_etb
                    ELSE 0 END)                                        AS fund_etb,
           sum(amount_etb) FILTER (WHERE entry_type = 'SOCIAL_FUND')   AS social_fund_etb,
           sum(CASE WHEN entry_type = 'BANK_DEPOSIT' THEN amount_etb
                    WHEN entry_type = 'BANK_WITHDRAWAL' THEN -amount_etb
                    ELSE 0 END)                                        AS bank_balance_etb
      FROM wlt_ledgerentry
     GROUP BY group_id
), loans AS (
    SELECT l.group_id,
           l.id AS loan_id,
           l.principal_etb - coalesce(paid.principal, 0) AS outstanding_etb,
           -- The earliest instalment the repayments have not yet covered, or
           -- the loan's own due date when it carries no schedule. The handoff's
           -- own punch list asks for this; `services.indicators` already does it.
           coalesce(
               (SELECT min(t.due_on)
                  FROM (SELECT s.due_on,
                               sum(s.principal_due_etb) OVER (ORDER BY s.instalment_no) AS cumulative
                          FROM wlt_loanschedule s WHERE s.loan_id = l.id) t
                 WHERE t.cumulative > coalesce(paid.principal, 0)),
               l.due_on) AS reference_due_on
      FROM wlt_loan l
      LEFT JOIN LATERAL (
          SELECT sum(r.principal_etb) AS principal FROM wlt_repayment r WHERE r.loan_id = l.id
      ) paid ON true
     WHERE l.status = 'DISBURSED'
), par AS (
    SELECT group_id,
           sum(outstanding_etb) AS outstanding_total,
           sum(outstanding_etb) FILTER (
               WHERE outstanding_etb > 0
                 AND reference_due_on < current_date - wlt_policy_int('loan.default_days_past_due', 30)
           ) AS outstanding_at_risk
      FROM loans
     GROUP BY group_id
), cycles AS (
    -- A cycle completes when every loan in it is settled. Counting distinct
    -- batches among repaid loans would credit a cycle whose other loans are
    -- still outstanding.
    SELECT group_id, count(*) AS completed_cycles FROM (
        SELECT group_id, cycle_batch
          FROM wlt_loan
         GROUP BY group_id, cycle_batch
        HAVING bool_and(status IN ('REPAID','WRITTEN_OFF'))
    ) settled GROUP BY group_id
), contrib AS (
    SELECT g.id AS group_id,
           bv.contribution_etb,
           wlt_cadence_days(bv.meeting_cadence) AS cadence_days,
           (SELECT count(*) FROM wlt_groupmembership m
             WHERE m.group_id = g.id AND m.exited_on IS NULL) AS members_current
      FROM wlt_group g
      LEFT JOIN wlt_bylawversion bv ON bv.group_id = g.id AND bv.effective_to IS NULL
)
SELECT g.id AS group_id,
       g.kebele_id,
       g.current_phase,
       coalesce(f.fund_etb, 0)           AS fund_etb,
       coalesce(f.social_fund_etb, 0)    AS social_fund_etb,
       coalesce(f.bank_balance_etb, 0)   AS bank_balance_etb,
       coalesce(p.outstanding_total, 0)  AS loans_outstanding_etb,
       CASE WHEN coalesce(p.outstanding_total,0) = 0 THEN 0
            ELSE round(100.0 * coalesce(p.outstanding_at_risk,0) / p.outstanding_total, 1)
       END                               AS par30_pct,
       -- Weeks, converted by the group's own cadence, so a weekly and a monthly
       -- group can be read against the same threshold.
       CASE WHEN coalesce(c.contribution_etb,0) = 0 OR coalesce(c.members_current,0) = 0 THEN NULL
            ELSE round(
                (coalesce(f.fund_etb,0) / (c.contribution_etb * c.members_current))
                * c.cadence_days / 7.0, 1)
       END                               AS fund_weeks_of_contribution,
       coalesce(cy.completed_cycles, 0)  AS completed_loan_cycles
  FROM wlt_group g
  LEFT JOIN fund f    ON f.group_id = g.id
  LEFT JOIN par p     ON p.group_id = g.id
  LEFT JOIN cycles cy ON cy.group_id = g.id
  LEFT JOIN contrib c ON c.group_id = g.id;

CREATE UNIQUE INDEX wlt_mv_group_financials_pk ON wlt_mv_group_financials (group_id);
"""

AGGREGATES = """
CREATE MATERIALIZED VIEW wlt_mv_groups_by_phase AS
SELECT g.kebele_id,
       g.status,
       g.current_phase,
       count(*)                                    AS group_count,
       count(*) FILTER (WHERE g.status = 'ACTIVE') AS active_count
  FROM wlt_group g
 GROUP BY g.kebele_id, g.status, g.current_phase;

-- CLA readiness by kebele. This screen drives facilitator behaviour more than
-- any report in the module: "two more groups at P2 and this kebele can form a
-- CLA" is actionable in a way a phase distribution is not.
CREATE MATERIALIZED VIEW wlt_mv_cla_readiness AS
SELECT g.kebele_id,
       count(*) FILTER (WHERE g.current_phase IN ('P2','P3','P4') AND g.status = 'ACTIVE') AS eligible_groups,
       wlt_policy_int('gate.cla.min_groups', 8) AS threshold,
       greatest(0, wlt_policy_int('gate.cla.min_groups', 8)
                   - count(*) FILTER (WHERE g.current_phase IN ('P2','P3','P4')
                                        AND g.status = 'ACTIVE'))                          AS groups_short
  FROM wlt_group g
 GROUP BY g.kebele_id;

-- The linkage funnel, over both surfaces. Block reasons are the highest-value
-- output in the module: they say which gate is stopping groups, which is the
-- evidence for adjusting a threshold rather than guessing at one.
CREATE MATERIALIZED VIEW wlt_mv_linkage_funnel AS
SELECT 'linkage'::text            AS source,
       l.linkage_type_id          AS type_code,
       l.subject_type,
       l.status,
       count(*)                   AS n,
       min(l.opened_on)           AS earliest,
       max(l.opened_on)           AS latest
  FROM wlt_servicelinkage l
 GROUP BY l.linkage_type_id, l.subject_type, l.status
UNION ALL
SELECT 'referral'::text,
       r.referral_category_id,
       r.subject_type,
       r.status,
       count(*),
       min(r.initiated_date),
       max(r.initiated_date)
  FROM referrals_referral r
 WHERE r.subject_type <> 'CASE'
 GROUP BY r.referral_category_id, r.subject_type, r.status;

-- What the funnel cannot say in a GROUP BY: which condition is doing the
-- blocking. One row per reason per type.
CREATE MATERIALIZED VIEW wlt_mv_linkage_block_reasons AS
SELECT l.linkage_type_id AS type_code,
       reason,
       count(*) AS n
  FROM wlt_servicelinkage l
  CROSS JOIN LATERAL jsonb_array_elements_text(
      CASE WHEN jsonb_typeof(l.block_reasons) = 'array' THEN l.block_reasons ELSE '[]'::jsonb END
  ) AS reason
 WHERE l.status = 'BLOCKED'
 GROUP BY l.linkage_type_id, reason;

-- Progress against the 5,000 ceiling, plus the exception-route share. Past 10%
-- the extract is the problem and should be fixed rather than worked around.
CREATE MATERIALIZED VIEW wlt_mv_enrolment_vs_allocation AS
WITH enrolled AS (
    SELECT reg.id AS region_id,
           count(DISTINCT m.person_id) AS members_enrolled,
           count(DISTINCT g.id)        AS groups_formed,
           count(DISTINCT m.person_id) FILTER (WHERE bp.enrolment_route = 'FACILITATOR') AS via_exception_route
      FROM locations_location reg
      JOIN locations_location zone   ON zone.parent_id = reg.id
      JOIN locations_location woreda ON woreda.parent_id = zone.id
      JOIN locations_location keb    ON keb.parent_id = woreda.id
      JOIN wlt_group g               ON g.kebele_id = keb.id
      JOIN wlt_groupmembership m     ON m.group_id = g.id AND m.exited_on IS NULL
      LEFT JOIN wlt_beneficiaryprofile bp ON bp.person_id = m.person_id
     WHERE reg.level = 'REGION'
     GROUP BY reg.id
)
SELECT a.location_id AS geography_id,
       gg.name       AS region,
       a.target_members,
       a.target_groups,
       coalesce(e.members_enrolled, 0) AS members_enrolled,
       coalesce(e.groups_formed, 0)    AS groups_formed,
       round(100.0 * coalesce(e.members_enrolled,0) / a.target_members, 1) AS pct_of_allocation,
       coalesce(e.via_exception_route, 0) AS via_exception_route,
       CASE WHEN coalesce(e.members_enrolled,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(e.via_exception_route,0) / e.members_enrolled, 1)
       END AS exception_route_pct
  FROM wlt_enrolmentallocation a
  JOIN locations_location gg ON gg.id = a.location_id
  LEFT JOIN enrolled e ON e.region_id = a.location_id;

-- Whether the model works in Afar the way it works in Amhara. The most
-- important output for the pilot's research question.
CREATE MATERIALIZED VIEW wlt_mv_cohort_survival AS
SELECT date_trunc('month', g.activated_on)::date AS cohort_month,
       g.kebele_id,
       count(*)                                                            AS cohort_size,
       count(*) FILTER (WHERE g.status = 'ACTIVE')                         AS still_active,
       count(*) FILTER (WHERE g.status IN ('DORMANT','AT_RISK'))           AS faltering,
       count(*) FILTER (WHERE g.status IN ('DISSOLVED','SPLIT','MERGED'))  AS ended,
       round(avg(current_date - g.activated_on))                           AS avg_days_since_activation
  FROM wlt_group g
 WHERE g.activated_on IS NOT NULL
 GROUP BY 1, 2;

-- A kebele with three abandoned constitutions has a mobilisation problem, and
-- it is invisible if only successes are reported.
CREATE MATERIALIZED VIEW wlt_mv_formation_attrition AS
SELECT me.kebele_id,
       count(DISTINCT me.id)                                              AS mobilisation_events,
       count(DISTINCT me.id) FILTER (WHERE NOT me.endorsement_obtained)   AS endorsement_refused,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'DRAFT')             AS drafts_open,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'ABANDONED')         AS abandoned,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'CONSTITUTED')       AS constituted_not_active,
       count(DISTINCT g.id) FILTER (WHERE g.activated_on IS NOT NULL)     AS activated
  FROM wlt_mobilisationevent me
  LEFT JOIN wlt_group g ON g.mobilisation_event_id = me.id
 GROUP BY me.kebele_id;
"""

AGGREGATES_REVERSE = """
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_formation_attrition;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_cohort_survival;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_enrolment_vs_allocation;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_linkage_block_reasons;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_linkage_funnel;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_cla_readiness;
DROP MATERIALIZED VIEW IF EXISTS wlt_mv_groups_by_phase;
"""

REFRESH = """
-- CONCURRENTLY on the two the facilitator UI reads, so a refresh never blocks a
-- read. It cannot run inside a transaction block, hence the COMMITs — legal in a
-- PROCEDURE, not in a FUNCTION.
CREATE OR REPLACE PROCEDURE wlt_refresh_reporting()
LANGUAGE plpgsql AS $$
BEGIN
    COMMIT;
    REFRESH MATERIALIZED VIEW CONCURRENTLY wlt_mv_group_compliance;
    COMMIT;
    REFRESH MATERIALIZED VIEW CONCURRENTLY wlt_mv_group_financials;
    COMMIT;
    REFRESH MATERIALIZED VIEW wlt_mv_groups_by_phase;
    REFRESH MATERIALIZED VIEW wlt_mv_cla_readiness;
    REFRESH MATERIALIZED VIEW wlt_mv_linkage_funnel;
    REFRESH MATERIALIZED VIEW wlt_mv_linkage_block_reasons;
    REFRESH MATERIALIZED VIEW wlt_mv_enrolment_vs_allocation;
    REFRESH MATERIALIZED VIEW wlt_mv_cohort_survival;
    REFRESH MATERIALIZED VIEW wlt_mv_formation_attrition;
    COMMIT;
END $$;
"""


class Migration(migrations.Migration):

    dependencies = [("wlt", "0003_remove_group_wlt_phase_only_when_operating_and_more"), ("referrals", "0008_backfill_allowed_subject_types")]

    operations = [
        migrations.RunSQL(HELPERS, HELPERS_REVERSE),
        migrations.RunSQL(COMPLIANCE, "DROP MATERIALIZED VIEW IF EXISTS wlt_mv_group_compliance;"),
        migrations.RunSQL(FINANCIALS, "DROP MATERIALIZED VIEW IF EXISTS wlt_mv_group_financials;"),
        migrations.RunSQL(AGGREGATES, AGGREGATES_REVERSE),
        migrations.RunSQL(REFRESH, "DROP PROCEDURE IF EXISTS wlt_refresh_reporting();"),
    ]
