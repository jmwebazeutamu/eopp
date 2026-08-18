-- =============================================================================
-- 003_materialized_views.sql
--
-- The reporting layer proper. Every Metabase question reads from these; none
-- reads an application table directly.
--
-- WHY MATERIALISED, NOT VIEWS:
-- DHIS2 documents this exact failure at scale: program indicators computed
-- on demand mean every dashboard load triggers a full join across event tables,
-- and their fix is the tracker-to-aggregate pipeline. Same principle here. A
-- supervisor on 3G opening a six-card dashboard is six independent query
-- round-trips; each one must hit a pre-aggregated row, not a five-CTE join.
--
-- Refresh cadence is set in 005_refresh.sql. Ordering matters: dim_youth and
-- fct_referral feed everything else, so refresh them first.
-- =============================================================================


-- =============================================================================
-- LAYER 1: dimensional and fact bases
-- =============================================================================

-- -----------------------------------------------------------------------------
-- rpt.dim_youth
-- -----------------------------------------------------------------------------
-- One row per registered youth, joined to the case and current pathway.
--
-- CONTAINS NO PII. No full_name, no phone_number, no national_or_kebele_id.
-- The BI layer never needs to identify an individual; the case management app
-- does, and it enforces caseload scoping in the Django ORM. If someone asks for
-- names in Metabase, the answer is no: that is what the case manager view is for.

DROP MATERIALIZED VIEW IF EXISTS rpt.dim_youth CASCADE;
CREATE MATERIALIZED VIEW rpt.dim_youth AS
SELECT
    y.youth_id,
    c.case_id,
    c.case_status,
    c.case_manager_id,
    y.region,
    y.zone,
    c.woreda,
    y.sex,
    rpt.age_band(y.date_of_birth)                       AS age_band,
    (rpt.age_band(y.date_of_birth) IN ('15-17','18-24','25-29')) AS is_youth_eth,  -- 15-29
    y.psnp_status,
    y.psnp_client_category,
    y.education_level,
    y.disability_status,
    (y.disability_status IS NOT NULL
     AND y.disability_status NOT IN ('none','None','no','No'))  AS has_disability,
    y.registration_date,
    c.opened_date,
    c.closed_date,
    c.exit_reason,
    c.last_activity_date,
    pa.selected_pathway                                 AS current_pathway,
    pr.priority_flag,
    pr.assessed_date                                    AS profiled_date,
    -- data-quality flags, surfaced on the supervisor dashboard
    (y.phone_number IS NULL OR y.phone_number = '')     AS missing_phone,
    (pr.profiling_id IS NULL)                           AS missing_profile,
    (y.consent_given IS FALSE OR y.consent_date IS NULL) AS missing_consent
FROM youth_youth y
JOIN cases_case c
  ON c.youth_id = y.youth_id
LEFT JOIN cases_pathwayassignment pa
  ON pa.case_id = c.case_id AND pa.is_current
LEFT JOIN LATERAL (
    -- latest profiling record is the current one (DEV_SPEC §3)
    SELECT p.profiling_id, p.priority_flag, p.assessed_date
    FROM cases_profilingrecord p
    WHERE p.case_id = c.case_id
    ORDER BY p.assessed_date DESC, p.profiling_id DESC
    LIMIT 1
) pr ON true;

COMMENT ON MATERIALIZED VIEW rpt.dim_youth IS
  'One row per registered youth with case and pathway context. Contains no PII by design.';


-- -----------------------------------------------------------------------------
-- rpt.fct_referral
-- -----------------------------------------------------------------------------
-- One row per referral with the derived facts every referral metric needs.
--
-- The three duration measures map onto the NNSI referral-systems playbook:
--   days_to_confirm  = Time to Match   (pending -> active)
--   days_to_attend   = the gap the prototype flags as the widest in the pipeline
--   days_to_close    = Time to Close   (initiated -> outcome recorded)

DROP MATERIALIZED VIEW IF EXISTS rpt.fct_referral CASCADE;
CREATE MATERIALIZED VIEW rpt.fct_referral AS
SELECT
    r.referral_id,
    r.case_id,
    d.youth_id,
    d.woreda,
    d.sex,
    d.age_band,
    d.psnp_client_category,
    d.has_disability,
    d.case_manager_id,
    r.referral_category,
    r.referral_trigger,
    r.is_parallel,
    r.parallel_group_id,
    r.parent_referral_id,
    r.replacement_referral_id,
    r.receiving_partner_id,
    p.partner_name,
    p.partner_type,
    r.initiated_date,
    r.confirmed_date,
    r.service_start_date,
    r.outcome_date,
    r.failure_date,
    r.status,
    r.confirmation_status,
    r.outcome_type,
    r.failure_reason_code,
    r.verification_source,

    -- durations
    (r.confirmed_date    - r.initiated_date)  AS days_to_confirm,
    (r.service_start_date - r.confirmed_date) AS days_to_attend,
    (coalesce(r.outcome_date, r.failure_date) - r.initiated_date) AS days_to_close,

    -- state classification
    (r.status IN ('completed','failed'))      AS is_closed,
    (r.status = 'completed')                  AS is_completed,
    (r.status = 'failed')                     AS is_failed,
    (r.status IN ('pending_confirmation','active')) AS is_open,

    -- timeliness, expressed the PSNP way: % within N days, not a mean
    (r.confirmed_date IS NOT NULL
     AND (r.confirmed_date - r.initiated_date)
         <= (SELECT confirmation_threshold_days FROM rpt.reporting_parameters WHERE id = 1)
    )                                          AS confirmed_within_threshold,

    -- maturation guard (README §8.2). A referral raised inside the maturation
    -- window is excluded from every rate denominator, never counted as a failure.
    rpt.is_mature(
        r.initiated_date,
        (SELECT referral_maturation_days FROM rpt.reporting_parameters WHERE id = 1)::integer
    )                                          AS is_mature,

    -- outcome verification strength. Report the verified subset as the headline;
    -- a self-reported placement rate is an aspiration, not a result.
    (r.verification_source IS NOT NULL
     AND r.verification_source <> 'self_reported') AS is_externally_verified,

    date_trunc('month', r.initiated_date)::date AS initiated_month
