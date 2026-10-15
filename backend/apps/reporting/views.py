"""SQL for the bi schema: the only thing the Metabase role can read (spec §8).

Nothing here is a literal that the application already owns. Table and column
names come from model metadata, status values from the enums, thresholds from
`apps.dashboard.rules`, and the schema name from settings, so a renamed column,
a new enum member or a moved threshold changes the views on the next `migrate`
rather than leaving them quietly wrong. The views are rebuilt by signal (see
`apps.py`) rather than by a migration for the same reason: a migration freezes
the SQL at the moment it was written.

Views, not tables: a card reads the row the application wrote a moment ago. No
view carries a name, phone number or national id of a young person — Metabase
has no row scoping, so the schema is the privacy boundary.

Youth-side only: every referral view requires a case, the same module boundary
as `Referral.objects.youth_side()`.

Two thresholds are deliberately NOT here: the caseload ceiling and the stall
threshold. A view would freeze them at build time; the views expose the raw
count and age and the dashboards read the settings (see `dashboards.py`).
"""

from django.conf import settings

from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.cases.models import Case, CaseStatus
from apps.dashboard.rules import PROVISIONAL_MIN_DENOMINATOR, REPORT_MIN_DENOMINATOR
from apps.partners.models import Partner
from apps.placements.models import Placement, RetentionCheck
from apps.referrals.models import Referral, ReferralStatus
from apps.referrals.taxonomy import FailureReasonCode, OutcomeType, ReferralCategory
from apps.users.models import User


def t(model) -> str:
    return model._meta.db_table


def c(model, field: str) -> str:
    return model._meta.get_field(field).column


def lit(values) -> str:
    """A SQL IN-list from enum members, in a stable order."""
    return ", ".join("'%s'" % v for v in sorted(str(x.value) for x in values))


def schema() -> str:
    return settings.BI_SCHEMA


