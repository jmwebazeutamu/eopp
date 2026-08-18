-- =============================================================================
-- 005_refresh.sql
--
-- Refresh procedures, called from Celery beat. Run AFTER 004_indexes.sql: -- CONCURRENTLY requires the unique indexes created there.
--
-- CADENCE, and why each tier differs:
--
--   Tier 1  case manager     LIVE. Not in this schema at all. Django views read
--                            the application tables directly. See
--                            django/CASE_MANAGER_DASHBOARD.md.
--   Tier 2  woreda supervisor  05:30 EAT daily, before the 07:00 email goes out
--   Tier 3  programme manager  02:00 EAT nightly
--   Tier 4  M&E / donor        FROZEN. Monthly, on the 1st. Never nightly.
--
-- Tier 4 is frozen because a donor dashboard that changes between the analyst's
-- screenshot and the review meeting destroys trust in the numbers. The as_of
-- date is a column on mv_results_framework so it renders in every export.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- rpt.refresh_operational(): tiers 2 and 3
-- -----------------------------------------------------------------------------
-- Order matters: dim_youth and fct_referral are the base layer and everything
-- else reads them. Refreshing a dependent view against a stale base produces
-- silently inconsistent cards.

CREATE OR REPLACE PROCEDURE rpt.refresh_operational(p_concurrently boolean DEFAULT true)
LANGUAGE plpgsql
AS $$
DECLARE
    v_view    text;
    v_started timestamptz := clock_timestamp();
    v_views   text[] := ARRAY[
        -- base layer first
        'dim_youth',
        'fct_referral',
        -- dependents
        'mv_pipeline_youth',
        'mv_pipeline_summary',
        'mv_referral_outcome_matrix',
        'mv_partner_performance',
        'mv_partner_failure_reasons',
        'mv_cohort_retention',
        'mv_placement_disposition',
        'mv_caseload_status',
        'mv_data_completeness',
        'mv_alert_load',
        'mv_parallel_load',
        'mv_disaggregation'
    ];
BEGIN
    FOREACH v_view IN ARRAY v_views LOOP
        IF p_concurrently THEN
            EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY rpt.%I', v_view);
        ELSE
            EXECUTE format('REFRESH MATERIALIZED VIEW rpt.%I', v_view);
        END IF;
    END LOOP;

    INSERT INTO rpt.refresh_log (scope, started_at, finished_at)
    VALUES ('operational', v_started, clock_timestamp());
END;
$$;


-- -----------------------------------------------------------------------------
-- rpt.refresh_donor(): tier 4 only. Call monthly, not nightly.
-- -----------------------------------------------------------------------------

CREATE OR REPLACE PROCEDURE rpt.refresh_donor(p_concurrently boolean DEFAULT true)
LANGUAGE plpgsql
AS $$
DECLARE
    v_started timestamptz := clock_timestamp();
BEGIN
    IF p_concurrently THEN
        REFRESH MATERIALIZED VIEW CONCURRENTLY rpt.mv_results_framework;
    ELSE
        REFRESH MATERIALIZED VIEW rpt.mv_results_framework;
    END IF;

    INSERT INTO rpt.refresh_log (scope, started_at, finished_at)
    VALUES ('donor', v_started, clock_timestamp());
END;
$$;


-- -----------------------------------------------------------------------------
-- rpt.refresh_all(): first build, and the test harness
-- -----------------------------------------------------------------------------
-- Uses non-concurrent refresh, because a materialised view that has never been
-- populated cannot be refreshed CONCURRENTLY.

CREATE OR REPLACE PROCEDURE rpt.refresh_all()
LANGUAGE plpgsql
AS $$
BEGIN
    CALL rpt.refresh_operational(p_concurrently => false);
    CALL rpt.refresh_donor(p_concurrently => false);
END;
$$;


-- -----------------------------------------------------------------------------
-- rpt.refresh_log: freshness, surfaced on the dashboards
-- -----------------------------------------------------------------------------
-- Every dashboard renders "as of <timestamp>" from this table. A dashboard that
-- does not say how stale it is invites the reader to assume it is live.

CREATE TABLE IF NOT EXISTS rpt.refresh_log (
    id          bigserial PRIMARY KEY,
    scope       text        NOT NULL,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL,
    duration_ms integer GENERATED ALWAYS AS
        ((extract(epoch FROM (finished_at - started_at)) * 1000)::integer) STORED
);

CREATE INDEX IF NOT EXISTS ix_refresh_log_scope ON rpt.refresh_log (scope, finished_at DESC);

CREATE OR REPLACE VIEW rpt.v_freshness AS
SELECT DISTINCT ON (scope)
    scope,
    finished_at                                            AS as_of,
    duration_ms,
    (now() - finished_at)                                  AS age,
    CASE scope
        WHEN 'operational' THEN (now() - finished_at) > INTERVAL '30 hours'
        WHEN 'donor'       THEN (now() - finished_at) > INTERVAL '40 days'
    END                                                    AS is_stale
FROM rpt.refresh_log
ORDER BY scope, finished_at DESC;

GRANT SELECT ON rpt.v_freshness TO metabase_ro;

COMMENT ON VIEW rpt.v_freshness IS
  'Drives the "as of" stamp in every dashboard header. is_stale should raise an ops alert, '
  'and the dashboards should show a stale banner rather than quietly serving old numbers.';


-- -----------------------------------------------------------------------------
-- Celery beat schedule: put this in backend/config/celery.py
-- -----------------------------------------------------------------------------
/*
from celery.schedules import crontab

app.conf.beat_schedule = {
    # Tier 3: programme manager. Nightly.
    "refresh-reporting-nightly": {
        "task": "apps.reporting.tasks.refresh_operational",
        "schedule": crontab(hour=2, minute=0),      # 02:00 EAT
    },
    # Tier 2: woreda supervisor. Before the 07:00 email subscription.
    "refresh-reporting-morning": {
        "task": "apps.reporting.tasks.refresh_operational",
        "schedule": crontab(hour=5, minute=30),     # 05:30 EAT
    },
    # Tier 4: donor. Monthly on the 1st. NOT nightly; see the header of this file.
    "refresh-reporting-donor": {
        "task": "apps.reporting.tasks.refresh_donor",
        "schedule": crontab(day_of_month=1, hour=3, minute=0),
    },
}

# apps/reporting/tasks.py
#
# from celery import shared_task
# from django.db import connection
#
# @shared_task
# def refresh_operational():
#     with connection.cursor() as cur:
#         cur.execute("CALL rpt.refresh_operational();")
#
# @shared_task
# def refresh_donor():
#     with connection.cursor() as cur:
#         cur.execute("CALL rpt.refresh_donor();")
*/