FROM referrals_referral r
JOIN rpt.dim_youth d      ON d.case_id = r.case_id
JOIN partners_partner p   ON p.partner_id = r.receiving_partner_id;

COMMENT ON MATERIALIZED VIEW rpt.fct_referral IS
  'One row per referral with derived durations, closure state, timeliness and maturation flags.';


-- =============================================================================
-- LAYER 2: dashboard-facing aggregates
-- =============================================================================

-- -----------------------------------------------------------------------------
-- rpt.mv_pipeline_youth  →  CARD PM-1, PM-2, WS-5
-- -----------------------------------------------------------------------------
-- One row per youth with the date they reached each pipeline stage, or NULL.
-- Stage dates, not booleans, so median-days-in-stage is computable downstream.
--
-- Stage 6 (service attended) depends on referrals_referral.service_start_date,
-- which the current DEV_SPEC §4.6 does not define. See README OQ-1. Until that
-- field exists this column is NULL and the pipeline card must show stage 6 as
-- "not yet instrumented" rather than as a zero.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_pipeline_youth CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_pipeline_youth AS
SELECT
    d.youth_id,
    d.case_id,
    d.woreda,
    d.sex,
    d.age_band,
    d.psnp_client_category,
    d.has_disability,
    d.current_pathway,

    d.registration_date                                       AS s1_registered,
    d.profiled_date                                           AS s2_profiled,
    pw.assessment_date                                        AS s3_pathway_assigned,
    ref.first_initiated                                       AS s4_referral_initiated,
    ref.first_confirmed                                       AS s5_partner_confirmed,
    ref.first_attended                                        AS s6_service_attended,
    ref.first_outcome_verified                                AS s7_outcome_verified,
    plc.first_positive_outcome                                AS s8_placed_or_enterprise,
    plc.retained_90                                           AS s9_retained_90,
    plc.placement_date,
    plc.is_subsidised,
    plc.exit_date,
    plc.exit_reason
FROM rpt.dim_youth d

LEFT JOIN LATERAL (
    SELECT min(pa.assessment_date) AS assessment_date
    FROM cases_pathwayassignment pa
    WHERE pa.case_id = d.case_id
) pw ON true

LEFT JOIN LATERAL (
    SELECT
        min(r.initiated_date)                                          AS first_initiated,
        min(r.confirmed_date)                                          AS first_confirmed,
        min(r.service_start_date)                                      AS first_attended,
        min(r.outcome_date) FILTER (
            WHERE r.status = 'completed' AND r.outcome_verified_by_id IS NOT NULL
        )                                                              AS first_outcome_verified
    FROM referrals_referral r
    WHERE r.case_id = d.case_id
) ref ON true

LEFT JOIN LATERAL (
    -- earliest positive economic outcome: a placement or an enterprise
    SELECT
        least(pl.placement_date, en.disbursement_date)                 AS first_positive_outcome,
        pl.placement_date,
        pl.is_subsidised,
        pl.exit_date,
        pl.exit_reason,
        CASE
            WHEN pl.placement_date IS NULL THEN NULL
            WHEN NOT rpt.is_mature(pl.placement_date, 90) THEN NULL     -- not yet due, NOT a failure
            WHEN pl.exit_date IS NULL OR pl.exit_date > pl.placement_date + 90 THEN true
            ELSE false
        END                                                            AS retained_90
    FROM (
        -- FIRST placement, not the current one. placement_id is the tiebreaker:
        -- without it, two same-day placements make is_subsidised / exit_reason /
        -- retained_90 flip between refreshes for the same youth.
        SELECT p.placement_date, p.is_subsidised, p.exit_date, p.exit_reason
        FROM placements_placement p
        WHERE p.case_id = d.case_id
        ORDER BY p.placement_date, p.placement_id
        LIMIT 1
    ) pl
    FULL OUTER JOIN (
        SELECT e.disbursement_date
        FROM enterprises_enterprise e
        WHERE e.case_id = d.case_id AND e.disbursement_date IS NOT NULL
        ORDER BY e.disbursement_date, e.enterprise_id
        LIMIT 1
    ) en ON true
) plc ON true;

COMMENT ON MATERIALIZED VIEW rpt.mv_pipeline_youth IS
  'Per-youth pipeline stage dates. s9_retained_90 is NULL, never false, when the 90-day mark has not passed.';


