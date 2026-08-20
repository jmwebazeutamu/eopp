"""Follow-Up / Contact Log — spec §4.9, and the §6.2 verification path.

Most of these are about the failures. A contact log that records only successful
calls cannot answer CM-4's "4+ failed contact attempts", cannot say whether a
caseload is contactable, and cannot verify anything — because the whole value of
`REACHED_ENGAGED` is that it stands beside the attempts that were not.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.alerts import tasks
from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.followups import services
from apps.followups.models import ContactMethod, ContactOutcome, ReEngagementStatus
from apps.referrals.models import ReferralStatus, VerificationSource

pytestmark = pytest.mark.django_db


@pytest.fixture
def log(db, case_manager):
    def _record(case, outcome=ContactOutcome.REACHED_ENGAGED, **fields):
        return services.record_attempt(
            case=case,
            contact_method=fields.pop("contact_method", ContactMethod.PHONE),
            contact_outcome=outcome,
            conducted_by=fields.pop("conducted_by", case_manager),
            **fields,
        )

    return _record


@pytest.fixture
def completed_referral(make_case, make_referral, case_manager, taxonomy):
    case = make_case(case_manager)
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["job_placement"])
    return referral


# ---------------------------------------------------------------------------
# The log itself
# ---------------------------------------------------------------------------


def test_a_failed_attempt_is_recorded_like_any_other(make_case, case_manager, log):
    """The failures are the point. CM-4's condition does not exist without them."""
    attempt = log(make_case(case_manager), ContactOutcome.NO_RESPONSE)
    assert attempt.pk is not None
    assert attempt.reached_the_youth is False


def test_trying_counts_as_activity_on_the_case(make_case, case_manager, log):
    """A case manager who called four times should not have the case counted as
    stalled for want of activity."""
    from apps.cases.models import Case

    case = make_case(case_manager)
    Case.objects.filter(pk=case.pk).update(last_activity_date=date.today() - timedelta(days=90))

    log(case, ContactOutcome.UNREACHABLE)
    case.refresh_from_db()
    assert case.last_activity_date == date.today()


def test_a_contact_that_reached_nobody_cannot_record_what_she_said(make_case, case_manager, log):
    with pytest.raises(ValidationError) as caught:
        log(
            make_case(case_manager),
            ContactOutcome.NO_RESPONSE,
            re_engagement_status=ReEngagementStatus.AGREED,
        )
    assert "re_engagement_status" in caught.value.message_dict


def test_a_pathway_revision_has_to_come_from_the_youth(make_case, case_manager, log):
    """A revision decided without her is a decision *about* her, which §4.4's
    assessment is not."""
    with pytest.raises(ValidationError) as caught:
        log(make_case(case_manager), ContactOutcome.UNREACHABLE, pathway_revision_flag=True)
    assert "pathway_revision_flag" in caught.value.message_dict


def test_an_attempt_cannot_be_dated_in_the_future(make_case, case_manager, log):
    with pytest.raises(ValidationError):
        log(make_case(case_manager), attempt_date=date.today() + timedelta(days=1))


def test_a_referral_from_another_case_is_refused(make_case, case_manager, make_referral, log):
    other = make_case(case_manager, name="Other")
    referral = make_referral(other)
    with pytest.raises(ValidationError) as caught:
        log(make_case(case_manager, name="Mine"), related_referral=referral)
    assert "related_referral" in caught.value.message_dict


# ---------------------------------------------------------------------------
# CM-4's fourth condition
# ---------------------------------------------------------------------------


def test_four_failed_attempts_put_a_case_on_the_at_risk_list(make_case, case_manager, log, settings):
    from apps.dashboard import queues

    settings.FAILED_CONTACT_ATTEMPTS_AT_RISK = 4
    case = make_case(case_manager)
    for _ in range(4):
        log(case, ContactOutcome.NO_RESPONSE)

    assert case.pk in {item.pk for item in queues.at_risk(case_manager)}


