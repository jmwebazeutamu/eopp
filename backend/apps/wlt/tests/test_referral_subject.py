"""Stage 0: the polymorphic referral subject — assertions A15 to A20.

The one change in the whole plan that touches live core code, so the youth-side
regression suite the migration runbook asks for is here too: same rows, same
scoping, same behaviour, before and after.

One departure from the runbook worth recording. Its eight stages exist to swap
`person_id` for `subject_person_id` on a live table — backfill, dual-write,
parity check, cut over, drop. None of that applies here, because `case` was not
replaced: it became one of five subject slots and every existing row already
satisfies the new constraint. The migration adds columns and a check; there is no
window in which a referral has two subjects or none.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.referrals.models import Referral, ReferralStatus, SubjectType
from apps.referrals.taxonomy import ReferralCategory
from apps.wlt.services import linkage as linkage_service

pytestmark = pytest.mark.django_db


@pytest.fixture
def wlt_categories(db):
    from django.core.management import call_command

    call_command("seed_wlt_taxonomy", verbosity=0)
    return {
        "service": ReferralCategory.objects.get(code="wlt-service-referral"),
        "protection": ReferralCategory.objects.get(code="wlt-protection-referral"),
    }


# ---------------------------------------------------------------------------
# A15 to A17 — exactly one subject
# ---------------------------------------------------------------------------


def test_a15_a_service_linkage_is_a_referral_with_a_group_subject(wlt_group, wlt_categories, make_partner, facilitator):
    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    referral = linkage_service.create_service_referral(
        subject=wlt_group, category=wlt_categories["service"], partner=provider, actor=facilitator
    )
    referral.refresh_from_db()
    assert referral.subject_type == SubjectType.GROUP
    assert referral.subject == wlt_group
    assert referral.case_id is None


def test_a16_a_referral_cannot_have_two_subjects(
    wlt_group, wlt_categories, make_partner, facilitator, make_case, case_manager
):
    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    case = make_case(case_manager)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Referral.objects.create(
                referral_category=wlt_categories["service"],
                receiving_partner=provider,
                initiated_by=facilitator,
                case=case,
                subject_group=wlt_group,
            )


def test_a17_a_referral_cannot_have_zero_subjects(wlt_categories, make_partner, facilitator):
    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Referral.objects.create(
                referral_category=wlt_categories["service"],
                receiving_partner=provider,
                initiated_by=facilitator,
            )


def test_deleting_a_group_with_a_referral_is_prevented_by_the_foreign_key(
    wlt_group, wlt_categories, make_partner, facilitator
):
    """The referential integrity a GenericForeignKey cannot give (decision D4)."""
    from django.db.models import ProtectedError

    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    linkage_service.create_service_referral(
        subject=wlt_group, category=wlt_categories["service"], partner=provider, actor=facilitator
    )
    with pytest.raises(ProtectedError):
        wlt_group.delete()


# ---------------------------------------------------------------------------
# A18 to A20 — safeguarding
# ---------------------------------------------------------------------------


def test_a18_a_protection_referral_cannot_be_raised_against_a_group(
    wlt_group, wlt_categories, make_partner, facilitator
):
    """Handbook §3.6 puts GBV on the meeting agenda. This is what stops a
    disclosure landing on a group timeline: not a convention, a constraint."""
    provider = make_partner(name="Woreda Women's Affairs", woredas=["Dessie Zuria"])
    with pytest.raises(ValidationError):
        linkage_service.create_service_referral(
            subject=wlt_group, category=wlt_categories["protection"], partner=provider, actor=facilitator
        )
    assert not Referral.objects.filter(referral_category=wlt_categories["protection"]).exists()


def test_a18_the_model_refuses_it_too_when_the_service_is_bypassed(
    wlt_group, wlt_categories, make_partner, facilitator
):
    provider = make_partner(name="Woreda Women's Affairs", woredas=["Dessie Zuria"])
    referral = Referral(
        referral_category=wlt_categories["protection"],
        receiving_partner=provider,
        initiated_by=facilitator,
        subject_group=wlt_group,
    )
    with pytest.raises(ValidationError) as caught:
        referral.full_clean(exclude=["subject_type"])
    assert "referral_category" in caught.value.message_dict


def test_a19_the_same_protection_referral_is_permitted_for_a_person(
    wlt_members, wlt_categories, make_partner, facilitator
):
    provider = make_partner(name="Woreda Women's Affairs", woredas=["Dessie Zuria"])
    referral = linkage_service.create_service_referral(
        subject=wlt_members[0], category=wlt_categories["protection"], partner=provider, actor=facilitator
    )
    referral.refresh_from_db()
    assert referral.subject_type == SubjectType.YOUTH


def test_a20_a_credit_facility_cannot_take_a_group_subject(wlt_group, make_partner, facilitator, wlt_policy):
    """The pilot rule, and the clearest finding in the Ethiopian savings-group
    literature. Enforced by the taxonomy row rather than by a type check, so
    lifting it is an administrator's decision."""
    from apps.wlt.services.linkage import LinkageError

    provider = make_partner(name="Amhara Credit and Savings", woredas=["Dessie Zuria"])
    with pytest.raises(LinkageError):
        linkage_service.propose(linkage_type="credit_facility", subject=wlt_group, provider=provider, actor=facilitator)