-- -----------------------------------------------------------------------------
-- rpt.mv_pipeline_summary  →  CARD PM-1 "Pipeline: where youth are lost"
-- -----------------------------------------------------------------------------
-- Stage counts, drop-off, and MEDIAN DAYS IN STAGE.
--
-- Median days in stage is the reason this is not a funnel chart. It is the most
-- actionable pipeline number available and no funnel visualisation shows it.
-- Render as a horizontal row chart with a shared left baseline; annotate the
-- drop-off between rows. Never a funnel chart (README §7).

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_pipeline_summary CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_pipeline_summary AS
WITH stages AS (
    SELECT woreda, 1 AS stage_order, 'Registered'            AS stage_label, s1_registered AS reached_date, NULL::date AS prev_date FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 2, 'Profiled & eligible',   s2_profiled,              s1_registered        FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 3, 'Pathway assigned',      s3_pathway_assigned,      s2_profiled          FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 4, 'Referral initiated',    s4_referral_initiated,    s3_pathway_assigned  FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 5, 'Partner confirmed',     s5_partner_confirmed,     s4_referral_initiated FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 6, 'Service attended',      s6_service_attended,      s5_partner_confirmed FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 7, 'Outcome verified',      s7_outcome_verified,      s6_service_attended  FROM rpt.mv_pipeline_youth
    UNION ALL SELECT woreda, 8, 'Placed / enterprise',   s8_placed_or_enterprise,  s7_outcome_verified  FROM rpt.mv_pipeline_youth
),
agg AS (
    SELECT
        woreda,
        stage_order,
        stage_label,
        count(*) FILTER (WHERE reached_date IS NOT NULL)::integer AS n_reached,
        -- Stage dates are independent per-youth minima, so a later stage can carry
        -- an EARLIER date than the one before it (a placement recorded before the
        -- referral outcome was verified, say). Without the >= guard the median
        -- goes negative and PM-1 ships "-100 days in previous stage".
        percentile_cont(0.5) WITHIN GROUP (
            ORDER BY (reached_date - prev_date)
        ) FILTER (
            WHERE reached_date IS NOT NULL
              AND prev_date IS NOT NULL
              AND reached_date >= prev_date
        ) AS median_days_from_prev,
        count(*) FILTER (
            WHERE reached_date IS NOT NULL
              AND prev_date IS NOT NULL
              AND reached_date <  prev_date
        )::integer AS n_out_of_order
    FROM stages
    GROUP BY woreda, stage_order, stage_label
)
SELECT
    a.woreda,
    a.stage_order,
    a.stage_label,
    a.n_reached,
    round(a.median_days_from_prev)::integer                              AS median_days_in_prev_stage,
    a.n_out_of_order,   -- data-quality signal: youth whose stage dates run backwards
    lag(a.n_reached) OVER (PARTITION BY a.woreda ORDER BY a.stage_order) AS n_prev_stage,
    lag(a.n_reached) OVER (PARTITION BY a.woreda ORDER BY a.stage_order) - a.n_reached AS n_lost,
    rpt.safe_rate(
        (lag(a.n_reached) OVER (PARTITION BY a.woreda ORDER BY a.stage_order) - a.n_reached)::integer,
        lag(a.n_reached) OVER (PARTITION BY a.woreda ORDER BY a.stage_order)::integer
    )                                                                    AS pct_lost,
    rpt.safe_rate(
        a.n_reached,
        max(a.n_reached) FILTER (WHERE a.stage_order = 1) OVER (PARTITION BY a.woreda)::integer
    )                                                                    AS pct_of_registered
FROM agg a;

COMMENT ON MATERIALIZED VIEW rpt.mv_pipeline_summary IS
  'Pipeline conversion by woreda. Filter woreda IS NOT NULL for panels; aggregate for the all-woreda view.';


-- -----------------------------------------------------------------------------
-- rpt.mv_referral_outcome_matrix  →  CARD PM-3 "Referral category -> outcome type"
-- -----------------------------------------------------------------------------
-- Render as a PIVOT TABLE with a single-hue background scale and the counts
-- visible. NOT a Sankey (README §7): a Sankey draws only ribbons that exist, so
-- the zero cells vanish: and the zero cells are the finding.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_referral_outcome_matrix CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_referral_outcome_matrix AS
WITH grid AS (
    -- Every woreda x category x outcome combination, including the ones with no
    -- referrals. A plain GROUP BY omits absent combinations and a Metabase pivot
    -- then renders them blank, which is indistinguishable from "no data".
    SELECT w.woreda, c.code AS referral_category, o.code AS outcome_type,
           c.sort_order AS category_order, o.sort_order AS outcome_order
    FROM (SELECT DISTINCT woreda FROM rpt.dim_youth) w
    CROSS JOIN rpt.ref_referral_category c
    CROSS JOIN rpt.ref_outcome_type o
),
observed AS (
    SELECT woreda, referral_category, outcome_type,
           count(*)::integer                 AS n_referrals,
           count(DISTINCT youth_id)::integer AS n_youth
    FROM rpt.fct_referral
    WHERE is_completed AND outcome_type IS NOT NULL
    GROUP BY woreda, referral_category, outcome_type
)
SELECT
    g.woreda,
    g.referral_category,
    g.outcome_type,
    g.category_order,
    g.outcome_order,
    coalesce(ob.n_referrals, 0) AS n_referrals,
    coalesce(ob.n_youth, 0)     AS n_youth
