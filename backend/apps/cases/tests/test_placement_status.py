"""Placement: one definition, and case status derived from it.

Fixes 1.1 and 1.2 of the dashboard consistency brief. Before this, four modules
each restated the placement filter — three counting referrals, one counting
youth — and nothing connected any of them to `case_status = PLACED`, so one
screen could show three different placement totals.
"""

from datetime import date

import pytest

from apps.cases.models import Case, CaseStatus
from apps.referrals.models import Referral, ReferralStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def place(taxonomy, make_referral, case_manager):
    def _place(case, outcome=None):
        referral = make_referral(case, category=taxonomy["employment"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=outcome or taxonomy["job_placement"],
            outcome_date=date.today(),
        )
        return referral

    return _place


class TestOneDefinition:
    def test_placements_is_the_only_definition(self, locations, taxonomy, case_manager, make_case, place):
        place(make_case(case_manager, name="In Work"))
        assert Referral.objects.placements().count() == 1

    def test_a_completed_non_placement_outcome_is_not_a_placement(
        self, locations, taxonomy, case_manager, make_case, make_referral
    ):
        """Finishing a course closes a referral without putting anyone in work."""
        referral = make_referral(make_case(case_manager, name="Studied"), category=taxonomy["training"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["training_completion"],
            outcome_date=date.today(),
        )
        assert Referral.objects.placements().count() == 0

    def test_youth_is_the_unit_for_a_youth_placed_twice(
        self, locations, taxonomy, case_manager, make_case, place
    ):
        """Two placements for one young person is one person in work."""
        case = make_case(case_manager, name="Placed Twice")
        place(case)
        place(case, outcome=taxonomy["job_placement"])

        assert Referral.objects.placements().count() == 2
        assert len(Referral.objects.placed_youth_ids()) == 1


class TestStatusFollowsTheOutcome:
    def test_recording_a_placement_moves_the_case_to_placed(
        self, locations, taxonomy, case_manager, make_case, place
    ):
        case = make_case(case_manager, name="Gets A Job")
        assert case.case_status == CaseStatus.ACTIVE

        place(case)

        case.refresh_from_db()
        assert case.case_status == CaseStatus.PLACED

    def test_it_happens_through_the_api_path_too(
        self, locations, taxonomy, case_manager, make_case, make_referral, as_user
    ):
        """The derivation lives in `transition_to`, so it cannot be bypassed by
        going through the endpoint instead of the service."""
        case = make_case(case_manager, name="Via The API")
        referral = make_referral(case, category=taxonomy["employment"])
        client = as_user(case_manager)
        client.post(f"/api/v1/referrals/{referral.pk}/confirm/", {"confirmed_by": "Ato Bekele"}, format="json")

        response = client.post(
            f"/api/v1/referrals/{referral.pk}/complete/",
            {"outcome_type": "JOB_PLACEMENT", "outcome_date": str(date.today())},
            format="json",
        )
        assert response.status_code == 200

        case.refresh_from_db()
        assert case.case_status == CaseStatus.PLACED

    def test_a_non_placement_outcome_leaves_the_status_alone(
        self, locations, taxonomy, case_manager, make_case, make_referral
    ):
        case = make_case(case_manager, name="Studied Only")
        referral = make_referral(case, category=taxonomy["training"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["training_completion"],
            outcome_date=date.today(),
        )

        case.refresh_from_db()
        assert case.case_status != CaseStatus.PLACED


class TestReconcileCommand:
    def test_it_reports_without_changing_anything(self, locations, taxonomy, case_manager, make_case, place, capsys):
        case = make_case(case_manager, name="Backlog")
        place(case)
        # Simulate the pre-derivation backlog.
        Case.objects.filter(pk=case.pk).update(case_status=CaseStatus.ACTIVE)

        from django.core.management import call_command

        call_command("reconcile_case_placement")
        case.refresh_from_db()
        assert case.case_status == CaseStatus.ACTIVE
        assert "Report only" in capsys.readouterr().out

    def test_apply_promotes_the_backlog(self, locations, taxonomy, case_manager, make_case, place):
        case = make_case(case_manager, name="Backlog")
        place(case)
        Case.objects.filter(pk=case.pk).update(case_status=CaseStatus.ACTIVE)

        from django.core.management import call_command

        call_command("reconcile_case_placement", apply=True)
        case.refresh_from_db()
        assert case.case_status == CaseStatus.PLACED

    def test_it_never_demotes_a_hand_set_placement(self, locations, case_manager, make_case):
        """§4.2 lets a case manager set PLACED by hand, and a youth may have been
        placed through a route the platform never recorded. Overwriting that to
        tidy a dashboard would destroy a human decision."""
        case = make_case(case_manager, name="Placed By Hand")
        Case.objects.filter(pk=case.pk).update(case_status=CaseStatus.PLACED)

        from django.core.management import call_command

        call_command("reconcile_case_placement", apply=True)
        case.refresh_from_db()
        assert case.case_status == CaseStatus.PLACED
