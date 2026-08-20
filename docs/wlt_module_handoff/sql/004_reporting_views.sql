-- =============================================================================
-- 004_reporting_views.sql
-- Extends the existing reporting layer. Materialized views follow the same
-- refresh orchestration as the youth-side views in 003_materialized_views.sql.
--
-- NOTE ON PAR30: this uses loan.due_on as the reference date, which is correct
-- for single-maturity loans. Once wlt.loan_schedule carries multiple
-- instalments, switch to the earliest unpaid instalment due_on. Flagged in the
-- punch list.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Helper: roster as it stood on a given date. Every indicator depends on this.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wlt.roster_on(p_group_id uuid, p_date date)
RETURNS TABLE (person_id uuid)
LANGUAGE sql STABLE AS $$
    SELECT m.person_id
      FROM wlt.group_membership m
     WHERE m.group_id = p_group_id
       AND m.joined_on <= p_date
       AND (m.exited_on IS NULL OR m.exited_on > p_date)
$$;

CREATE OR REPLACE FUNCTION wlt.policy_int(p_key text, p_default integer DEFAULT NULL)
RETURNS integer LANGUAGE sql STABLE AS $$
    SELECT coalesce(
        (SELECT (value #>> '{}')::integer
           FROM wlt.policy_parameter
          WHERE key = p_key
            AND scope_geo_id IS NULL
            AND effective_from <= current_date
            AND (effective_to IS NULL OR effective_to > current_date)
          ORDER BY effective_from DESC LIMIT 1),
        p_default)
$$;

-- ---------------------------------------------------------------------------
-- Current roster size
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW wlt.v_group_roster AS
SELECT g.id AS group_id,
       g.name,
       g.kebele_id,
       g.status,
       g.current_phase,
       count(m.id) FILTER (WHERE m.exited_on IS NULL) AS members_current
  FROM wlt.group g
  LEFT JOIN wlt.group_membership m ON m.group_id = g.id
 GROUP BY g.id;

-- ---------------------------------------------------------------------------
-- Attendance and savings compliance over the rolling window.
-- Denominator is the roster as it stood at each meeting, not the roster today.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_group_compliance AS
WITH windowed AS (
    SELECT m.*, row_number() OVER (PARTITION BY m.group_id ORDER BY m.held_on DESC) AS rn
      FROM wlt.meeting m
     WHERE m.status = 'closed'
), recent AS (
    SELECT * FROM windowed WHERE rn <= wlt.policy_int('indicator.rolling_meetings', 12)
), expected AS (
    -- denominator: the roster as it stood at EACH meeting, not the roster today
    SELECT r.group_id, r.id AS meeting_id, r.held_on,
           (SELECT count(*) FROM wlt.roster_on(r.group_id, r.held_on)) AS roster_n
      FROM recent r
), denom AS (
    -- computed before any join, so the join fan-out cannot inflate it
    SELECT group_id, sum(roster_n) AS expected_n FROM expected GROUP BY group_id
), pres AS (
    -- attendance_pct above 100 means attendance was recorded for someone who
    -- was off the roster on that date. Treat it as a data-quality alarm.
    SELECT e.group_id, count(*) AS present_n
      FROM expected e
      JOIN wlt.attendance a ON a.meeting_id = e.meeting_id
     WHERE a.status IN ('present','late')
     GROUP BY e.group_id
), sav AS (
    SELECT e.group_id, count(DISTINCT (l.meeting_id, l.person_id)) AS saved_n
      FROM expected e
      JOIN wlt.ledger_entry l ON l.meeting_id = e.meeting_id
     WHERE l.entry_type = 'savings' AND l.amount_etb > 0 AND l.person_id IS NOT NULL
     GROUP BY e.group_id
)
SELECT g.id AS group_id,
       g.kebele_id,
       g.current_phase,
       coalesce(pres.present_n, 0)                                      AS attendances_present,
       coalesce(d.expected_n, 0)                                        AS attendances_expected,
       CASE WHEN coalesce(d.expected_n,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(pres.present_n,0) / d.expected_n, 1) END
                                                                        AS attendance_pct,
       CASE WHEN coalesce(d.expected_n,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(sav.saved_n,0) / d.expected_n, 1) END
                                                                        AS savings_compliance_pct,
       (SELECT count(*) FROM wlt.meeting mm
         WHERE mm.group_id = g.id AND mm.status = 'closed')              AS meetings_held_total,
       (SELECT max(mm.held_on) FROM wlt.meeting mm
         WHERE mm.group_id = g.id AND mm.status = 'closed')              AS last_meeting_on
  FROM wlt.group g
  LEFT JOIN denom d   ON d.group_id = g.id
  LEFT JOIN pres      ON pres.group_id = g.id
  LEFT JOIN sav       ON sav.group_id = g.id;

CREATE UNIQUE INDEX ON wlt.mv_group_compliance (group_id);

-- ---------------------------------------------------------------------------
-- Financial position: fund, outstanding, PAR30, weeks of contribution
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_group_financials AS
WITH fund AS (
    SELECT group_id,
           sum(CASE WHEN entry_type IN ('savings','fine','loan_principal_repayment',
                                        'loan_charge_repayment') THEN amount_etb
                    WHEN entry_type = 'loan_disbursement' THEN -amount_etb
                    ELSE 0 END) AS fund_etb,
           sum(amount_etb) FILTER (WHERE entry_type = 'social_fund') AS social_fund_etb
      FROM wlt.ledger_entry
     GROUP BY group_id
), loans AS (
    SELECT l.group_id,
           l.id AS loan_id,
           l.due_on,
           l.principal_etb - coalesce((SELECT sum(principal_etb) FROM wlt.repayment r
                                        WHERE r.loan_id = l.id), 0) AS outstanding_etb
      FROM wlt.loan l
     WHERE l.status = 'disbursed'
), par AS (
    SELECT group_id,
           sum(outstanding_etb) AS outstanding_total,
           sum(outstanding_etb) FILTER (
               WHERE outstanding_etb > 0
                 AND due_on < current_date - wlt.policy_int('loan.default_days_past_due', 30)
           ) AS outstanding_at_risk
      FROM loans
     GROUP BY group_id
), contrib AS (
    SELECT g.id AS group_id,
           bv.contribution_etb,
           (SELECT count(*) FROM wlt.group_membership m
             WHERE m.group_id = g.id AND m.exited_on IS NULL) AS members_current
      FROM wlt.group g
      LEFT JOIN wlt.bylaw_version bv ON bv.group_id = g.id AND bv.effective_to IS NULL
)
SELECT g.id AS group_id,
       g.kebele_id,
       g.current_phase,
       coalesce(f.fund_etb, 0)                    AS fund_etb,
       coalesce(f.social_fund_etb, 0)             AS social_fund_etb,
       coalesce(p.outstanding_total, 0)           AS loans_outstanding_etb,
       CASE WHEN coalesce(p.outstanding_total,0) = 0 THEN 0
            ELSE round(100.0 * coalesce(p.outstanding_at_risk,0) / p.outstanding_total, 1)
       END                                        AS par30_pct,
       CASE WHEN coalesce(c.contribution_etb,0) = 0 OR coalesce(c.members_current,0) = 0 THEN NULL
            ELSE round(coalesce(f.fund_etb,0) / (c.contribution_etb * c.members_current), 1)
       END                                        AS fund_weeks_of_contribution,
       (SELECT count(DISTINCT cycle_batch) FROM wlt.loan l2
         WHERE l2.group_id = g.id AND l2.status = 'repaid') AS completed_loan_cycles
  FROM wlt.group g
  LEFT JOIN fund f    ON f.group_id = g.id
  LEFT JOIN par p     ON p.group_id = g.id
  LEFT JOIN contrib c ON c.group_id = g.id;

CREATE UNIQUE INDEX ON wlt.mv_group_financials (group_id);

-- ---------------------------------------------------------------------------
-- Groups by phase
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_groups_by_phase AS
SELECT g.kebele_id,
       g.status,
       g.current_phase,
       count(*) AS group_count,
       count(*) FILTER (WHERE g.status = 'active') AS active_count
  FROM wlt.group g
 GROUP BY g.kebele_id, g.status, g.current_phase;

-- ---------------------------------------------------------------------------
-- CLA readiness by kebele. Drives facilitator behaviour more than any report.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_cla_readiness AS
SELECT g.kebele_id,
       count(*) FILTER (WHERE g.current_phase IN ('p2','p3','p4')
                          AND g.status = 'active')                AS eligible_groups,
       wlt.policy_int('gate.cla.min_groups', 8)                   AS threshold,
       greatest(0, wlt.policy_int('gate.cla.min_groups', 8)
                   - count(*) FILTER (WHERE g.current_phase IN ('p2','p3','p4')
                                        AND g.status = 'active')) AS groups_short
  FROM wlt.group g
 GROUP BY g.kebele_id;

-- ---------------------------------------------------------------------------
-- Linkage funnel. Block reasons are the highest-value output for programme
-- learning: they say which gate is stopping groups.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_linkage_funnel AS
SELECT r.type_code,
       r.subject_type,
       r.status,
       count(*)                                       AS n,
       count(*) FILTER (WHERE r.status = 'blocked')   AS blocked_n,
       min(r.opened_on)                               AS earliest,
       max(r.opened_on)                               AS latest
  FROM referrals.referral r
 GROUP BY r.type_code, r.subject_type, r.status;

-- ---------------------------------------------------------------------------
-- Enrolment against the 5,000 ceiling
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_enrolment_vs_allocation AS
WITH enrolled AS (
    SELECT reg.id AS region_id,
           count(DISTINCT m.person_id) AS members_enrolled,
           count(DISTINCT g.id)        AS groups_formed,
           count(DISTINCT m.person_id) FILTER (
               WHERE bp.enrolment_route = 'facilitator')          AS via_exception_route
      FROM core.geography reg
      JOIN core.geography keb
        ON keb.id = reg.id OR keb.parent_id = reg.id
      JOIN wlt.group g            ON g.kebele_id = keb.id
      JOIN wlt.group_membership m ON m.group_id = g.id AND m.exited_on IS NULL
      LEFT JOIN wlt.beneficiary_profile bp ON bp.person_id = m.person_id
     WHERE reg.level = 'region'
     GROUP BY reg.id
)
SELECT a.geography_id,
       gg.name AS region,
       a.target_members,
       a.target_groups,
       coalesce(e.members_enrolled, 0) AS members_enrolled,
       coalesce(e.groups_formed, 0)    AS groups_formed,
       round(100.0 * coalesce(e.members_enrolled,0) / a.target_members, 1) AS pct_of_allocation,
       coalesce(e.via_exception_route, 0) AS via_exception_route,
       CASE WHEN coalesce(e.members_enrolled,0) = 0 THEN NULL
            ELSE round(100.0 * coalesce(e.via_exception_route,0)
                       / e.members_enrolled, 1) END AS exception_route_pct
  FROM wlt.enrolment_allocation a
  JOIN core.geography gg ON gg.id = a.geography_id
  LEFT JOIN enrolled e   ON e.region_id = a.geography_id;

-- ---------------------------------------------------------------------------
-- Cohort survival. The metric that says if the model works in Afar the way it
-- works in Amhara. Most important output for the pilot research.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_cohort_survival AS
SELECT date_trunc('month', g.activated_on)::date AS cohort_month,
       g.kebele_id,
       count(*)                                                     AS cohort_size,
       count(*) FILTER (WHERE g.status = 'active')                  AS still_active,
       count(*) FILTER (WHERE g.status IN ('dormant','at_risk'))    AS faltering,
       count(*) FILTER (WHERE g.status IN ('dissolved','split','merged')) AS ended,
       round(avg(current_date - g.activated_on))                    AS avg_days_since_activation
  FROM wlt.group g
 WHERE g.activated_on IS NOT NULL
 GROUP BY 1, 2;

-- ---------------------------------------------------------------------------
-- Abandoned formations. A kebele with three abandoned constitutions is a
-- mobilisation problem, and it is invisible if only successes are reported.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW wlt.mv_formation_attrition AS
SELECT me.kebele_id,
       count(DISTINCT me.id)                                        AS mobilisation_events,
       count(DISTINCT me.id) FILTER (WHERE NOT me.endorsement_obtained) AS endorsement_refused,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'draft')       AS drafts_open,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'abandoned')   AS abandoned,
       count(DISTINCT g.id) FILTER (WHERE g.status = 'constituted') AS constituted_not_active,
       count(DISTINCT g.id) FILTER (WHERE g.activated_on IS NOT NULL) AS activated
  FROM wlt.mobilisation_event me
  LEFT JOIN wlt.group g ON g.mobilisation_event_id = me.id
 GROUP BY me.kebele_id;