FROM grid g
LEFT JOIN observed ob
       ON ob.woreda = g.woreda
      AND ob.referral_category = g.referral_category
      AND ob.outcome_type = g.outcome_type

UNION ALL

-- Completed referrals with no outcome_type recorded. Kept OUT of the grid so it
-- reads as a data-quality row, not as an outcome. "0" and "not recorded" are
-- different findings and must look different on screen.
SELECT woreda, referral_category, 'not recorded', 99, 99,
       count(*)::integer, count(DISTINCT youth_id)::integer
FROM rpt.fct_referral
WHERE is_completed AND outcome_type IS NULL
GROUP BY woreda, referral_category;

COMMENT ON MATERIALIZED VIEW rpt.mv_referral_outcome_matrix IS
  'Completed referrals cross-tabulated by category and outcome. n_youth is deduplicated; '
  'use it for any person-level indicator, n_referrals for referral-level counts.';


-- -----------------------------------------------------------------------------
-- rpt.mv_partner_performance  →  CARD PM-4 "Partner performance"
-- -----------------------------------------------------------------------------
-- The highest-risk card in the system.
--
-- SORT BY n_closed DESCENDING. NOT BY RATE. Ranking on unstable rates sorts
-- partners by luck, generates management pressure on partners who happened to
-- receive few referrals, and is politically irreversible once published.
--
-- Rate suppression and the funnel verdict are computed here, not in Metabase.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_partner_performance CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_partner_performance AS
WITH scope AS (
    SELECT *
    FROM rpt.fct_referral
    WHERE is_closed
      AND is_mature
      AND initiated_date >= current_date
          - ((SELECT partner_lookback_days FROM rpt.reporting_parameters WHERE id = 1) || ' days')::interval
),
overall AS (
    SELECT
        CASE WHEN count(*) > 0
             THEN count(*) FILTER (WHERE is_completed)::numeric / count(*)
             ELSE NULL END AS overall_rate
    FROM scope
),
by_partner AS (
    SELECT
        s.receiving_partner_id,
        s.partner_name,
        s.partner_type,
        count(*)::integer                              AS n_closed,
        count(*) FILTER (WHERE s.is_completed)::integer AS n_completed,
        count(*) FILTER (WHERE s.is_failed)::integer    AS n_failed,
        round(percentile_cont(0.5) WITHIN GROUP (ORDER BY s.days_to_confirm))::integer AS median_days_to_confirm,
        count(*) FILTER (WHERE s.confirmed_within_threshold)::integer AS n_confirmed_on_time
    FROM scope s
    GROUP BY s.receiving_partner_id, s.partner_name, s.partner_type
)
SELECT
    b.receiving_partner_id                         AS partner_id,
    b.partner_name,
    b.partner_type,
    b.n_closed,
    b.n_completed,
    b.n_failed,
    b.median_days_to_confirm,
    rpt.safe_rate(b.n_confirmed_on_time, b.n_closed) AS pct_confirmed_on_time,
    rpt.safe_rate(b.n_completed, b.n_closed)         AS completion_rate,
    rpt.rate_label_nocounts(b.n_completed, b.n_closed) AS completion_rate_label,
    rpt.suppression_band(b.n_closed)                 AS band,
    w.lower_pct                                      AS ci_lower,
    w.upper_pct                                      AS ci_upper,
    rpt.funnel_verdict(b.n_completed, b.n_closed, o.overall_rate)                 AS verdict,
    rpt.verdict_label(rpt.funnel_verdict(b.n_completed, b.n_closed, o.overall_rate)) AS verdict_label,
    round(100 * o.overall_rate)                      AS programme_rate_pct
FROM by_partner b
CROSS JOIN overall o
LEFT JOIN LATERAL rpt.wilson_bounds(b.n_completed, b.n_closed) w ON true;

COMMENT ON MATERIALIZED VIEW rpt.mv_partner_performance IS
  'Partner completion rates with suppression bands, Wilson CIs and funnel-plot verdicts. '
  'ORDER BY n_closed DESC in every consuming question. Sorting by completion_rate is a review-blocking defect.';


-- -----------------------------------------------------------------------------
-- rpt.mv_partner_failure_reasons  →  CARD PM-4 drill-down
-- -----------------------------------------------------------------------------

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_partner_failure_reasons CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_partner_failure_reasons AS
SELECT
    receiving_partner_id                         AS partner_id,
    partner_name,
    coalesce(failure_reason_code, 'NOT_RECORDED') AS failure_reason_code,
    count(*)::integer                             AS n_failed
FROM rpt.fct_referral
WHERE is_failed AND is_mature
GROUP BY receiving_partner_id, partner_name, coalesce(failure_reason_code, 'NOT_RECORDED');


