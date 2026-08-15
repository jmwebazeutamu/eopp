"""Alert detection jobs — spec §6 system actions, scheduled per §10 Sprint 4.

Each job turns a condition that already exists in the data into an Alert row
somebody owns. The conditions are defined once, as querysets on the entities
themselves (`Case.objects.stalled_beyond_threshold`,
`Referral.objects.awaiting_onward_prompt`, and so on), and these jobs only
materialise them — so the §8 dashboards and the alerts can never disagree about
what "stalled" means.

Every job is idempotent. Beat re-runs them on a schedule and they re-detect the
same conditions each time; `_raise` is a no-op when an open alert already
exists, backed by a partial unique index rather than trust.
"""

import logging
from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.db import IntegrityError, transaction

from apps.cases.models import Case
from apps.referrals.models import Referral, ReferralStatus

from .models import Alert, AlertStatus, AlertType, threshold_for

logger = logging.getLogger(__name__)


def _raise(case, alert_type, referral=None, summary="", assigned_to=None):
    """Create an alert unless an equivalent one is already open.

    Returns the alert if one was created, else None. The IntegrityError branch
    catches the race where two beat workers detect the same condition at once —
    the database refuses the second, which is exactly the wanted outcome.
    """
    assignee = assigned_to or case.case_manager

    existing = Alert.objects.open().filter(case=case, alert_type=alert_type, referral=referral).exists()
    if existing:
        return None

    try:
        with transaction.atomic():
            return Alert.objects.create(
                case=case,
                referral=referral,
                alert_type=alert_type,
                threshold_days=threshold_for(alert_type),
                assigned_to=assignee,
                summary=summary[:255],
            )
    except IntegrityError:
        # Lost the race to another worker; the alert exists, which is the point.
        logger.debug("Alert already raised concurrently: %s / %s", case.pk, alert_type)
        return None


@shared_task(name="alerts.detect_stalled_cases")
def detect_stalled_cases():
    """Cases with no activity past the stall threshold — spec §4.13, §8.

    Deliberately does NOT set `case_status = STALLED`. §6.2's System Action
    column lists alerts, never a status change, and moving a case to Stalled is
    a judgement about the case rather than an observation about the clock. The
    case manager makes that call from the alert.
    """
    threshold = settings.STALL_ALERT_THRESHOLD_DAYS
    created = 0

    for case in Case.objects.stalled_beyond_threshold(threshold).select_related("youth", "case_manager"):
        alert = _raise(
            case,
            AlertType.STALL,
            summary=f"No activity for {case.days_since_activity} days (threshold {threshold}).",
        )
        created += bool(alert)

    logger.info("detect_stalled_cases: %s alert(s) raised", created)
    return created


@shared_task(name="alerts.detect_overdue_confirmations")
def detect_overdue_confirmations():
    """Referrals a partner has not answered within the window — §4.13.

    Pairs with the PARTNER_NON_RESPONSIVE failure code in §5.4: this alert is
    what tells a case manager that code may now apply.
    """
    threshold = settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS
    cutoff = date.today() - timedelta(days=threshold)
    created = 0

    overdue = Referral.objects.filter(
        status=ReferralStatus.PENDING_CONFIRMATION, initiated_date__lt=cutoff
    ).select_related("case", "case__youth", "case__case_manager", "receiving_partner")

    for referral in overdue:
        waiting = (date.today() - referral.initiated_date).days
        alert = _raise(
            referral.case,
            AlertType.REFERRAL_CONFIRMATION_OVERDUE,
            referral=referral,
            summary=(
                f"{referral.receiving_partner.partner_name} has not confirmed "
                f"in {waiting} days (threshold {threshold})."
            ),
        )
        created += bool(alert)

    logger.info("detect_overdue_confirmations: %s alert(s) raised", created)
    return created


