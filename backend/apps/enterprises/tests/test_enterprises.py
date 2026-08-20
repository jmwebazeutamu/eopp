"""Enterprise — spec §4.8, Sprint 6.

Three claims this entity is careful not to make, and one test each: a grant
disbursed is not a business trading, a business trading is not a business that
survived, and a milestone that was missed does not disappear.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.enterprises import services
from apps.enterprises.models import (
    BusinessPlanStatus,
    Enterprise,
    MarketLinkageStatus,
    MilestoneStatus,
    RegistrationStatus,
    SupportType,
)
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def officer(db):
    return User.objects.create_user(
        "eo-1", "pw-Test-12345", full_name="Enterprise Officer", role=Role.ENTERPRISE_OFFICER
    )


@pytest.fixture
def other_officer(db):
    return User.objects.create_user("eo-2", "pw-Test-12345", full_name="Second Officer", role=Role.ENTERPRISE_OFFICER)


@pytest.fixture
def make_enterprise(db, officer, make_referral, taxonomy):
    def _make(case, recorded_by=None, **fields):
        fields.setdefault("business_name", "Hana's Poultry")
        fields.setdefault("sector", "Livestock")
        fields.setdefault("source_referral", make_referral(case, category=taxonomy["enterprise"]))
        return services.open_enterprise(case=case, recorded_by=recorded_by or officer, **fields)

    return _make


def _approve(enterprise):
    return services.set_plan_status(enterprise, status=BusinessPlanStatus.APPROVED)


# ---------------------------------------------------------------------------
# Plan and disbursement
# ---------------------------------------------------------------------------


def test_a_revision_request_is_not_a_rejection(make_case, case_manager, make_enterprise):
    """Most first plans come back for revision. Filing that as a rejection would
    report a coaching workload as a failure rate."""
    enterprise = make_enterprise(make_case(case_manager))
    services.set_plan_status(enterprise, status=BusinessPlanStatus.REVISION_REQUESTED)

    assert enterprise.business_plan_status == BusinessPlanStatus.REVISION_REQUESTED
    assert enterprise.business_plan_status not in BusinessPlanStatus.approved_statuses()


def test_an_enterprise_requires_a_source_referral(make_case, case_manager, officer):
    with pytest.raises(ValidationError) as caught:
        services.open_enterprise(case=make_case(case_manager), recorded_by=officer, business_name="Test", sector="Food")
    assert "source_referral" in caught.value.message_dict


def test_only_enterprise_or_finance_referrals_may_create_an_enterprise(
    make_case, case_manager, officer, make_referral, taxonomy
):
    case = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.open_enterprise(
            case=case,
            recorded_by=officer,
            business_name="Test",
            sector="Food",
            source_referral=make_referral(case, category=taxonomy["training"]),
        )
    assert "source_referral" in caught.value.message_dict


def test_money_cannot_be_disbursed_against_an_unapproved_plan(make_case, case_manager, make_enterprise):
    """Either a data error or a control failure, and both want catching when
    somebody types it rather than in an audit."""
    enterprise = make_enterprise(make_case(case_manager))
    with pytest.raises(ValidationError):
        services.record_disbursement(enterprise, amount=5000, support_type=SupportType.GRANT)


def test_a_disbursement_needs_an_amount_and_a_kind(make_case, case_manager, make_enterprise):
    """A grant and a loan are different instruments with different consequences
    for the youth; one number covering both says nothing about either."""
    enterprise = _approve(make_enterprise(make_case(case_manager)))
    with pytest.raises(ValidationError):
        services.record_disbursement(enterprise, amount=5000, support_type=SupportType.NONE)
    with pytest.raises(ValidationError):
        services.record_disbursement(enterprise, amount=None, support_type=SupportType.GRANT)


def test_disbursement_moves_the_case_to_placed(make_case, case_manager, make_enterprise):
    from apps.cases.models import CaseStatus

    case = make_case(case_manager)
    enterprise = _approve(make_enterprise(case))
    services.record_disbursement(enterprise, amount=5000, support_type=SupportType.GRANT)
    case.refresh_from_db()

    assert case.case_status == CaseStatus.PLACED


def test_a_grant_disbursed_is_not_a_business_trading(make_case, case_manager, make_enterprise):
    """A programme that reports its own transfer as the youth's result is
    reporting its activity back to itself."""
    enterprise = _approve(make_enterprise(make_case(case_manager)))
    services.record_disbursement(enterprise, amount=5000, support_type=SupportType.GRANT)

    assert enterprise.has_support
    assert enterprise.started_trading_on is None
    assert enterprise.market_linkage_status == MarketLinkageStatus.NONE
    assert Enterprise.objects.trading().count() == 0


def test_trading_is_its_own_date(make_case, case_manager, make_enterprise):
    enterprise = _approve(make_enterprise(make_case(case_manager)))
    services.record_disbursement(
        enterprise, amount=5000, support_type=SupportType.GRANT, disbursed_on=date.today() - timedelta(days=30)
    )
    services.record_trading(enterprise, started_on=date.today() - timedelta(days=5))

    assert enterprise.started_trading_on != enterprise.disbursement_date
    assert Enterprise.objects.trading().count() == 1


def test_a_registration_number_belongs_to_a_registered_business(make_case, case_manager, make_enterprise):
    enterprise = make_enterprise(make_case(case_manager))
    enterprise.business_registration_number = "ET-12345"
    enterprise.business_registration_status = RegistrationStatus.IN_PROGRESS
    with pytest.raises(ValidationError):
        enterprise.full_clean()


def test_not_required_is_a_real_registration_answer(make_case, case_manager, make_enterprise):
    """Many youth enterprises operate below the threshold. Forcing them into
    "not registered" would report informality as non-compliance."""
    enterprise = make_enterprise(make_case(case_manager), business_registration_status=RegistrationStatus.NOT_REQUIRED)
    enterprise.full_clean()
    assert Enterprise.objects.registered().count() == 0


# ---------------------------------------------------------------------------
# Milestones — §4.8's sub-table
# ---------------------------------------------------------------------------


def test_a_missed_milestone_is_recorded_with_its_reason(make_case, case_manager, make_enterprise):
    """A plan whose missed milestones disappear reads as a plan that went well."""
    enterprise = make_enterprise(make_case(case_manager))
    milestone = services.add_milestone(
        enterprise, milestone_name="Register with the woreda", target_date=date.today() - timedelta(days=10)
    )
    services.miss_milestone(milestone, reason="The woreda office was closed for the season.")

    assert milestone.status == MilestoneStatus.MISSED
    assert "closed" in milestone.note
    assert enterprise.milestones.count() == 1


def test_a_missed_milestone_needs_a_reason(make_case, case_manager, make_enterprise):
    enterprise = make_enterprise(make_case(case_manager))
    milestone = services.add_milestone(enterprise, milestone_name="Buy stock", target_date=date.today())
    with pytest.raises(ValidationError):
        services.miss_milestone(milestone, reason="  ")


def test_an_achieved_milestone_carries_its_date(make_case, case_manager, make_enterprise):
    enterprise = make_enterprise(make_case(case_manager))
    milestone = services.add_milestone(enterprise, milestone_name="Buy stock", target_date=date.today())
    services.achieve_milestone(milestone)

    assert milestone.status == MilestoneStatus.ACHIEVED
    assert milestone.completion_date == date.today()


def test_a_milestone_is_settled_once(make_case, case_manager, make_enterprise):
    enterprise = make_enterprise(make_case(case_manager))
    milestone = services.add_milestone(enterprise, milestone_name="Buy stock", target_date=date.today())
    services.achieve_milestone(milestone)
    with pytest.raises(ValidationError):
        services.miss_milestone(milestone, reason="Changed my mind.")


def test_overdue_milestones_are_counted_on_the_enterprise(make_case, case_manager, make_enterprise):
    enterprise = make_enterprise(make_case(case_manager))
    services.add_milestone(enterprise, milestone_name="Late", target_date=date.today() - timedelta(days=5))
    services.add_milestone(enterprise, milestone_name="Future", target_date=date.today() + timedelta(days=5))

    assert enterprise.milestones_overdue == 1


# ---------------------------------------------------------------------------
# Survival
# ---------------------------------------------------------------------------


def test_survival_counts_only_enterprises_old_enough_to_have_failed(make_case, case_manager, make_enterprise):
    """Including a business disbursed last week would report it as a failure it
    has had no chance to be."""
    old = _approve(make_enterprise(make_case(case_manager, name="Old")))
    services.record_disbursement(
        old, amount=5000, support_type=SupportType.GRANT, disbursed_on=date.today() - timedelta(days=250)
    )
    new = _approve(make_enterprise(make_case(case_manager, name="New")))
    services.record_disbursement(
        new, amount=5000, support_type=SupportType.GRANT, disbursed_on=date.today() - timedelta(days=7)
    )

    surviving, mature = services.survival_inputs(Enterprise.objects.all(), months=6)
    assert (surviving, mature) == (1, 1)


def test_a_closed_business_needs_a_reason_and_leaves_the_survivors(make_case, case_manager, make_enterprise):
    enterprise = _approve(make_enterprise(make_case(case_manager)))
    services.record_disbursement(
        enterprise, amount=5000, support_type=SupportType.GRANT, disbursed_on=date.today() - timedelta(days=250)
    )
    with pytest.raises(ValidationError):
        services.close_enterprise(enterprise, reason="   ")

    services.close_enterprise(enterprise, reason="Stock was lost in the flood.")
    surviving, mature = services.survival_inputs(Enterprise.objects.all(), months=6)
    assert (surviving, mature) == (0, 1)


# ---------------------------------------------------------------------------
# §7 scoping — the last LINKED role
# ---------------------------------------------------------------------------


def test_an_enterprise_officer_sees_the_records_she_made(
    as_user, officer, other_officer, make_case, case_manager, make_enterprise
):
    mine = make_enterprise(make_case(case_manager, name="Mine"), recorded_by=officer)
    make_enterprise(make_case(case_manager, name="Theirs"), recorded_by=other_officer)

    response = as_user(officer).get("/api/v1/enterprises/")
    assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]


def test_an_enterprise_officer_reaches_the_case_behind_her_own_record(
    as_user, officer, make_case, case_manager, make_enterprise
):
    """The §7 LINKED scope her role has carried since Sprint 0 with nothing to
    resolve it through."""
    case = make_case(case_manager)
    make_enterprise(case, recorded_by=officer)

    response = as_user(officer).get("/api/v1/cases/")
    assert [row["id"] for row in response.data["results"]] == [str(case.pk)]


def test_disbursement_cannot_be_patched_onto_an_enterprise(as_user, case_manager, make_case, make_enterprise):
    """It would produce a disbursement no control saw and a case status nobody
    derived."""
    enterprise = make_enterprise(make_case(case_manager))
    as_user(case_manager).patch(
        f"/api/v1/enterprises/{enterprise.pk}/",
        {"grant_or_loan_amount": "9000.00", "disbursement_date": date.today().isoformat()},
        format="json",
    )
    enterprise.refresh_from_db()

    assert enterprise.disbursement_date is None


def test_the_awaiting_disbursement_queue_lists_approved_plans_with_no_money(
    as_user, case_manager, make_case, make_enterprise
):
    waiting = _approve(make_enterprise(make_case(case_manager, name="Waiting")))
    paid = _approve(make_enterprise(make_case(case_manager, name="Paid")))
    services.record_disbursement(paid, amount=5000, support_type=SupportType.GRANT)

    response = as_user(case_manager).get("/api/v1/enterprises/awaiting-disbursement/")
    assert [row["id"] for row in response.data] == [str(waiting.pk)]


def test_the_api_refuses_a_category_not_flagged_for_enterprise(
    as_user, case_manager, make_case, make_referral, taxonomy
):
    """The rule has to hold on the route people use.

    `perform_create` saves through the serializer, and a `ModelSerializer` does
    not run `full_clean` — so the check in `clean()` was not enforced here.
    """
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["training"])

    response = as_user(case_manager).post(
        "/api/v1/enterprises/",
        {"source_referral": str(referral.pk), "business_name": "Wrong Category", "sector": "Food"},
        format="json",
    )

    assert response.status_code == 400
    assert "source_referral" in response.data


def test_an_administrator_can_widen_which_categories_open_an_enterprise(
    case_manager, make_case, make_referral, taxonomy
):
    """The flag is configuration (§9), not a tuple in `apps.enterprises.models`."""
    coaching = taxonomy["training"].__class__.objects.get(code="COACHING")
    coaching.creates_enterprise = True
    coaching.save(update_fields=["creates_enterprise"])

    case = make_case(case_manager)
    enterprise = services.open_enterprise(
        case=case,
        recorded_by=case_manager,
        source_referral=make_referral(case, category=coaching),
        business_name="Widened",
        sector="Food",
    )

    assert enterprise.pk is not None


def test_an_enterprise_created_through_the_api_derives_its_case_from_the_referral(
    as_user, case_manager, make_case, make_referral, taxonomy
):
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["enterprise"])
    response = as_user(case_manager).post(
        "/api/v1/enterprises/",
        {
            "source_referral": str(referral.pk),
            "business_name": "Derived Case Enterprise",
            "sector": "Food",
        },
        format="json",
    )

    assert response.status_code == 201
    assert str(response.data["case"]) == str(case.pk)