def _views() -> dict:
    case_, ref, part, usr = t(Case), t(Referral), t(Partner), t(User)
    cat, out, fail = t(ReferralCategory), t(OutcomeType), t(FailureReasonCode)
    cm = c(Case, "case_manager")
    r_case, r_part = c(Referral, "case"), c(Referral, "receiving_partner")
    open_cases = CaseStatus.open_statuses()
    live_cases = [s for s in open_cases if s != CaseStatus.PLACED]
    closed = [ReferralStatus.COMPLETED, ReferralStatus.FAILED]
    done, failed = ReferralStatus.COMPLETED.value, ReferralStatus.FAILED.value
    n = "COUNT(*)"
    return {
        "case_status": f"""
            SELECT k.id AS case_id, k.{c(Case, 'case_status')} AS case_status, k.{c(Case, 'woreda')} AS woreda,
                   k.{cm} AS case_manager_id, u.{c(User, 'full_name')} AS case_manager,
                   k.{c(Case, 'opened_date')} AS opened_date, k.{c(Case, 'closed_date')} AS closed_date,
                   k.{c(Case, 'last_activity_date')} AS last_activity_date,
                   (CURRENT_DATE - k.{c(Case, 'last_activity_date')}) AS days_since_activity
            FROM {case_} k JOIN {usr} u ON u.id = k.{cm}""",
        "referral_pipeline": f"""
            SELECT r.id AS referral_id, r.{r_case} AS case_id, k.{c(Case, 'woreda')} AS woreda,
                   r.{c(Referral, 'status')} AS status, r.{c(Referral, 'referral_category')} AS category_code,
                   g.label AS category, r.{r_part} AS partner_id,
                   r.{c(Referral, 'initiated_date')} AS initiated_date
            FROM {ref} r JOIN {case_} k ON k.id = r.{r_case}
            JOIN {cat} g ON g.code = r.{c(Referral, 'referral_category')}
            WHERE r.{r_case} IS NOT NULL""",
        "parallel_load": f"""
            SELECT r.{r_case} AS case_id, k.{c(Case, 'woreda')} AS woreda,
                   r.{c(Referral, 'parallel_group_id')} AS parallel_group_id, {n} AS active_referrals
            FROM {ref} r JOIN {case_} k ON k.id = r.{r_case}
            WHERE r.{c(Referral, 'status')} = '{ReferralStatus.ACTIVE.value}'
              AND r.{c(Referral, 'parallel_group_id')} IS NOT NULL
            GROUP BY r.{r_case}, k.{c(Case, 'woreda')}, r.{c(Referral, 'parallel_group_id')}
            HAVING {n} >= 2""",
        "referral_outcomes": f"""
            SELECT r.id AS referral_id, k.{c(Case, 'woreda')} AS woreda,
                   r.{c(Referral, 'outcome_type')} AS outcome_code, o.label AS outcome,
                   r.{c(Referral, 'outcome_date')} AS outcome_date,
                   r.{c(Referral, 'verification_source')} AS verification_source
            FROM {ref} r JOIN {case_} k ON k.id = r.{r_case}
            LEFT JOIN {out} o ON o.code = r.{c(Referral, 'outcome_type')}
            WHERE r.{c(Referral, 'status')} = '{done}'""",
        # Failed ÷ (Failed + Completed): the definition apps.dashboard.tiers uses,
        # so a card and the in-app partner panel cannot disagree. A rate is NULL
        # below the provisional floor — suppressed is not zero.
        "partner_closure": f"""
            SELECT p.id AS partner_id, p.{c(Partner, 'partner_name')} AS partner_name,
                   {n} FILTER (WHERE r.{c(Referral, 'status')} = '{done}') AS completed,
                   {n} FILTER (WHERE r.{c(Referral, 'status')} = '{failed}') AS failed,
                   {n} AS closed,
                   CASE WHEN {n} >= {PROVISIONAL_MIN_DENOMINATOR} THEN
                        ROUND(100.0 * {n} FILTER (WHERE r.{c(Referral, 'status')} = '{failed}') / {n}) END AS failed_percent,
                   CASE WHEN {n} >= {PROVISIONAL_MIN_DENOMINATOR} THEN
                        ROUND(100.0 * {n} FILTER (WHERE r.{c(Referral, 'status')} = '{done}') / {n}) END AS completed_percent,
                   CASE WHEN {n} >= {REPORT_MIN_DENOMINATOR} THEN 'report'
                        WHEN {n} >= {PROVISIONAL_MIN_DENOMINATOR} THEN 'provisional'
                        ELSE 'withheld' END AS band
            FROM {ref} r JOIN {part} p ON p.id = r.{r_part}
            WHERE r.{r_case} IS NOT NULL AND r.{c(Referral, 'status')} IN ({lit(closed)})
            GROUP BY p.id, p.{c(Partner, 'partner_name')}""",
        "failure_reasons": f"""
            SELECT p.id AS partner_id, p.{c(Partner, 'partner_name')} AS partner_name,
                   COALESCE(f.label, 'No reason recorded') AS reason, {n} AS failed
            FROM {ref} r JOIN {part} p ON p.id = r.{r_part}
            LEFT JOIN {fail} f ON f.code = r.{c(Referral, 'failure_reason_code')}
            WHERE r.{r_case} IS NOT NULL AND r.{c(Referral, 'status')} = '{failed}'
            GROUP BY p.id, p.{c(Partner, 'partner_name')}, f.label""",
        "placement_retention": f"""
            SELECT pl.id AS placement_id, k.{c(Case, 'woreda')} AS woreda,
                   pl.{c(Placement, 'sector')} AS sector,
                   (pl.{c(Placement, 'source_referral')} IS NOT NULL) AS referral_sourced,
                   pl.{c(Placement, 'is_subsidised')} AS is_subsidised,
                   pl.{c(Placement, 'placement_date')} AS placement_date,
                   rc.{c(RetentionCheck, 'checkpoint')} AS checkpoint,
                   rc.{c(RetentionCheck, 'status')} AS check_status
            FROM {t(Placement)} pl JOIN {case_} k ON k.id = pl.{c(Placement, 'case')}
            JOIN {t(RetentionCheck)} rc ON rc.{c(RetentionCheck, 'placement')} = pl.id""",
        "caseload": f"""
            SELECT k.{cm} AS case_manager_id, u.{c(User, 'full_name')} AS case_manager,
                   k.{c(Case, 'woreda')} AS woreda, {n} AS active_cases
            FROM {case_} k JOIN {usr} u ON u.id = k.{cm}
            WHERE k.{c(Case, 'case_status')} IN ({lit(open_cases)})
            GROUP BY k.{cm}, u.{c(User, 'full_name')}, k.{c(Case, 'woreda')}""",
        "stalled_cases": f"""
            SELECT k.id AS case_id, k.{c(Case, 'woreda')} AS woreda, u.{c(User, 'full_name')} AS case_manager,
                   k.{c(Case, 'case_status')} AS case_status,
                   k.{c(Case, 'last_activity_date')} AS last_activity_date,
                   (CURRENT_DATE - k.{c(Case, 'last_activity_date')}) AS days_since_activity,
                   EXISTS (SELECT 1 FROM {t(Alert)} a WHERE a.{c(Alert, 'case')} = k.id
                           AND a.{c(Alert, 'alert_type')} = '{AlertType.STALL.value}'
                           AND a.{c(Alert, 'status')} = '{AlertStatus.OPEN.value}') AS has_open_alert
            FROM {case_} k JOIN {usr} u ON u.id = k.{cm}
            WHERE k.{c(Case, 'case_status')} IN ({lit(live_cases)})""",
    }


def view_names() -> list:
    return list(_views())


def drop_sql() -> str:
    return f"DROP SCHEMA IF EXISTS {schema()} CASCADE;"


def create_sql() -> str:
    stmts = [f"CREATE SCHEMA IF NOT EXISTS {schema()};"]
    stmts += [f"CREATE VIEW {schema()}.{name} AS {sql};" for name, sql in _views().items()]
    return "\n".join(stmts)