@shared_task(name="alerts.generate_onward_prompts")
def generate_onward_prompts():
    """Completed referrals with no onward step yet — spec §6.2, §5.2.

    §5.2 is explicit that the case manager "reviews and confirms before the new
    referral is created, to manage data entry burden", so this raises a prompt
    and stops. Nothing is created on the youth's record automatically.
    """
    created = 0

    for referral in Referral.objects.awaiting_onward_prompt().select_related(
        "case", "case__youth", "case__case_manager", "referral_category"
    ):
        alert = _raise(
            referral.case,
            AlertType.ONWARD_REFERRAL_PROMPT,
            referral=referral,
            summary=(
                f"{referral.referral_category.label} referral completed"
                f"{' with ' + referral.outcome_type.label if referral.outcome_type_id else ''}. "
                "Consider an onward referral."
            ),
        )
        created += bool(alert)

    logger.info("generate_onward_prompts: %s prompt(s) raised", created)
    return created


@shared_task(name="alerts.generate_replacement_prompts")
def generate_replacement_prompts():
    """Failed referrals with no replacement yet — spec §6.2.

    Cancelled referrals are excluded by construction: §6.1 keeps Cancelled
    separate from Failed precisely so a case manager's own withdrawal does not
    prompt a replacement.
    """
    created = 0

    for referral in Referral.objects.awaiting_replacement_prompt().select_related(
        "case", "case__youth", "case__case_manager", "referral_category", "failure_reason_code"
    ):
        reason = referral.failure_reason_code.label if referral.failure_reason_code_id else "unspecified"
        alert = _raise(
            referral.case,
            AlertType.REPLACEMENT_REFERRAL_PROMPT,
            referral=referral,
            summary=f"{referral.referral_category.label} referral failed ({reason}). Consider a replacement.",
        )
        created += bool(alert)

    logger.info("generate_replacement_prompts: %s prompt(s) raised", created)
    return created


@shared_task(name="alerts.resolve_cleared_alerts")
def resolve_cleared_alerts():
    """Close alerts whose underlying condition has gone away.

    An alert is a view of a condition, so when the condition clears the alert
    should not sit in an inbox waiting to be dismissed by hand — a case manager
    who logs a visit has already dealt with the stall. Closed as ACTIONED with
    no `actioned_by`, which is how a system resolution is distinguished from a
    person's in the §9 audit trail.
    """
    resolved = 0

    for alert in Alert.objects.open().select_related("case", "referral"):
        if not _condition_still_holds(alert):
            alert.resolve(AlertStatus.ACTIONED)
            resolved += 1

    logger.info("resolve_cleared_alerts: %s alert(s) auto-closed", resolved)
    return resolved


def _condition_still_holds(alert):
    """Whether the situation that raised this alert is still true."""
    if alert.alert_type == AlertType.STALL:
        # Re-derived from the same queryset the detection job uses, against the
        # threshold recorded on the alert rather than today's setting — an alert
        # raised under a 30-day rule is not silently re-judged at 45.
        return Case.objects.filter(pk=alert.case_id).stalled_beyond_threshold(alert.threshold_days).exists()

    if alert.alert_type == AlertType.REFERRAL_CONFIRMATION_OVERDUE:
        return Referral.objects.filter(pk=alert.referral_id, status=ReferralStatus.PENDING_CONFIRMATION).exists()

    if alert.alert_type == AlertType.ONWARD_REFERRAL_PROMPT:
        return Referral.objects.filter(pk=alert.referral_id).awaiting_onward_prompt().exists()

    if alert.alert_type == AlertType.REPLACEMENT_REFERRAL_PROMPT:
        return Referral.objects.filter(pk=alert.referral_id).awaiting_replacement_prompt().exists()

    # FOLLOW_UP_DUE and RETENTION_CHECK_DUE have no detection job yet — their
    # source entities are Follow-Up (§4.9, Sprint 6) and Placement (§4.7,
    # Sprint 5). Leave them open rather than auto-closing something this
    # function cannot actually evaluate.
    return True


@shared_task(name="alerts.run_all_detections")
def run_all_detections():
    """Every detection job plus the resolution sweep, in order.

    Resolution runs last so an alert raised and cleared within one cycle does
    not linger until the next.
    """
    return {
        "stalled": detect_stalled_cases(),
        "overdue_confirmations": detect_overdue_confirmations(),
        "onward_prompts": generate_onward_prompts(),
        "replacement_prompts": generate_replacement_prompts(),
        "auto_resolved": resolve_cleared_alerts(),
    }