def test_three_failures_do_not(make_case, case_manager, log, settings):
    from apps.dashboard import queues

    settings.FAILED_CONTACT_ATTEMPTS_AT_RISK = 4
    case = make_case(case_manager)
    for _ in range(3):
        log(case, ContactOutcome.NO_RESPONSE)

    assert case.pk not in {item.pk for item in queues.at_risk(case_manager)}


def test_a_youth_who_answered_and_declined_is_not_unreachable(make_case, case_manager, log, settings):
    """Reached-not-engaged is not a failure to contact. She said no, and the
    case manager knows where she stands — a different problem, for a different
    queue."""
    from apps.dashboard import queues

    settings.FAILED_CONTACT_ATTEMPTS_AT_RISK = 4
    case = make_case(case_manager)
    for _ in range(5):
        log(case, ContactOutcome.REACHED_NOT_ENGAGED)

    assert case.pk not in {item.pk for item in queues.at_risk(case_manager)}


def test_the_contact_summary_separates_reached_from_failed(make_case, case_manager, log):
    case = make_case(case_manager)
    log(case, ContactOutcome.NO_RESPONSE)
    log(case, ContactOutcome.UNREACHABLE)
    log(case, ContactOutcome.REACHED_NOT_ENGAGED)

    summary = services.contact_summary(case)
    assert summary["attempts"] == 3
    assert summary["failed"] == 2
    assert summary["reached"] == 1


# ---------------------------------------------------------------------------
# Verification — §6.2, §8.3
# ---------------------------------------------------------------------------


def test_a_follow_up_that_reached_the_youth_verifies_her_outcome(completed_referral, case_manager, log):
    attempt = log(completed_referral.case, ContactOutcome.REACHED_ENGAGED, related_referral=completed_referral)
    services.verify_referral_outcome(
        attempt, verification_source=VerificationSource.EMPLOYER_CONFIRMED, actor=case_manager
    )
    completed_referral.refresh_from_db()

    assert completed_referral.is_externally_verified
    assert completed_referral.outcome_verified_by == case_manager
    # The method is stamped with the source and the verifier, not typed
    # separately — the three used to drift apart when each was set by hand.
    assert completed_referral.outcome_verification_method


def test_a_call_nobody_answered_cannot_verify_anything(completed_referral, case_manager, log):
    """A verification founded on an unanswered call is the self-reported figure
    wearing a better label."""
    attempt = log(completed_referral.case, ContactOutcome.NO_RESPONSE, related_referral=completed_referral)
    with pytest.raises(ValidationError):
        services.verify_referral_outcome(
            attempt, verification_source=VerificationSource.EMPLOYER_CONFIRMED, actor=case_manager
        )


def test_a_follow_up_with_no_referral_cannot_verify(make_case, case_manager, log):
    attempt = log(make_case(case_manager), ContactOutcome.REACHED_ENGAGED)
    with pytest.raises(ValidationError):
        services.verify_referral_outcome(
            attempt, verification_source=VerificationSource.DOCUMENT_VERIFIED, actor=case_manager
        )


def test_a_referral_with_no_outcome_has_nothing_to_verify(make_case, make_referral, case_manager, log):
    case = make_case(case_manager)
    referral = make_referral(case)
    attempt = log(case, ContactOutcome.REACHED_ENGAGED, related_referral=referral)
    with pytest.raises(ValidationError):
        services.verify_referral_outcome(
            attempt, verification_source=VerificationSource.PROVIDER_CONFIRMED, actor=case_manager
        )


def test_self_reported_is_recorded_but_leaves_no_verifier(completed_referral, case_manager, log):
    """The youth said so, which is a record and not a verification. Stamping the
    verifier would make it look like one."""
    attempt = log(completed_referral.case, ContactOutcome.REACHED_ENGAGED, related_referral=completed_referral)
    services.verify_referral_outcome(attempt, verification_source=VerificationSource.SELF_REPORTED, actor=case_manager)
    completed_referral.refresh_from_db()

    assert completed_referral.verification_source == VerificationSource.SELF_REPORTED
    assert completed_referral.is_externally_verified is False


