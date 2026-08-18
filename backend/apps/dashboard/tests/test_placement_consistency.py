"""Placement figures agree, or say what unit they are in.

Fixes 1.2 and 1.3. The defect was not arithmetic: four modules each restated
the placement filter, three counting referrals and one counting youth, so one
screen showed 59, 63, 60 and 70 for what a reader takes to be the same thing.
"""

from datetime import date, timedelta

import pytest

from apps.dashboard.services import metric_cards, scoped_bases, woreda_comparison
from apps.dashboard.tiers import cumulative_placements, disaggregation, results_framework
from apps.referrals.models import ReferralStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(taxonomy, make_referral, case_manager):
    def _place(case, on=None):
        referral = make_referral(case, category=taxonomy["employment"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=on or date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["job_placement"],
            outcome_date=on or date.today(),
        )
        return referral

    return _place


class TestOneNumberAcrossFourPages:
    def test_every_placement_figure_counts_the_same_youth(
        self, locations, taxonomy, programme_manager, make_case, place
    ):
        """A youth placed twice is one young person in work. Counting referrals
        made the gender split read 63 while the woreda table beneath it read 59."""
        twice = make_case(programme_manager, name="Placed Twice")
        place(twice)
        place(twice)
        place(make_case(programme_manager, name="Placed Once"))

        youth, cases, referrals = scoped_bases(programme_manager)
        headline = len(referrals.placed_youth_ids())

        assert referrals.placements().count() == 3  # referrals
        assert headline == 2  # youth

        cards = metric_cards(youth, referrals, date.today())
        assert cards["gender_split"]["placed_total"] == headline
        assert cards["placements_this_quarter"]["value"] == headline
        assert sum(row["placed"] for row in woreda_comparison(youth, referrals)) == headline

        cumulative = cumulative_placements(referrals, date.today())
        assert cumulative["series"][-1]["cumulative"] == headline

    def test_every_placement_figure_states_its_unit(self, locations, programme_manager, make_case, place):
        place(make_case(programme_manager, name="Placed"))
        youth, cases, referrals = scoped_bases(programme_manager)

        cards = metric_cards(youth, referrals, date.today())
        assert cards["gender_split"]["unit"] == "youth"
        assert cards["placements_this_quarter"]["unit"] == "youth"
        assert cumulative_placements(referrals, date.today())["unit"] == "youth"
        assert all(row["unit"] == "youth" for row in woreda_comparison(youth, referrals))

    def test_the_disaggregation_agrees_with_the_headline(
        self, locations, taxonomy, programme_manager, make_case, place
    ):
        for index in range(3):
            place(make_case(programme_manager, name=f"Placed {index}"))
        youth, cases, referrals = scoped_bases(programme_manager)

        cuts = disaggregation(youth, referrals, date.today())
        headline = len(referrals.placed_youth_ids())
        for cut in cuts:
            assert sum(row["placed"] for row in cut["rows"]) == headline, cut["label"]

    def test_the_results_indicator_agrees_too(self, locations, taxonomy, programme_manager, make_case, place):
        place(make_case(programme_manager, name="Placed"))
        youth, cases, referrals = scoped_bases(programme_manager)

        indicators = results_framework(youth, referrals, date.today(), 14)
        employed = [i for i in indicators if i["code"] == "employed"][0]
        assert employed["value"] == len(referrals.placed_youth_ids())


class TestCumulativeChart:
    def test_the_last_point_equals_the_headline(self, locations, taxonomy, programme_manager, make_case, place):
        """The brief's acceptance test for 1.3, stated exactly."""
        for index in range(4):
            place(make_case(programme_manager, name=f"Placed {index}"))
        youth, cases, referrals = scoped_bases(programme_manager)

        cumulative = cumulative_placements(referrals, date.today())
        assert cumulative["series"][-1]["cumulative"] == len(referrals.placed_youth_ids())

    def test_placements_older_than_the_window_are_carried_in_not_dropped(
        self, locations, taxonomy, programme_manager, make_case, place
    ):
        """A total labelled "to date" that omits the earliest placements is
        simply wrong. This is the defect that closed the line at 60 against a
        headline of 59 over a true 63."""
        old = date.today() - timedelta(days=800)
        place(make_case(programme_manager, name="Placed Long Ago"), on=old)
        place(make_case(programme_manager, name="Placed Recently"))

        youth, cases, referrals = scoped_bases(programme_manager)
        cumulative = cumulative_placements(referrals, date.today(), months=6)

        assert cumulative["opening_balance"] == 1
        assert cumulative["series"][0]["cumulative"] >= 1
        assert cumulative["series"][-1]["cumulative"] == len(referrals.placed_youth_ids()) == 2

    def test_a_youth_enters_the_series_once_on_their_first_placement(
        self, locations, taxonomy, programme_manager, make_case, place
    ):
        case = make_case(programme_manager, name="Placed Twice")
        place(case, on=date.today() - timedelta(days=60))
        place(case)

        youth, cases, referrals = scoped_bases(programme_manager)
        cumulative = cumulative_placements(referrals, date.today())
        assert cumulative["series"][-1]["cumulative"] == 1
        assert sum(point["placed"] for point in cumulative["series"]) + cumulative["opening_balance"] == 1


# ---------------------------------------------------------------------------
# Phase 5 — the small ones
# ---------------------------------------------------------------------------


class TestConfirmationInvariant:
    def test_a_refused_transition_leaves_no_confirmation_behind(
        self, locations, taxonomy, case_manager, make_case, make_referral, settings
    ):
        """A confirmed_date on a referral nobody confirmed.

        The §6.3 cap refuses the third concurrent confirmation. The database
        rolls back, but the *instance* kept the caller's field updates, so the
        next transition on the same object wrote a confirmation date for a
        confirmation that never happened.
        """
        from apps.referrals.models import ConfirmationStatus

        case = make_case(case_manager, name="At The Cap")
        for _ in range(2):
            referral = make_referral(case, category=taxonomy["training"])
            referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

        third = make_referral(case, category=taxonomy["employment"])
        with pytest.raises(Exception):
            third.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

        # The instance must not still be carrying the refused values.
        assert third.confirmed_date is None

        # And the cancel that follows must not persist them.
        third.transition_to(ReferralStatus.CANCELLED, actor=case_manager, notes="Withdrawn.")
        third.refresh_from_db()
        assert third.confirmed_date is None
        assert third.confirmation_status == ConfirmationStatus.PENDING

    def test_the_database_refuses_the_combination_outright(
        self, locations, taxonomy, case_manager, make_case, make_referral
    ):
        """The write path that produced it was subtle enough to survive review,
        so the invariant is enforced where it cannot be bypassed."""
        from django.db import IntegrityError, transaction

        from apps.referrals.models import ConfirmationStatus, Referral

        referral = make_referral(make_case(case_manager, name="Invariant"))
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                Referral.objects.filter(pk=referral.pk).update(
                    confirmation_status=ConfirmationStatus.PENDING, confirmed_date=date.today()
                )
