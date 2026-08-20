"""Reading and refreshing the WLT materialized views.

The views are created in migration `0004_reporting_views`. This module is how
the rest of the platform touches them: a refresh entry point for the Celery task
and the management command, and thin readers for the two aggregate screens.

Why materialized views at all, when `services.indicators` computes the same
figures in Python: the indicator service is the source of truth and answers for
*one group*, which is what a readiness card and a gate need. These answer for a
kebele, a woreda or a region at once, and doing that per group in Python is a
query per group per page. The two must agree, and a test asserts they do on the
seeded fixture — that test is the reason both can exist.
"""

from django.db import connection

# In dependency order. `wlt_refresh_reporting()` refreshes the first two
# CONCURRENTLY so a rebuild never blocks the facilitator UI, which is why both
# carry a unique index.
VIEWS = [
    "wlt_mv_group_compliance",
    "wlt_mv_group_financials",
    "wlt_mv_groups_by_phase",
    "wlt_mv_cla_readiness",
    "wlt_mv_linkage_funnel",
    "wlt_mv_linkage_block_reasons",
    "wlt_mv_enrolment_vs_allocation",
    "wlt_mv_cohort_survival",
    "wlt_mv_formation_attrition",
]


def refresh():
    """Rebuild every WLT view. Called nightly, and by `manage.py refresh_wlt_reporting`.

    Two routes, because `REFRESH ... CONCURRENTLY` cannot run inside a
    transaction block. Normally the stored procedure runs and commits between
    views, which is what keeps the two the UI reads readable throughout. Inside
    an open transaction — every test, and any caller that wrapped this in
    `atomic` — the procedure's `COMMIT` is illegal, so the views are refreshed
    one at a time and non-concurrently. Same data either way; the difference is
    only whether a concurrent reader is blocked for the duration.
    """
    if connection.in_atomic_block:
        with connection.cursor() as cursor:
            for view in VIEWS:
                cursor.execute(f"REFRESH MATERIALIZED VIEW {view}")
        return {"refreshed": True, "concurrent": False}

    with connection.cursor() as cursor:
        cursor.execute("CALL wlt_refresh_reporting()")
    return {"refreshed": True, "concurrent": True}


def _rows(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def cla_readiness(kebele_ids=None):
    """Per kebele: eligible groups, the threshold, and how many more are needed."""
    sql = """
        SELECT r.kebele_id, l.name AS kebele, r.eligible_groups, r.threshold, r.groups_short
          FROM wlt_mv_cla_readiness r
          JOIN locations_location l ON l.id = r.kebele_id
    """
    params = []
    if kebele_ids is not None:
        sql += " WHERE r.kebele_id = ANY(%s)"
        params.append(list(kebele_ids))
    sql += " ORDER BY r.groups_short, l.name"
    return _rows(sql, params)


def linkage_funnel():
    """Proposed through closed, across both linkage surfaces."""
    return _rows("SELECT * FROM wlt_mv_linkage_funnel ORDER BY source, type_code, status")


def block_reasons():
    """Which gate is stopping groups, and how often."""
    return _rows("SELECT * FROM wlt_mv_linkage_block_reasons ORDER BY n DESC")


def enrolment_vs_allocation():
    return _rows("SELECT * FROM wlt_mv_enrolment_vs_allocation ORDER BY region")


def cohort_survival():
    return _rows("SELECT * FROM wlt_mv_cohort_survival ORDER BY cohort_month")


def formation_attrition():
    return _rows(
        """
        SELECT a.*, l.name AS kebele
          FROM wlt_mv_formation_attrition a
          JOIN locations_location l ON l.id = a.kebele_id
         ORDER BY l.name
        """
    )


def groups_by_phase():
    return _rows("SELECT * FROM wlt_mv_groups_by_phase")
