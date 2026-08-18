-- =============================================================================
-- 004_indexes.sql
--
-- Two sets of indexes:
--   (a) on the APPLICATION tables, to make the materialised-view refresh fast
--   (b) on the MATERIALISED VIEWS, to make Metabase filtering fast
--
-- (b) matters more than it looks. Each Metabase card is an independent query
-- round-trip; on a high-latency 3G connection, per-card latency dominates
-- perceived load time far more than payload size does.
--
-- Every mv_* gets at least one UNIQUE index. That is not optional: REFRESH
-- MATERIALIZED VIEW CONCURRENTLY requires one, and without CONCURRENTLY the
-- refresh takes an ACCESS EXCLUSIVE lock and every dashboard blocks for its
-- duration.
-- =============================================================================


-- =============================================================================
-- (a) Application tables: refresh performance
-- =============================================================================

CREATE INDEX IF NOT EXISTS ix_referral_case          ON referrals_referral (case_id);
CREATE INDEX IF NOT EXISTS ix_referral_partner       ON referrals_referral (receiving_partner_id);
CREATE INDEX IF NOT EXISTS ix_referral_status        ON referrals_referral (status);
CREATE INDEX IF NOT EXISTS ix_referral_initiated     ON referrals_referral (initiated_date);
CREATE INDEX IF NOT EXISTS ix_referral_parent        ON referrals_referral (parent_referral_id)
    WHERE parent_referral_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_referral_parallel      ON referrals_referral (parallel_group_id)
    WHERE parallel_group_id IS NOT NULL;

-- The case manager's "referrals awaiting partner response" queue. Partial index:
-- pending referrals are a small and shrinking fraction of the table, and this is
-- the hottest query on the operational dashboard.
CREATE INDEX IF NOT EXISTS ix_referral_pending_by_initiator
    ON referrals_referral (initiated_by_id, initiated_date)
    WHERE confirmation_status = 'pending_confirmation';

CREATE INDEX IF NOT EXISTS ix_case_manager           ON cases_case (case_manager_id);
CREATE INDEX IF NOT EXISTS ix_case_woreda_status     ON cases_case (woreda, case_status);
CREATE INDEX IF NOT EXISTS ix_case_last_activity     ON cases_case (last_activity_date);

CREATE INDEX IF NOT EXISTS ix_profiling_case         ON cases_profilingrecord (case_id, assessed_date DESC);
CREATE INDEX IF NOT EXISTS ix_pathway_case_current   ON cases_pathwayassignment (case_id) WHERE is_current;

CREATE INDEX IF NOT EXISTS ix_placement_case         ON placements_placement (case_id);
CREATE INDEX IF NOT EXISTS ix_placement_date         ON placements_placement (placement_date);
CREATE INDEX IF NOT EXISTS ix_enterprise_case        ON enterprises_enterprise (case_id);
CREATE INDEX IF NOT EXISTS ix_training_case          ON training_trainingenrolment (case_id);
CREATE INDEX IF NOT EXISTS ix_followup_case          ON followups_followup (case_id, attempt_date DESC);

-- The alert work queue. Partial index on open alerts only: the whole point of
-- the operational dashboard is that it answers "what is still open" in one hop.
CREATE INDEX IF NOT EXISTS ix_alert_open_assignee
    ON alerts_alert (assigned_to_id, triggered_date)
    WHERE status = 'open';
CREATE INDEX IF NOT EXISTS ix_alert_case             ON alerts_alert (case_id);

CREATE INDEX IF NOT EXISTS ix_youth_woreda           ON youth_youth (woreda);


-- =============================================================================
-- (b) Materialised views: Metabase filter performance
--     UNIQUE indexes are REQUIRED for CONCURRENTLY refresh.
-- =============================================================================

CREATE UNIQUE INDEX IF NOT EXISTS ux_dim_youth              ON rpt.dim_youth (youth_id);
CREATE INDEX        IF NOT EXISTS ix_dim_youth_woreda       ON rpt.dim_youth (woreda, case_status);
CREATE INDEX        IF NOT EXISTS ix_dim_youth_cm           ON rpt.dim_youth (case_manager_id);
CREATE INDEX        IF NOT EXISTS ix_dim_youth_disagg       ON rpt.dim_youth (sex, age_band, psnp_client_category);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fct_referral           ON rpt.fct_referral (referral_id);
CREATE INDEX        IF NOT EXISTS ix_fct_referral_partner   ON rpt.fct_referral (receiving_partner_id, status);
CREATE INDEX        IF NOT EXISTS ix_fct_referral_woreda    ON rpt.fct_referral (woreda, initiated_month);
CREATE INDEX        IF NOT EXISTS ix_fct_referral_mature    ON rpt.fct_referral (is_mature, is_closed);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pipeline_youth         ON rpt.mv_pipeline_youth (youth_id);
CREATE INDEX        IF NOT EXISTS ix_pipeline_youth_woreda  ON rpt.mv_pipeline_youth (woreda);

CREATE UNIQUE INDEX IF NOT EXISTS ux_pipeline_summary       ON rpt.mv_pipeline_summary (woreda, stage_order);

CREATE UNIQUE INDEX IF NOT EXISTS ux_outcome_matrix
    ON rpt.mv_referral_outcome_matrix (woreda, referral_category, outcome_type);
-- The view CROSS JOINs the taxonomy lookups, so a woreda x category x outcome
-- triple appears exactly once; the UNION ALL branch uses the reserved
-- outcome_type 'not recorded', which is not a member of rpt.ref_outcome_type.

CREATE UNIQUE INDEX IF NOT EXISTS ux_partner_performance    ON rpt.mv_partner_performance (partner_id);
-- Deliberately NOT indexed on completion_rate. Sorting this view by rate is a
-- review-blocking defect (README §7), and there is no reason to make it fast.

CREATE UNIQUE INDEX IF NOT EXISTS ux_partner_failure
    ON rpt.mv_partner_failure_reasons (partner_id, failure_reason_code);

CREATE UNIQUE INDEX IF NOT EXISTS ux_cohort_retention
    ON rpt.mv_cohort_retention (anchor, cohort_month, woreda, is_subsidised, checkpoint_days);
CREATE INDEX IF NOT EXISTS ix_cohort_retention_anchor
    ON rpt.mv_cohort_retention (anchor, checkpoint_days);

CREATE UNIQUE INDEX IF NOT EXISTS ux_placement_disposition
    ON rpt.mv_placement_disposition (woreda, disposition);

CREATE UNIQUE INDEX IF NOT EXISTS ux_caseload_status
    ON rpt.mv_caseload_status (woreda, case_manager_id, case_status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_data_completeness
    ON rpt.mv_data_completeness (woreda, case_manager_id, field_label);

CREATE UNIQUE INDEX IF NOT EXISTS ux_alert_load
    ON rpt.mv_alert_load (woreda, case_manager_id, alert_type);

CREATE UNIQUE INDEX IF NOT EXISTS ux_parallel_load          ON rpt.mv_parallel_load (case_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_results_framework      ON rpt.mv_results_framework (ord);

CREATE UNIQUE INDEX IF NOT EXISTS ux_disaggregation
    ON rpt.mv_disaggregation (dimension, group_label);
