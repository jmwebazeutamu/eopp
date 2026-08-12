"""Partner tests — spec §4.11, and the §4.12 partner-staff link."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.partners.models import MouStatus, Partner, PartnerType
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def partner(locations):
    return Partner.objects.create(
        partner_name="Adama Polytechnic College",
        partner_type=PartnerType.TVET_INSTITUTION,
        woreda_coverage=["Adama"],
        contact_name="Tigist Bekele",
        phone="+251911111111",
        email="tvet@example.et",
    )


@pytest.fixture
def partner_staff(partner):
    return User.objects.create_user(
        "partner1",
        "pw-Test-12345",
        full_name="Partner Staff",
        role=Role.PARTNER_STAFF,
        partner=partner,
    )


# ---------------------------------------------------------------------------
# Model rules
# ---------------------------------------------------------------------------


def test_partner_needs_at_least_one_woreda(locations):
    """A partner covering nothing can never be matched to a case."""
    partner = Partner(
        partner_name="Nowhere Ltd",
        partner_type=PartnerType.EMPLOYER,
        woreda_coverage=[],
        contact_name="X",
        phone="+251900000000",
        email="x@example.et",
    )
    with pytest.raises(ValidationError) as exc:
        partner.clean()
    assert "woreda_coverage" in exc.value.message_dict


def test_signed_mou_requires_a_date(partner):
    partner.mou_status = MouStatus.SIGNED
    partner.mou_date = None
    with pytest.raises(ValidationError) as exc:
        partner.clean()
    assert "mou_date" in exc.value.message_dict


def test_inactive_partner_cannot_receive_referrals(partner):
    assert partner.can_receive_referrals is True
    partner.active_status = False
    assert partner.can_receive_referrals is False


def test_covering_filters_by_woreda(partner, locations):
    Partner.objects.create(
        partner_name="Bishoftu Metal Works",
        partner_type=PartnerType.EMPLOYER,
        woreda_coverage=["Bishoftu"],
        contact_name="Y",
        phone="+251900000001",
        email="y@example.et",
    )
    assert [p.partner_name for p in Partner.objects.covering("Adama")] == ["Adama Polytechnic College"]


def test_partner_name_is_unique_within_a_type(partner):
    with pytest.raises(IntegrityError), transaction.atomic():
        Partner.objects.create(
            partner_name="Adama Polytechnic College",
            partner_type=PartnerType.TVET_INSTITUTION,
            woreda_coverage=["Adama"],
            contact_name="Z",
            phone="+251900000002",
            email="z@example.et",
        )


# ---------------------------------------------------------------------------
# User.partner consistency — spec §4.12
# ---------------------------------------------------------------------------


def test_partner_staff_must_have_a_partner(db):
    user = User(username="ps", full_name="No Partner", role=Role.PARTNER_STAFF)
    with pytest.raises(ValidationError) as exc:
        user.clean()
    assert "partner" in exc.value.message_dict


def test_non_partner_role_cannot_have_a_partner(partner):
    user = User(username="cm", full_name="Manager", role=Role.CASE_MANAGER, partner=partner)
    with pytest.raises(ValidationError) as exc:
        user.clean()
    assert "partner" in exc.value.message_dict


def test_partner_staff_with_a_partner_is_valid(partner_staff):
    partner_staff.clean()  # must not raise
    assert partner_staff.partner.partner_name == "Adama Polytechnic College"


def test_deleting_a_partner_with_staff_is_blocked(partner, partner_staff):
    """PROTECT: removing a partner must not silently delete accounts the audit
    trail points at."""
    from django.db.models import ProtectedError

    with pytest.raises(ProtectedError):
        partner.delete()


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_case_manager_can_read_but_not_write_partners(partner, case_manager, as_user):
    client = as_user(case_manager)
    assert client.get("/api/v1/partners/").status_code == 200
    response = client.patch(f"/api/v1/partners/{partner.pk}/", {"phone": "+251999999999"}, format="json")
    assert response.status_code == 403


def test_programme_manager_can_write_partners(partner, programme_manager, as_user):
    response = as_user(programme_manager).patch(
        f"/api/v1/partners/{partner.pk}/", {"phone": "+251999999999"}, format="json"
    )
    assert response.status_code == 200, response.data


def test_unknown_woreda_in_coverage_is_rejected(locations, programme_manager, as_user):
    response = as_user(programme_manager).post(
        "/api/v1/partners/",
        {
            "partner_name": "Ghost Trainers",
            "partner_type": PartnerType.TVET_INSTITUTION,
            "woreda_coverage": ["Atlantis"],
            "contact_name": "Q",
            "phone": "+251900000003",
            "email": "q@example.et",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "woreda_coverage" in response.data


def test_partners_can_be_filtered_by_woreda(partner, locations, case_manager, as_user):
    Partner.objects.create(
        partner_name="Bishoftu Only",
        partner_type=PartnerType.EMPLOYER,
        woreda_coverage=["Bishoftu"],
        contact_name="B",
        phone="+251900000004",
        email="b@example.et",
    )
    response = as_user(case_manager).get("/api/v1/partners/?woreda=Adama")
    names = [row["partner_name"] for row in response.data["results"]]
    assert names == ["Adama Polytechnic College"]


def test_partners_cannot_be_deleted(partner, programme_manager, as_user):
    assert as_user(programme_manager).delete(f"/api/v1/partners/{partner.pk}/").status_code == 405


def test_creating_partner_staff_without_a_partner_is_rejected(system_admin, as_user):
    response = as_user(system_admin).post(
        "/api/v1/users/",
        {
            "username": "ps2",
            "full_name": "Partner Staff Two",
            "role": Role.PARTNER_STAFF,
            "password": "pw-Test-12345-long",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "partner" in response.data


def test_creating_partner_staff_with_a_partner_succeeds(partner, system_admin, as_user):
    response = as_user(system_admin).post(
        "/api/v1/users/",
        {
            "username": "ps3",
            "full_name": "Partner Staff Three",
            "role": Role.PARTNER_STAFF,
            "partner": str(partner.pk),
            "password": "pw-Test-12345-long",
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["partner_name"] == "Adama Polytechnic College"


def test_mou_date_is_required_for_a_signed_mou_via_api(partner, programme_manager, as_user):
    response = as_user(programme_manager).patch(
        f"/api/v1/partners/{partner.pk}/", {"mou_status": MouStatus.SIGNED}, format="json"
    )
    assert response.status_code == 400
    assert "mou_date" in response.data


def test_signed_mou_with_a_date_is_accepted(partner, programme_manager, as_user):
    response = as_user(programme_manager).patch(
        f"/api/v1/partners/{partner.pk}/",
        {"mou_status": MouStatus.SIGNED, "mou_date": str(date.today())},
        format="json",
    )
    assert response.status_code == 200, response.data
