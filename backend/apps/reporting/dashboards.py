"""The nine spec §8 dashboards, as data. The single definition Metabase is built from.

Each card is SQL over a bi view (never a table in `public`). Numbers the
programme can change — the caseload ceiling, the stall threshold, the rate
bands — are read from settings and `apps.dashboard.rules` here and handed to
Metabase as parameter defaults, so changing a setting and re-running
`build_metabase_dashboards` moves every card that depends on it.
"""

from django.conf import settings

from apps.dashboard import rules
from apps.referrals.models import ReferralStatus


def _bi(view: str) -> str:
    return f"{settings.BI_SCHEMA}.{view}"


WOREDA = "[[AND woreda = {{woreda}}]]"
WOREDA_TAG = {"woreda": {"name": "woreda", "display-name": "Woreda", "type": "text", "required": False}}


def dashboards() -> list:
    """Return [{name, description, cards:[{name, sql, display, tags, w, h}]}]."""
    ceiling, stall = settings.CASELOAD_CEILING, settings.STALL_ALERT_THRESHOLD_DAYS
    return [
        {
            "name": "Case status distribution",
            "description": "Cases by status, filterable by woreda and case manager.",
            "cards": [
                {
                    "name": "Cases by status",
                    "sql": f"SELECT case_status, COUNT(*) AS cases FROM {_bi('case_status')} "
                    f"WHERE TRUE {WOREDA} [[AND case_manager = {{{{case_manager}}}}]] GROUP BY 1 ORDER BY 2 DESC",
                    "display": "bar",
                    "tags": {
                        **WOREDA_TAG,
                        "case_manager": {
                            "name": "case_manager",
                            "display-name": "Case manager",
                            "type": "text",
                            "required": False,
                        },
                    },
                }
            ],
        },
        {
            "name": "Referral pipeline by stage and type",
            "description": "Referral count by status and category.",
            "cards": [
                {
                    "name": "Referrals by status and category",
                    "sql": f"SELECT category, status, COUNT(*) AS referrals FROM {_bi('referral_pipeline')} "
                    f"WHERE TRUE {WOREDA} GROUP BY 1, 2 ORDER BY 1, 2",
                    "display": "bar",
                    "tags": WOREDA_TAG,
                    "viz": {"stackable.stack_type": "stacked"},
                }
            ],
        },
        {
            "name": "Parallel referral loads",
            "description": "Cases with two or more concurrently Active referrals in one parallel group.",
            "cards": [
                {
                    "name": "Cases carrying a parallel load",
                    "sql": f"SELECT COUNT(DISTINCT case_id) AS cases FROM {_bi('parallel_load')} WHERE TRUE {WOREDA}",
                    "display": "scalar",
                    "tags": WOREDA_TAG,
                },
                {
                    "name": "Parallel load by size",
                    "sql": f"SELECT active_referrals, COUNT(*) AS groups FROM {_bi('parallel_load')} "
                    f"WHERE TRUE {WOREDA} GROUP BY 1 ORDER BY 1",
                    "display": "bar",
                    "tags": WOREDA_TAG,
                },
            ],
        },
        {
            "name": "Outcome type breakdown",
            "description": "Completed referrals by outcome type.",
            "cards": [
                {
                    "name": "Completed referrals by outcome",
                    "sql": f"SELECT COALESCE(outcome, 'No outcome recorded') AS outcome, COUNT(*) AS referrals "
                    f"FROM {_bi('referral_outcomes')} WHERE TRUE {WOREDA} GROUP BY 1 ORDER BY 2 DESC",
                    "display": "pie",
                    "tags": WOREDA_TAG,
                }
            ],
        },
        {
            "name": "Failed referral rate by partner",
            "description": (
                f"Failed ÷ ({ReferralStatus.FAILED.label} + {ReferralStatus.COMPLETED.label}). "
                f"A rate is shown from {rules.PROVISIONAL_MIN_DENOMINATOR} closed referrals; "
                f"below that it is withheld, not zero. Ordered by evidence, not by rate."
            ),
            "cards": [
                {
                    "name": "Failed rate by partner",
                    "sql": f"SELECT partner_name, failed, closed, failed_percent, band FROM {_bi('partner_closure')} "
                    f"ORDER BY closed DESC",
                    "display": "table",
                },
                {
                    "name": "Failure reasons by partner",
                    "sql": f"SELECT partner_name, reason, failed FROM {_bi('failure_reasons')} ORDER BY partner_name, failed DESC",
                    "display": "bar",
                    "viz": {"stackable.stack_type": "stacked"},
                },
            ],
        },
        {
            "name": "Referral completion rate by partner",
            "description": (
                f"Completed ÷ closed referrals; same bands as the failed rate "
                f"({rules.REPORT_MIN_DENOMINATOR} to report, {rules.PROVISIONAL_MIN_DENOMINATOR} provisional)."
            ),
            "cards": [
                {
                    "name": "Completion rate by partner",
                    "sql": f"SELECT partner_name, completed, closed, completed_percent, band FROM {_bi('partner_closure')} "
                    f"ORDER BY closed DESC",
                    "display": "table",
                }
            ],
        },
        {
            "name": "Placement retention",
            "description": "Retention at the 30/60/90-day checkpoints, by sector and by referral-sourced vs direct.",
            "cards": [
                {
                    "name": "Checkpoint outcome by sector",
                    "sql": f"SELECT sector, checkpoint, check_status, COUNT(*) AS checks FROM {_bi('placement_retention')} "
                    f"WHERE TRUE {WOREDA} GROUP BY 1, 2, 3 ORDER BY 1, 2",
                    "display": "table",
                    "tags": WOREDA_TAG,
                },
                {
                    "name": "Checkpoint outcome, referral-sourced vs direct",
                    "sql": f"SELECT CASE WHEN referral_sourced THEN 'Referral-sourced' ELSE 'Direct' END AS source, "
                    f"checkpoint, check_status, COUNT(*) AS checks FROM {_bi('placement_retention')} "
                    f"WHERE TRUE {WOREDA} GROUP BY 1, 2, 3 ORDER BY 1, 2",
                    "display": "table",
                    "tags": WOREDA_TAG,
                },
            ],
        },
        {
            "name": "Caseload by case manager",
            "description": f"Active cases per case manager; the ceiling is {ceiling} (setting CASELOAD_CEILING).",
            "cards": [
                {
                    "name": "Active cases per case manager",
                    "sql": "SELECT case_manager, SUM(active_cases) AS active_cases, "
                    "SUM(active_cases) > {{ceiling}} AS over_ceiling "
                    f"FROM {_bi('caseload')} WHERE TRUE {WOREDA} GROUP BY 1 ORDER BY 2 DESC",
                    "display": "bar",
                    "tags": {
                        **WOREDA_TAG,
                        "ceiling": {
                            "name": "ceiling",
                            "display-name": "Caseload ceiling",
                            "type": "number",
                            "default": str(ceiling),
                            "required": True,
                        },
                    },
                }
            ],
        },
        {
            "name": "Stalled case alerts",
            "description": f"Cases with no activity for more than {stall} days (setting STALL_ALERT_THRESHOLD_DAYS).",
            "cards": [
                {
                    "name": "Cases past the stall threshold",
                    "sql": f"SELECT case_id, woreda, case_manager, case_status, last_activity_date, days_since_activity, "
                    f"has_open_alert FROM {_bi('stalled_cases')} WHERE days_since_activity > {{{{stall_days}}}} "
                    f"{WOREDA} ORDER BY days_since_activity DESC",
                    "display": "table",
                    "tags": {
                        **WOREDA_TAG,
                        "stall_days": {
                            "name": "stall_days",
                            "display-name": "Stall threshold (days)",
                            "type": "number",
                            "default": str(stall),
                            "required": True,
                        },
                    },
                }
            ],
        },
    ]