def test_the_unverified_queue_is_the_complement_of_the_verified_one(completed_referral, case_manager, log):
    from apps.referrals.models import Referral

    referrals = Referral.objects.youth_side()
    assert services.unverified_outcomes(referrals).count() == 1

    attempt = log(completed_referral.case, ContactOutcome.REACHED_ENGAGED, related_referral=completed_referral)
    services.verify_referral_outcome(
        attempt, verification_source=VerificationSource.PROVIDER_CONFIRMED, actor=case_manager
    )

    assert services.unverified_outcomes(referrals).count() == 0


# ---------------------------------------------------------------------------
# The Follow-Up Due alert — §4.13's last undetected type
# ---------------------------------------------------------------------------


@pytest.fixture
def active_referral(make_case, make_referral, case_manager):
    case = make_case(case_manager)
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    return referral


def test_an_active_referral_nobody_followed_up_raises_an_alert(active_referral, settings):
    from apps.referrals.models import Referral

    settings.FOLLOW_UP_DUE_DAYS = 14
    Referral.objects.filter(pk=active_referral.pk).update(confirmed_date=date.today() - timedelta(days=20))

    assert tasks.detect_follow_ups_due() == 1
    alert = Alert.objects.get(alert_type=AlertType.FOLLOW_UP_DUE)
    assert alert.referral == active_referral


def test_a_recently_confirmed_referral_does_not(active_referral, settings):
    settings.FOLLOW_UP_DUE_DAYS = 14
    assert tasks.detect_follow_ups_due() == 0


def test_recording_any_attempt_clears_the_alert(active_referral, case_manager, log, settings):
    """Successful or not: trying is the action the alert asks for, and whether
    she answered is what the log itself records."""
    from apps.referrals.models import Referral

    settings.FOLLOW_UP_DUE_DAYS = 14
    Referral.objects.filter(pk=active_referral.pk).update(confirmed_date=date.today() - timedelta(days=20))
    tasks.detect_follow_ups_due()

    log(active_referral.case, ContactOutcome.NO_RESPONSE, related_referral=active_referral)

    assert tasks.resolve_cleared_alerts() == 1
    assert Alert.objects.get(alert_type=AlertType.FOLLOW_UP_DUE).status == AlertStatus.ACTIONED


def test_a_completed_referral_is_not_awaiting_follow_up(completed_referral, settings):
    settings.FOLLOW_UP_DUE_DAYS = 14
    assert tasks.detect_follow_ups_due() == 0


# ---------------------------------------------------------------------------
# §7 scoping
# ---------------------------------------------------------------------------


def test_the_log_cannot_be_edited_through_the_api(as_user, case_manager, make_case, log):
    """A contact log that can be edited afterwards is not evidence of anything,
    including the four failures CM-4 counts."""
    attempt = log(make_case(case_manager), ContactOutcome.NO_RESPONSE)
    response = as_user(case_manager).patch(
        f"/api/v1/followups/{attempt.pk}/", {"contact_outcome": "REACHED_ENGAGED"}, format="json"
    )
    assert response.status_code == 405


def test_a_case_manager_sees_her_caseloads_log_only(as_user, case_manager, other_case_manager, make_case, log):
    mine = log(make_case(case_manager, name="Mine"), ContactOutcome.REACHED_ENGAGED)
    log(make_case(other_case_manager, name="Theirs"), ContactOutcome.REACHED_ENGAGED)

    response = as_user(case_manager).get("/api/v1/followups/")
    assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]


def test_the_unverified_queue_is_scoped(as_user, completed_referral, other_case_manager):
    """M&E's queue is still §7-scoped: an aggregate is a disclosure, and so is a
    list of somebody else's youth."""
    response = as_user(other_case_manager).get("/api/v1/followups/unverified/")
    assert response.status_code == 200
    assert response.data["count"] == 0
