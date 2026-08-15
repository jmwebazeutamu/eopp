"""Alert tests — spec §4.13, and the §6 system actions that raise them.

Thresholds are exercised at their boundaries with freezegun rather than by
constructing dates by hand, so an off-by-one in a job shows up here.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from freezegun import freeze_time

from apps.alerts import tasks
from apps.alerts.models import Alert, AlertStatus, AlertType, threshold_for
from apps.referrals import services
from apps.referrals.models import ReferralStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(make_case, case_manager):
    return make_case(case_manager)


def _age_case(case, days):
    """Push a case's last activity back without touching it."""
    from apps.cases.models import Case

    Case.objects.filter(pk=case.pk).update(last_activity_date=date.today() - timedelta(days=days))
    case.refresh_from_db()
    return case


# ---------------------------------------------------------------------------
# Stall detection — spec §4.13, §8
# ---------------------------------------------------------------------------


def test_stall_alert_raised_past_the_threshold(case, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)

    assert tasks.detect_stalled_cases() == 1
    alert = Alert.objects.get(case=case, alert_type=AlertType.STALL)
    assert alert.status == AlertStatus.OPEN
    assert alert.threshold_days == 30
    assert "45 days" in alert.summary


def test_no_stall_alert_below_the_threshold(case, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 29)
    assert tasks.detect_stalled_cases() == 0


def test_stall_alert_fires_exactly_on_the_threshold(case, settings):
    """30 days with a 30-day threshold must alert, not wait for 31."""
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 30)
    assert tasks.detect_stalled_cases() == 1


def test_stall_alert_is_assigned_to_the_case_manager(case, case_manager, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 40)
    tasks.detect_stalled_cases()
    assert Alert.objects.get(case=case).assigned_to == case_manager


def test_closed_cases_never_raise_stall_alerts(case, settings):
    from apps.cases.models import Case, CaseStatus

    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 200)
    Case.objects.filter(pk=case.pk).update(
        case_status=CaseStatus.EXITED, closed_date=date.today(), exit_reason="Placed"
    )
    assert tasks.detect_stalled_cases() == 0


def test_stall_detection_does_not_change_case_status(case, settings):
    """§6.2's System Action column lists alerts, never a status change."""
    from apps.cases.models import CaseStatus

    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 60)
    tasks.detect_stalled_cases()
    case.refresh_from_db()
    assert case.case_status == CaseStatus.ACTIVE


# ---------------------------------------------------------------------------
# Idempotence — beat re-runs these on a schedule
# ---------------------------------------------------------------------------


def test_repeated_runs_do_not_duplicate_alerts(case, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)

    assert tasks.detect_stalled_cases() == 1
    assert tasks.detect_stalled_cases() == 0
    assert tasks.detect_stalled_cases() == 0
    assert Alert.objects.filter(case=case, alert_type=AlertType.STALL).count() == 1


def test_database_refuses_a_second_open_alert_of_the_same_kind(case, case_manager, settings):
    """The dedup guard is a constraint, not just a check in the job."""
    Alert.objects.create(case=case, alert_type=AlertType.STALL, assigned_to=case_manager)
    with pytest.raises(IntegrityError), transaction.atomic():
        Alert.objects.create(case=case, alert_type=AlertType.STALL, assigned_to=case_manager)


def test_a_resolved_alert_can_be_raised_again(case, case_manager, settings):
    """Dedup applies to *open* alerts — a recurring condition must re-alert."""
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)

    tasks.detect_stalled_cases()
    Alert.objects.get(case=case).resolve(AlertStatus.DISMISSED, actor=case_manager)

    assert tasks.detect_stalled_cases() == 1
    assert Alert.objects.filter(case=case, alert_type=AlertType.STALL).count() == 2


# ---------------------------------------------------------------------------
# Referral confirmation overdue — spec §4.13, §5.4
# ---------------------------------------------------------------------------


def test_overdue_confirmation_alert(case, make_referral, settings):
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7

    with freeze_time(date.today() - timedelta(days=10)):
        referral = make_referral(case)

    assert tasks.detect_overdue_confirmations() == 1
    alert = Alert.objects.get(alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE)
    assert alert.referral == referral
    assert "10 days" in alert.summary