-- -----------------------------------------------------------------------------
-- rpt.mv_cohort_retention  →  CARD PM-5 "Placement retention by intake cohort"
-- -----------------------------------------------------------------------------
-- Render as a cohort table (Metabase pivot with conditional formatting), NOT a
-- survival curve, so the reader can separate decay-with-tenure (read across a
-- row) from cohort-over-cohort improvement (read down a column).
--
-- CENSORING IS THE CRITICAL MECHANIC. A cell whose checkpoint has not yet
-- arrived returns NULL for the rate and a date in matures_on. Rendering it as
-- 0% or as a blank is the most common bug in cohort tables, and in a donor
-- review a blank reads as programme collapse.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_cohort_retention CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_cohort_retention AS
WITH spells AS (
    -- TWO ANCHORS, deliberately, because the operational and the reporting
    -- question are different and will never produce the same number:
    --
    --   'placement'  clock starts at placement_date. Drives case manager
    --                follow-up and the 30/60/90 cascade on PM-5.
    --   'exit'       clock starts at case closed_date, unsubsidised placements
    --                only. This is the World Bank / UPSNJP construction and the
    --                one that rolls up (ME-4). Anchoring on placement instead
    --                would silently drop unplaced youth from the denominator,
    --                turning retention into a measure of who we managed to
    --                place rather than who we served.
    --
    -- Both are computed here so ME-4 can state the anchor on every row.
    SELECT
        'placement'::text                            AS anchor,
        p.placement_id,
        d.woreda,
        p.is_subsidised,
        p.placement_date                             AS anchor_date,
        p.exit_date,
        date_trunc('month', p.placement_date)::date  AS cohort_month
    FROM placements_placement p
    JOIN rpt.dim_youth d ON d.case_id = p.case_id

    UNION ALL

    SELECT
        'exit'::text,
        p.placement_id,
        d.woreda,
        p.is_subsidised,
        c.closed_date,
        p.exit_date,
        date_trunc('month', c.closed_date)::date
    FROM placements_placement p
    JOIN cases_case c    ON c.case_id = p.case_id
    JOIN rpt.dim_youth d ON d.case_id = p.case_id
    WHERE c.closed_date IS NOT NULL
      AND NOT p.is_subsidised          -- unsubsidised employment only, per UPSNJP
),
checkpoints AS (
    SELECT * FROM (VALUES (30), (60), (90)) AS t(checkpoint_days)
),
cells AS (
    SELECT
        sp.anchor,
        sp.cohort_month,
        sp.woreda,
        sp.is_subsidised,
        c.checkpoint_days,
        count(*)::integer AS n_placed,
        -- eligible = the checkpoint has actually arrived for this spell
        count(*) FILTER (
            WHERE rpt.is_mature(sp.anchor_date, c.checkpoint_days)
        )::integer AS n_eligible,
        count(*) FILTER (
            WHERE rpt.is_mature(sp.anchor_date, c.checkpoint_days)
              AND (sp.exit_date IS NULL
                   OR sp.exit_date > sp.anchor_date + c.checkpoint_days)
        )::integer AS n_retained,
        -- the last spell in the cohort to mature; drives the cell's label
        max(rpt.matures_on(sp.anchor_date, c.checkpoint_days)) AS cohort_matures_on
    FROM spells sp
    CROSS JOIN checkpoints c
    GROUP BY sp.anchor, sp.cohort_month, sp.woreda, sp.is_subsidised, c.checkpoint_days
)
SELECT
    anchor,
    cohort_month,
    woreda,
    is_subsidised,
    checkpoint_days,
    n_placed,
    n_eligible,
    n_retained,
    (n_eligible = 0)                                       AS is_censored,
    CASE WHEN n_eligible = 0 THEN cohort_matures_on END    AS matures_on,
    CASE WHEN n_eligible = 0 THEN NULL
         ELSE rpt.safe_rate(n_retained, n_eligible) END    AS retention_rate,
    CASE WHEN n_eligible = 0
         THEN 'matures ' || to_char(cohort_matures_on, 'DD Mon')
         ELSE rpt.rate_label(n_retained, n_eligible) END   AS cell_label,
    rpt.suppression_band(n_eligible)                       AS band
FROM cells;

COMMENT ON MATERIALIZED VIEW rpt.mv_cohort_retention IS
  'Retention by anchor, cohort month and checkpoint. PM-5 filters anchor = ''placement''; '
  'ME-4 filters anchor = ''exit''. is_censored marks not-yet-due cells; render those hatched '
  'with the matures_on date, never as 0% and never as a blank. Never mix anchors in one card, '
  'and always state the anchor on the row.';


-- -----------------------------------------------------------------------------
-- rpt.mv_placement_disposition  →  CARD PM-6 "What happened to the 90-day cohort"
-- -----------------------------------------------------------------------------
-- A retention percentage hides this composition, and the composition matters:
-- a youth who left for a better job is not a programme failure.
--
-- exit_reason is free text in DEV_SPEC §4.7. It must become an enum before this
-- card is trustworthy: see README OQ-5.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_placement_disposition CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_placement_disposition AS
WITH eligible AS (
    SELECT
        p.placement_id,
        d.woreda,
        p.placement_date,
        p.exit_date,
        p.exit_reason,
        p.retention_check_90_status
    FROM placements_placement p
    JOIN rpt.dim_youth d ON d.case_id = p.case_id
    WHERE rpt.is_mature(p.placement_date, 90)
)
SELECT
    woreda,
    CASE
        -- Order matters. 'unreachable' MUST be tested first: a youth we could not
        -- reach has no exit_date, so an exit_date IS NULL test would classify them
        -- as still placed. That is the optimistic-default bug this card exists to
        -- avoid: an unverified outcome counted as a success.
        WHEN retention_check_90_status = 'unreachable'            THEN 'outcome_unknown'
        WHEN exit_date IS NULL OR exit_date > placement_date + 90 THEN 'still_placed'
        WHEN exit_reason IN ('better_job','further_training','voluntary_progression') THEN 'left_for_better'
        WHEN exit_reason IS NULL                                  THEN 'outcome_unknown'
        ELSE 'left_involuntarily'
    END                       AS disposition,
    count(*)::integer         AS n