-- ---------------------------------------------------------------------------
-- Refresh. Wire into the existing 005_refresh.sql orchestration.
-- ---------------------------------------------------------------------------
-- Call with:  CALL wlt.refresh_reporting();
--
-- CONCURRENTLY is used for the two views the facilitator UI reads, so a refresh
-- never blocks a read. It cannot run inside a transaction block, hence the
-- COMMIT between statements; that is legal in a PROCEDURE, not in a FUNCTION.
CREATE OR REPLACE PROCEDURE wlt.refresh_reporting()
LANGUAGE plpgsql AS $$
BEGIN
    COMMIT;
    REFRESH MATERIALIZED VIEW CONCURRENTLY wlt.mv_group_compliance;
    COMMIT;
    REFRESH MATERIALIZED VIEW CONCURRENTLY wlt.mv_group_financials;
    COMMIT;
    REFRESH MATERIALIZED VIEW wlt.mv_groups_by_phase;
    REFRESH MATERIALIZED VIEW wlt.mv_cla_readiness;
    REFRESH MATERIALIZED VIEW wlt.mv_linkage_funnel;
    REFRESH MATERIALIZED VIEW wlt.mv_enrolment_vs_allocation;
    REFRESH MATERIALIZED VIEW wlt.mv_cohort_survival;
    REFRESH MATERIALIZED VIEW wlt.mv_formation_attrition;
    COMMIT;
END $$;
