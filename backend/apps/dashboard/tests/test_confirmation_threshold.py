"""One threshold, one boundary rule, one overdue count.

Fixes 2.1, 2.2 and 2.3. The product held two values for the same standard and
two comparison operators over it, so a single referral could be within
threshold on the Results indicator and overdue in the my-work API at once, and
the same population reported as 10, 13 or 14 depending on which card asked.
"""

from datetime import date, timedelta

import pytest

from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.alerts.tasks import detect_overdue_confirmations
from apps.dashboard import queues
from apps.dashboard.rules import (
    confirmation_threshold_days,
    is_overdue_for_confirmation,
    is_within_confirmation_threshold,
)
from apps.dashboard.services import scoped_bases
from apps.dashboard.tiers import results_framework

pytestmark = pytest.mark.django_db


@pytest.fixture
def waited(taxonomy, make_case, make_referral, case_manager):
    """A pending referral that has been waiting an exact number of days."""

    def _waited(days, name=None):
        referral = make_referral(make_case(case_manager, name=name or f"Waited {days}"))
        referral.initiated_date = date.today() - timedelta(days=days)
        referral.save(update_fields=["initiated_date"])
        return referral

    return _waited


class TestTheBoundaryRule:
    def test_a_wait_of_exactly_the_threshold_is_within_it(self, settings):
        """Written down once: overdue means strictly greater. A partner who
        answers on day N has met a standard stated as "within N days"."""
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        assert is_within_confirmation_threshold(14) is True
        assert is_overdue_for_confirmation(14) is False

    def test_a_day_past_it_is_overdue(self, settings):
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        assert is_overdue_for_confirmation(15) is True
        assert is_within_confirmation_threshold(15) is False

    def test_the_two_are_exact_complements(self, settings):
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        for days in range(0, 30):
            assert is_within_confirmation_threshold(days) != is_overdue_for_confirmation(days)

    def test_there_is_one_threshold_not_two(self, settings):
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 21
        assert confirmation_threshold_days() == 21


class TestOneOverdueCount:
    def test_the_tile_the_woreda_card_and_the_alert_engine_agree(
        self, locations, taxonomy, settings, case_manager, waited
    ):
        """2.3. Three consumers, one population. They reported 10, 13 and 14
        over the same 24 referrals."""
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        for days in (0, 7, 13, 14, 15, 28, 45):
            waited(days)

        # 15, 28 and 45 are strictly beyond 14. Day 14 itself is not.
        assert queues.awaiting_over_threshold(case_manager) == 3

        detect_overdue_confirmations()
        raised = Alert.objects.filter(
            alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE, status=AlertStatus.OPEN
        ).count()
        assert raised == 3

    def test_a_referral_at_exactly_the_threshold_is_in_neither_population(
        self, locations, taxonomy, settings, case_manager, waited
    ):
        """The brief's acceptance test: one referral was in both."""
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
        waited(7, name="Exactly Seven")

        assert queues.awaiting_over_threshold(case_manager) == 0
        detect_overdue_confirmations()
        assert not Alert.objects.filter(alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE).exists()

    def test_moving_the_threshold_moves_every_consumer(self, locations, taxonomy, settings, case_manager, waited):
        for days in (5, 10, 20):
            waited(days)

        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
        assert queues.awaiting_over_threshold(case_manager) == 2
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        assert queues.awaiting_over_threshold(case_manager) == 1
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 30
        assert queues.awaiting_over_threshold(case_manager) == 0


class TestTheIndicatorUsesTheSameRule:
    def test_the_within_threshold_indicator_counts_the_boundary_as_within(
        self, locations, taxonomy, settings, programme_manager, case_manager, make_case, make_referral
    ):
        settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
        referral = make_referral(make_case(programme_manager, name="Answered On Day 14"))
        referral.initiated_date = date.today() - timedelta(days=90)
        referral.save(update_fields=["initiated_date"])
        from apps.referrals.models import ReferralStatus

        referral.transition_to(
            ReferralStatus.ACTIVE,
            actor=case_manager,
            confirmed_date=referral.initiated_date + timedelta(days=14),
        )

        youth, cases, referrals = scoped_bases(programme_manager)
        indicators = results_framework(youth, referrals, date.today(), 14)
        timeliness = [i for i in indicators if i["code"] == "confirmed_within_threshold"][0]
        assert timeliness["rate"]["n"] == 1


# ---------------------------------------------------------------------------
# Phase 3 — recorded is not verified
# ---------------------------------------------------------------------------


@pytest.fixture
def completed(taxonomy, make_case, make_referral, case_manager):
    """A mature completed referral with a chosen verification source."""

    def _completed(source, name=None):
        from apps.referrals.models import ReferralStatus

        referral = make_referral(
            make_case(case_manager, name=name or f"Outcome {source}"), category=taxonomy["employment"]
        )
        referral.initiated_date = date.today() - timedelta(days=90)
        referral.save(update_fields=["initiated_date"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["job_placement"],
            outcome_date=date.today(),
            verification_source=source,
        )
        return referral

    return _completed


class TestRecordedIsNotVerified:
    def test_a_self_reported_outcome_is_not_externally_verified(self, locations, taxonomy, completed):
        """3.1. A self-reported placement rate is an aspiration."""
        from apps.referrals.models import Referral, VerificationSource

        completed(VerificationSource.SELF_REPORTED)
        assert Referral.objects.with_recorded_outcome().count() == 1
        assert Referral.objects.externally_verified().count() == 0

    def test_a_blank_source_is_not_verified_either(self, locations, taxonomy, completed):
        """The safe direction. 8 rows carry free text that names no verifier."""
        from apps.referrals.models import Referral

        completed("")
        assert Referral.objects.with_recorded_outcome().count() == 1
        assert Referral.objects.externally_verified().count() == 0

    def test_an_employer_confirmation_is(self, locations, taxonomy, completed):
        from apps.referrals.models import Referral, VerificationSource

        referral = completed(VerificationSource.EMPLOYER_CONFIRMED)
        assert Referral.objects.externally_verified().count() == 1
        assert referral.is_externally_verified is True

    def test_loop_closure_reports_the_verified_rate_as_primary(self, locations, taxonomy, programme_manager, completed):
        """The card read 50% where the verified figure was 32%, because it
        tested `outcome_verified_by IS NOT NULL` — which only says a staff
        member signed the record off."""
        from apps.referrals.models import VerificationSource

        completed(VerificationSource.EMPLOYER_CONFIRMED)
        completed(VerificationSource.SELF_REPORTED)
        completed(VerificationSource.SELF_REPORTED)

        youth, cases, referrals = scoped_bases(programme_manager)
        indicators = results_framework(youth, referrals, date.today(), 14)
        loop = [i for i in indicators if i["code"] == "loop_closure"][0]

        # Primary is the verified subset: 1 of 3.
        assert loop["rate"]["n"] == 1
        # Recorded sits beside it, never instead of it: 3 of 3.
        assert loop["recorded"]["n"] == 3

    def test_the_monthly_tile_carries_both(self, locations, taxonomy, case_manager, completed):
        from apps.dashboard import queues
        from apps.referrals.models import VerificationSource

        completed(VerificationSource.PROVIDER_CONFIRMED)
        completed(VerificationSource.SELF_REPORTED)

        counts = queues.outcomes_verified(case_manager)
        assert counts == {"verified": 1, "recorded": 2}