FROM eligible
GROUP BY woreda, 2;

COMMENT ON MATERIALIZED VIEW rpt.mv_placement_disposition IS
  'Disposition of the mature 90-day cohort, in exactly four segments so PM-6 stays inside the '
  'four-stack ceiling: still_placed / left_for_better / left_involuntarily / outcome_unknown. '
  'outcome_unknown merges unreachable youth and missing exit reasons: both are "we do not know", '
  'and neither may be quietly counted as a success.';


-- -----------------------------------------------------------------------------
-- rpt.mv_caseload_status  →  CARD WS-1 "Team caseload by status"
-- -----------------------------------------------------------------------------
-- Six operational statuses collapsed to FOUR display segments. Four is the
-- practical ceiling for a stacked bar; six adjacent segments cannot hold the
-- 3:1 non-text contrast WCAG 1.4.11 requires. Full six-status detail stays in
-- the drill-down table, which is also the WCAG 1.1.1 text alternative.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_caseload_status CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_caseload_status AS
SELECT
    d.woreda,
    d.case_manager_id,
    u.full_name                     AS case_manager_name,
    d.case_status,
    CASE d.case_status
        WHEN 'active'           THEN '1 On track'
        WHEN 'referral_pending' THEN '2 Awaiting partner'
        WHEN 'stalled'          THEN '3 Stalled'
        WHEN 'placed'           THEN '4 Exited or placed'
        WHEN 'exited'           THEN '4 Exited or placed'
        ELSE                         '4 Exited or placed'
    END                             AS display_segment,
    count(*)::integer               AS n_cases,
    max(current_date - d.last_activity_date)::integer AS max_days_since_activity
FROM rpt.dim_youth d
LEFT JOIN users_user u ON u.user_id = d.case_manager_id
-- The closed_date IS NULL arm is load-bearing: closed_date is nullable, and
-- without it an exited case with no closed_date evaluates to NULL and silently
-- disappears from the supervisor's caseload chart.
WHERE d.case_status <> 'exited'
   OR d.closed_date IS NULL
   OR d.closed_date >= current_date - INTERVAL '90 days'
GROUP BY d.woreda, d.case_manager_id, u.full_name, d.case_status;

COMMENT ON MATERIALIZED VIEW rpt.mv_caseload_status IS
  'Caseload by status per case manager. display_segment is prefixed 1-4 so it sorts in workflow '
  'order, never by size: a status distribution ordered by count becomes unreadable across time.';


-- -----------------------------------------------------------------------------
-- rpt.mv_data_completeness  →  CARD WS-6 "Data completeness"
-- -----------------------------------------------------------------------------
-- A data-quality widget shipped alongside the programme widgets, not hidden in
-- an admin screen. Missing failure_reason_code is the highest-cost gap: it
-- breaks the replacement-prompt logic and the partner failure breakdown at once.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_data_completeness CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_data_completeness AS
SELECT woreda, case_manager_id, 'Phone number' AS field_label,
       count(*) FILTER (WHERE missing_phone)::integer   AS n_missing,
       count(*)::integer                                AS n_total
FROM rpt.dim_youth GROUP BY woreda, case_manager_id
UNION ALL
SELECT woreda, case_manager_id, 'Profiling record',
       count(*) FILTER (WHERE missing_profile)::integer, count(*)::integer
FROM rpt.dim_youth GROUP BY woreda, case_manager_id
UNION ALL
SELECT woreda, case_manager_id, 'Consent date',
       count(*) FILTER (WHERE missing_consent)::integer, count(*)::integer
FROM rpt.dim_youth GROUP BY woreda, case_manager_id
UNION ALL
SELECT woreda, case_manager_id, 'Outcome type on completed referral',
       count(*) FILTER (WHERE outcome_type IS NULL)::integer, count(*)::integer
FROM rpt.fct_referral WHERE is_completed GROUP BY woreda, case_manager_id
UNION ALL
SELECT woreda, case_manager_id, 'Failure reason on failed referral',
       count(*) FILTER (WHERE failure_reason_code IS NULL)::integer, count(*)::integer
FROM rpt.fct_referral WHERE is_failed GROUP BY woreda, case_manager_id
UNION ALL
SELECT woreda, case_manager_id, 'Verification source on completed referral',
       count(*) FILTER (WHERE verification_source IS NULL)::integer, count(*)::integer
FROM rpt.fct_referral WHERE is_completed GROUP BY woreda, case_manager_id;


-- -----------------------------------------------------------------------------
-- rpt.mv_alert_load  →  CARDS WS-2, WS-3
-- -----------------------------------------------------------------------------
-- Counts, never a rate. A case manager's caseload is far below the 30-per-cell
-- stability floor once disaggregated, so a per-staff rate would be noise: -- and it would create cream-skimming pressure with no information value.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_alert_load CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_alert_load AS
SELECT
    d.woreda,
    a.assigned_to_id                                                     AS case_manager_id,
    u.full_name                                                          AS case_manager_name,
    a.alert_type,
    count(*)::integer                                                    AS n_open,
    count(*) FILTER (
        WHERE current_date - a.triggered_date > a.threshold_days
    )::integer                                                           AS n_overdue,
    max(current_date - a.triggered_date - a.threshold_days)::integer     AS max_days_overdue