def test_an_empty_allowed_list_means_case_only_and_not_anything(db, taxonomy):
    """A category configured before subject types existed is not unrestricted.

    Reading an empty list as "anything" would open the safeguarding rule the
    moment somebody cleared the field, which is the failure mode worth spending
    a test on.
    """
    category = taxonomy["training"]
    category.allowed_subject_types = []
    category.save()

    assert category.permits(SubjectType.CASE)
    assert not category.permits(SubjectType.GROUP)


# ---------------------------------------------------------------------------
# The youth-side regression the runbook asks for
# ---------------------------------------------------------------------------


def test_a_youth_referral_still_resolves_renders_and_transitions(make_case, make_referral, case_manager, taxonomy):
    case = make_case(case_manager)
    referral = make_referral(case)
    referral.refresh_from_db()

    assert referral.subject_type == SubjectType.CASE
    assert referral.subject == case
    assert referral.subject_label == case.youth.full_name
    assert str(referral)

    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    assert referral.status == ReferralStatus.ACTIVE


def test_the_youth_referral_list_does_not_show_group_referrals(
    as_user, case_manager, make_case, make_referral, wlt_group, wlt_categories, make_partner, facilitator
):
    """The highest-risk item in the whole plan, per the migration runbook:
    referral visibility now resolves through two scoping paths, and a leak
    between the modules would appear here first."""
    case = make_case(case_manager)
    make_referral(case)
    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    linkage_service.create_service_referral(
        subject=wlt_group, category=wlt_categories["service"], partner=provider, actor=facilitator
    )

    response = as_user(case_manager).get("/api/v1/referrals/")
    assert response.status_code == 200
    subjects = {row.get("subject_type", "CASE") for row in response.data["results"]}
    assert subjects == {"CASE"}


def test_an_administrator_reading_every_referral_still_sees_no_group_referrals(
    as_user, system_admin, make_case, make_referral, case_manager, wlt_group, wlt_categories, make_partner, facilitator
):
    """`Scope.ALL` widens *which cases*, not *which modules*.

    The administrator's 2026-08-16 widening gives full case and referral access.
    It does not make the youth referral screen — built around a case and a young
    person — the place a savings group's bank linkage appears.
    """
    case = make_case(case_manager)
    make_referral(case)
    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    linkage_service.create_service_referral(
        subject=wlt_group, category=wlt_categories["service"], partner=provider, actor=facilitator
    )

    response = as_user(system_admin).get("/api/v1/referrals/")
    assert response.data["count"] == 1


def test_the_alert_engine_ignores_group_subject_referrals(
    wlt_group, wlt_categories, make_partner, facilitator, settings
):
    """An Alert names a case, and a group-subject referral has none. Before
    `youth_side()` this raised `AttributeError` on the first sweep after a
    linkage was created."""
    from apps.alerts.tasks import detect_overdue_confirmations

    provider = make_partner(name="Woreda Health Office", woredas=["Dessie Zuria"])
    referral = linkage_service.create_service_referral(
        subject=wlt_group, category=wlt_categories["service"], partner=provider, actor=facilitator
    )
    Referral.objects.filter(pk=referral.pk).update(initiated_date=date(2020, 1, 1))

    assert detect_overdue_confirmations() == 0