def test_recent_referral_is_not_overdue(case, make_referral, settings):
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
    with freeze_time(date.today() - timedelta(days=3)):
        make_referral(case)
    assert tasks.detect_overdue_confirmations() == 0


def test_confirmed_referral_is_not_overdue(case, make_referral, case_manager, settings):
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
    with freeze_time(date.today() - timedelta(days=20)):
        referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    assert tasks.detect_overdue_confirmations() == 0


def test_two_overdue_referrals_raise_two_distinct_alerts(case, make_referral, taxonomy, settings):
    """Alerts are per-referral, so a case can hold more than one of a type."""
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
    with freeze_time(date.today() - timedelta(days=15)):
        make_referral(case, category=taxonomy["training"])
        make_referral(case, category=taxonomy["employment"])

    assert tasks.detect_overdue_confirmations() == 2
    assert Alert.objects.filter(alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE).count() == 2


# ---------------------------------------------------------------------------
# Onward and replacement prompts — spec §6.2
# ---------------------------------------------------------------------------


def test_completion_raises_an_onward_prompt(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    assert tasks.generate_onward_prompts() == 1
    alert = Alert.objects.get(alert_type=AlertType.ONWARD_REFERRAL_PROMPT)
    assert alert.referral == referral
    assert "Training Completion" in alert.summary


def test_failure_raises_a_replacement_prompt(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])

    assert tasks.generate_replacement_prompts() == 1
    alert = Alert.objects.get(alert_type=AlertType.REPLACEMENT_REFERRAL_PROMPT)
    assert "Youth no-show" in alert.summary


def test_cancellation_raises_no_replacement_prompt(case, make_referral, case_manager):
    """§6.1 separates Cancelled from Failed so a withdrawal does not prompt."""
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.CANCELLED, actor=case_manager)
    assert tasks.generate_replacement_prompts() == 0


def test_prompts_do_not_create_referrals_automatically(case, make_referral, case_manager, taxonomy):
    """§5.2: the case manager confirms before anything is created."""
    from apps.referrals.models import Referral

    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    tasks.generate_onward_prompts()
    assert Referral.objects.filter(case=case).count() == 1  # only the original


# ---------------------------------------------------------------------------
# Auto-resolution
# ---------------------------------------------------------------------------