FROM alerts_alert a
JOIN rpt.dim_youth d  ON d.case_id = a.case_id
LEFT JOIN users_user u ON u.user_id = a.assigned_to_id
WHERE a.status = 'open'
GROUP BY d.woreda, a.assigned_to_id, u.full_name, a.alert_type;


-- -----------------------------------------------------------------------------
-- rpt.mv_parallel_load  →  CARD PM-7 "Parallel referral loads"
-- -----------------------------------------------------------------------------
-- DEV_SPEC §6.3: a case may hold at most two Active referrals sharing a
-- parallel_group_id. Complementary Service referrals sit OUTSIDE that cap under
-- the current working default. This view counts both so the policy decision in
-- OQ-7 can be evidenced rather than argued.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_parallel_load CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_parallel_load AS
SELECT
    f.woreda,
    f.case_id,
    count(*) FILTER (
        WHERE f.status = 'active' AND f.referral_category <> 'complementary_service'
    )::integer AS n_active_capped,
    count(*) FILTER (
        WHERE f.status = 'active' AND f.referral_category = 'complementary_service'
    )::integer AS n_active_complementary,
    count(*) FILTER (WHERE f.status = 'active')::integer AS n_active_total,
    (count(*) FILTER (
        WHERE f.status = 'active' AND f.referral_category <> 'complementary_service'
    ) > 2) AS breaches_cap
FROM rpt.fct_referral f
GROUP BY f.woreda, f.case_id
HAVING count(*) FILTER (WHERE f.status = 'active') > 0;


-- -----------------------------------------------------------------------------
-- rpt.mv_results_framework  →  CARD ME-1 "Results framework"
-- -----------------------------------------------------------------------------
-- The donor layer. Indicator wording is taken verbatim from the parent
-- operations so woreda figures roll up without reconciliation.
--
-- FROZEN, NOT LIVE. 005_refresh.sql refreshes this monthly on a fixed date; the
-- as_of date is a column so it renders in every export. A donor dashboard that
-- changes between the analyst's screenshot and the review meeting destroys
-- trust in the numbers.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_results_framework CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_results_framework AS
WITH asof AS (SELECT current_date AS as_of),

-- 1. PSNP 5 / SEASN (P172479), verbatim wording
i1 AS (
    SELECT count(DISTINCT p.case_id)::integer AS actual
    FROM (
        SELECT case_id FROM placements_placement WHERE placement_type = 'job'
        UNION
        SELECT case_id FROM enterprises_enterprise WHERE business_plan_status = 'financed'
    ) p
),
-- 2. PSNP 5 / SEASN (P172479), verbatim wording
i2 AS (
    SELECT count(DISTINCT case_id)::integer AS actual
    FROM enterprises_enterprise
    WHERE disbursement_date IS NOT NULL
),
-- 3. World Bank Jobs M&E Toolkit (2017), intermediate
i3 AS (
    SELECT
        count(*) FILTER (WHERE completion_status = 'completed')::integer AS num,
        count(*)::integer                                                AS den
    FROM training_trainingenrolment
    WHERE enrolment_date IS NOT NULL
),
-- 4. Jobs M&E Toolkit, PDO-level. GROSS, not net of deadweight or displacement.
i4 AS (
    SELECT count(DISTINCT case_id)::integer AS actual
    FROM (
        SELECT case_id FROM placements_placement
        UNION
        SELECT case_id FROM enterprises_enterprise WHERE disbursement_date IS NOT NULL
    ) t
),
-- 5. Ethiopia UPSNJP (P169943) construction: unsubsidised only, anchored on
--    programme exit, not placement date.
i5 AS (
    SELECT
        count(*) FILTER (
            WHERE NOT p.is_subsidised
              AND (p.exit_date IS NULL OR p.exit_date > c.closed_date + 90)
        )::integer AS num,
        count(*)::integer AS den
    FROM cases_case c
    JOIN placements_placement p ON p.case_id = c.case_id
    WHERE c.closed_date IS NOT NULL
      AND rpt.is_mature(c.closed_date, 90)
),
-- 6. PSNP "% of transfers within 45 days" construction, adapted to referrals
i6 AS (
    SELECT
        count(*) FILTER (WHERE confirmed_within_threshold)::integer AS num,
        count(*)::integer                                           AS den
    FROM rpt.fct_referral
    WHERE is_mature
),
-- 7. CMS50 "Closing the Referral Loop", adapted. Maturation window applied.
i7 AS (
    SELECT
        count(*) FILTER (WHERE is_completed)::integer AS num,
        count(*)::integer                             AS den
    FROM rpt.fct_referral
    WHERE is_closed AND is_mature
)
SELECT * FROM (
    SELECT 1 AS ord,
        'Youth clients with business plans financed or enrolled in wage employment' AS indicator,
        'PSNP 5 / SEASN (P172479), verbatim'  AS source_framework,
        'count'                               AS unit,
        i1.actual::numeric AS actual, NULL::integer AS num, NULL::integer AS den, a.as_of
    FROM i1, asof a
    UNION ALL SELECT 2, 'Youth who received livelihood grant',
        'PSNP 5 / SEASN (P172479), verbatim', 'count', i2.actual, NULL, NULL, a.as_of FROM i2, asof a
    UNION ALL SELECT 3, 'Share of project beneficiaries completing training',
        'WB Jobs M&E Toolkit (2017), intermediate', 'rate',
        rpt.safe_rate(i3.num, i3.den), i3.num, i3.den, a.as_of FROM i3, asof a
    UNION ALL SELECT 4, 'Number of self- and/or wage employed project beneficiaries',
        'WB Jobs M&E Toolkit, PDO-level', 'count', i4.actual, NULL, NULL, a.as_of FROM i4, asof a
    UNION ALL SELECT 5, 'Wage-employed 3 months after completion (unsubsidised)',
        'Ethiopia UPSNJP (P169943) construction', 'rate',
        rpt.safe_rate(i5.num, i5.den), i5.num, i5.den, a.as_of FROM i5, asof a
    UNION ALL SELECT 6, 'Referrals confirmed by the receiving partner within threshold',
        'PSNP "within 45 days" construction, adapted', 'rate',
        rpt.safe_rate(i6.num, i6.den), i6.num, i6.den, a.as_of FROM i6, asof a
    UNION ALL SELECT 7, 'Referral loop closure rate',
        'CMS50 closed-loop logic, adapted', 'rate',
        rpt.safe_rate(i7.num, i7.den), i7.num, i7.den, a.as_of FROM i7, asof a
) x
ORDER BY ord;

COMMENT ON MATERIALIZED VIEW rpt.mv_results_framework IS
  'Donor results framework. Refreshed monthly on a fixed date, not nightly. Targets are held in '
  'rpt.indicator_targets so a target revision does not require a code change.';


-- -----------------------------------------------------------------------------
-- rpt.indicator_targets: editable through Django admin
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS rpt.indicator_targets (
    ord            integer PRIMARY KEY,
    target_value   numeric NOT NULL,
    target_date    date    NOT NULL,
    notes          text
);

INSERT INTO rpt.indicator_targets (ord, target_value, target_date, notes) VALUES
    (1, 300, '2026-12-31', 'End-of-pilot target, 3 woredas'),
    (2, 180, '2026-12-31', NULL),
    (3,  75, '2026-12-31', 'percentage'),
    (4, 260, '2026-12-31', NULL),
    (5,  60, '2026-12-31', 'percentage'),
    (6,  80, '2026-12-31', 'percentage'),
    (7,  70, '2026-12-31', 'percentage')
ON CONFLICT (ord) DO NOTHING;


-- -----------------------------------------------------------------------------
-- rpt.mv_disaggregation  →  CARD ME-3 "Disaggregation"
-- -----------------------------------------------------------------------------
-- Suppression applies to EVERY disaggregation, not just the headline. The cuts
-- donors ask for: female, PWD, by woreda, by age band: are precisely where
-- denominators collapse.
--
-- SECONDARY SUPPRESSION IS NOT IMPLEMENTED HERE. If one cell in a group is
-- suppressed and the group total is published, the hidden value is recoverable
-- by subtraction. The consuming Metabase question must suppress a second cell
-- or suppress the total. See README §6.2 and OQ-6.

DROP MATERIALIZED VIEW IF EXISTS rpt.mv_disaggregation CASCADE;
CREATE MATERIALIZED VIEW rpt.mv_disaggregation AS
WITH base AS (
    SELECT
        p.youth_id,
        d.sex, d.age_band, d.psnp_client_category, d.has_disability, d.woreda,
        d.current_pathway,
        (p.s8_placed_or_enterprise IS NOT NULL) AS is_placed
    FROM rpt.mv_pipeline_youth p
    JOIN rpt.dim_youth d ON d.youth_id = p.youth_id
),
cuts AS (
    SELECT 'Sex'             AS dimension, sex                                       AS grp, is_placed FROM base
    UNION ALL SELECT 'Age band',           age_band,                                     is_placed FROM base
    UNION ALL SELECT 'PSNP client category', coalesce(psnp_client_category,'Not PSNP'), is_placed FROM base
    UNION ALL SELECT 'Disability status',  CASE WHEN has_disability THEN 'With disability' ELSE 'No disability' END, is_placed FROM base
    UNION ALL SELECT 'Woreda',             woreda,                                       is_placed FROM base
    UNION ALL SELECT 'Pathway',            coalesce(current_pathway,'Not assigned'),     is_placed FROM base
)
-- Rural/urban is required by README §6.2 but has NO source column: DEV_SPEC §4.1
-- has no settlement type, and woreda does not imply one. Tracked as OQ-11.
-- TODO(open-question): add Youth.settlement_type, then add the cut here.
SELECT
    dimension,
    grp                                             AS group_label,
    count(*)::integer                               AS n_registered,
    count(*) FILTER (WHERE is_placed)::integer      AS n_placed,
    rpt.safe_rate(count(*) FILTER (WHERE is_placed)::integer, count(*)::integer) AS placement_rate,
    rpt.rate_label_nocounts(count(*) FILTER (WHERE is_placed)::integer, count(*)::integer) AS placement_rate_label,
    rpt.suppression_band(count(*)::integer)         AS band
FROM cuts
GROUP BY dimension, grp;