def test_activity_clears_a_stall_alert(case, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()

    case.touch()  # a case manager logs something

    assert tasks.resolve_cleared_alerts() == 1
    alert = Alert.objects.get(case=case, alert_type=AlertType.STALL)
    assert alert.status == AlertStatus.ACTIONED
    # No actor: this is how a system resolution reads in the §9 audit trail.
    assert alert.actioned_by is None


def test_confirming_a_referral_clears_the_overdue_alert(case, make_referral, case_manager, settings):
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
    with freeze_time(date.today() - timedelta(days=15)):
        referral = make_referral(case)
    tasks.detect_overdue_confirmations()

    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    assert tasks.resolve_cleared_alerts() >= 1
    assert Alert.objects.get(alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE).status == AlertStatus.ACTIONED


def test_creating_the_onward_referral_clears_its_prompt(case, make_referral, case_manager, taxonomy, partner):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])
    tasks.generate_onward_prompts()

    services.create_onward_referral(
        parent=referral,
        referral_category=taxonomy["employment"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )

    tasks.resolve_cleared_alerts()
    assert Alert.objects.get(alert_type=AlertType.ONWARD_REFERRAL_PROMPT).status == AlertStatus.ACTIONED


def test_resolution_uses_the_threshold_recorded_on_the_alert(case, settings):
    """An alert raised under a 30-day rule is not re-judged at 90."""
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()

    settings.STALL_ALERT_THRESHOLD_DAYS = 90  # policy changes later

    assert tasks.resolve_cleared_alerts() == 0
    assert Alert.objects.get(case=case).status == AlertStatus.OPEN


def test_open_alert_with_a_live_condition_is_left_alone(case, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()
    assert tasks.resolve_cleared_alerts() == 0


# ---------------------------------------------------------------------------
# Model rules
# ---------------------------------------------------------------------------


def test_referral_scoped_alert_types_require_a_referral(case, case_manager):
    alert = Alert(case=case, alert_type=AlertType.ONWARD_REFERRAL_PROMPT, assigned_to=case_manager)
    with pytest.raises(ValidationError) as exc:
        alert.clean()
    assert "referral" in exc.value.message_dict


def test_a_referral_from_another_case_is_rejected(case, make_case, make_referral, case_manager, other_case_manager):
    other = make_case(other_case_manager, name="Other")
    foreign = make_referral(other, initiated_by=other_case_manager)
    alert = Alert(
        case=case,
        referral=foreign,
        alert_type=AlertType.ONWARD_REFERRAL_PROMPT,
        assigned_to=case_manager,
    )
    with pytest.raises(ValidationError) as exc:
        alert.clean()
    assert "referral" in exc.value.message_dict


def test_resolving_an_already_closed_alert_is_refused(case, case_manager):
    alert = Alert.objects.create(case=case, alert_type=AlertType.STALL, assigned_to=case_manager)
    alert.resolve(AlertStatus.ACTIONED, actor=case_manager)
    with pytest.raises(ValidationError):
        alert.resolve(AlertStatus.DISMISSED, actor=case_manager)


def test_threshold_lookup_covers_every_alert_type(settings):
    """A type with no configured threshold would silently record 0."""
    for value, _label in AlertType.choices:
        assert threshold_for(value) is not None


# ---------------------------------------------------------------------------
# API — spec §7 scoping and resolution
# ---------------------------------------------------------------------------


def test_case_manager_sees_only_their_own_alerts(case, make_case, other_case_manager, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    theirs = make_case(other_case_manager, name="Theirs")
    _age_case(case, 45)
    _age_case(theirs, 45)
    tasks.detect_stalled_cases()

    response = as_user(case_manager).get("/api/v1/alerts/")
    assert response.data["count"] == 1


def test_my_inbox_returns_assigned_open_alerts(case, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()

    response = as_user(case_manager).get("/api/v1/alerts/my-inbox/")
    assert response.data["count"] == 1


def test_actioning_an_alert_records_the_actor(case, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()
    alert = Alert.objects.get(case=case)

    response = as_user(case_manager).post(
        f"/api/v1/alerts/{alert.pk}/action/", {"note": "Home visit completed"}, format="json"
    )
    assert response.status_code == 200, response.data
    alert.refresh_from_db()
    assert alert.status == AlertStatus.ACTIONED
    assert alert.actioned_by == case_manager


def test_dismissing_is_distinct_from_actioning(case, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()
    alert = Alert.objects.get(case=case)

    as_user(case_manager).post(f"/api/v1/alerts/{alert.pk}/dismiss/", {}, format="json")
    alert.refresh_from_db()
    assert alert.status == AlertStatus.DISMISSED


def test_supervisor_can_read_but_not_resolve(case, supervisor, as_user, settings):
    """§7 makes the supervisor read-only on case content."""
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()
    alert = Alert.objects.get(case=case)

    client = as_user(supervisor)
    assert client.get("/api/v1/alerts/").data["count"] == 1
    # 403 from CanAccessCases, which refuses unsafe methods for read-only roles
    # before the view runs. The equivalent check inside _resolve is a backstop
    # for any future route that reaches it by another path.
    assert client.post(f"/api/v1/alerts/{alert.pk}/action/", {}, format="json").status_code == 403


def test_alerts_cannot_be_deleted(case, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()
    alert = Alert.objects.get(case=case)
    assert as_user(case_manager).delete(f"/api/v1/alerts/{alert.pk}/").status_code == 405


def test_summary_counts_by_type(case, case_manager, as_user, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    tasks.detect_stalled_cases()

    response = as_user(case_manager).get("/api/v1/alerts/summary/")
    assert response.data["open_total"] == 1
    assert response.data["assigned_to_me"] == 1
    stall_row = next(r for r in response.data["by_type"] if r["alert_type"] == AlertType.STALL)
    assert stall_row["count"] == 1
    # Every type appears, so the UI can render a stable list.
    assert len(response.data["by_type"]) == len(AlertType.choices)


def test_run_all_detections_reports_each_job(case, make_referral, case_manager, taxonomy, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    _age_case(case, 45)
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])
    # The transition touched the case, so it is no longer stalled.
    _age_case(case, 45)

    result = tasks.run_all_detections()
    assert result["stalled"] == 1
    assert result["replacement_prompts"] == 1
    assert set(result) == {
        "stalled",
        "overdue_confirmations",
        "onward_prompts",
        "replacement_prompts",
        "auto_resolved",
    }
