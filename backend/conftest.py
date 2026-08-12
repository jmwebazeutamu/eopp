"""Shared pytest fixtures."""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.cases.models import Case
from apps.locations.models import Location, LocationLevel
from apps.users.models import Role, User
from apps.youth.models import Sex, Youth


@pytest.fixture
def locations(db):
    """A minimal slice of the hierarchy: one region, one zone, two woredas."""
    region = Location.objects.create(code="ET-OR", name="Oromia", level=LocationLevel.REGION)
    zone = Location.objects.create(code="ET-OR-ES", name="East Shewa", level=LocationLevel.ZONE, parent=region)
    adama = Location.objects.create(code="ET-OR-ES-ADAMA", name="Adama", level=LocationLevel.WOREDA, parent=zone)
    bishoftu = Location.objects.create(
        code="ET-OR-ES-BISHOFTU", name="Bishoftu", level=LocationLevel.WOREDA, parent=zone
    )
    return {"region": region, "zone": zone, "adama": adama, "bishoftu": bishoftu}


@pytest.fixture
def outreach_worker(db):
    return User.objects.create_user(
        "outreach1", "pw-Test-12345", full_name="Outreach One", role=Role.OUTREACH_WORKER, woreda_assignment=["Adama"]
    )


@pytest.fixture
def case_manager(db):
    return User.objects.create_user(
        "cm-a", "pw-Test-12345", full_name="Manager A", role=Role.CASE_MANAGER, woreda_assignment=["Adama"]
    )


@pytest.fixture
def other_case_manager(db):
    return User.objects.create_user(
        "cm-b", "pw-Test-12345", full_name="Manager B", role=Role.CASE_MANAGER, woreda_assignment=["Adama"]
    )


@pytest.fixture
def supervisor(db):
    return User.objects.create_user(
        "sup-a", "pw-Test-12345", full_name="Supervisor A", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )


@pytest.fixture
def programme_manager(db):
    return User.objects.create_user(
        "pm-a", "pw-Test-12345", full_name="Programme Manager", role=Role.PROGRAMME_MANAGER, woreda_assignment=[]
    )


@pytest.fixture
def system_admin(db):
    return User.objects.create_user(
        "admin-a", "pw-Test-12345", full_name="Sys Admin", role=Role.SYSTEM_ADMIN, woreda_assignment=[]
    )


@pytest.fixture
def make_youth(db, locations, outreach_worker):
    def _make(name="Abebe Bekele", woreda="Adama", age=22, **kwargs):
        return Youth.objects.create(
            full_name=name,
            sex=kwargs.pop("sex", Sex.MALE),
            date_of_birth=date.today() - timedelta(days=365 * age + 10),
            region="Oromia",
            zone="East Shewa",
            woreda=woreda,
            kebele=kwargs.pop("kebele", "Adama 01"),
            consent_given=True,
            consent_date=date.today(),
            registering_worker=outreach_worker,
            **kwargs,
        )

    return _make


@pytest.fixture
def make_case(db, make_youth):
    def _make(case_manager, name="Abebe Bekele", woreda="Adama", **kwargs):
        youth = kwargs.pop("youth", None) or make_youth(name=name, woreda=woreda)
        return Case.objects.create(youth=youth, case_manager=case_manager, woreda=woreda, **kwargs)

    return _make


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def as_user(api):
    def _login(user):
        api.force_authenticate(user=user)
        return api

    return _login


# --- Sprint 3: referral fixtures -------------------------------------------


@pytest.fixture
def taxonomy(db):
    """The spec §5 starter lists, loaded the same way production gets them."""
    from django.core.management import call_command

    call_command("seed_referral_taxonomy", verbosity=0)

    from apps.referrals.taxonomy import FailureReasonCode, OutcomeType, ReferralCategory

    return {
        "training": ReferralCategory.objects.get(code="TRAINING"),
        "employment": ReferralCategory.objects.get(code="EMPLOYMENT"),
        "enterprise": ReferralCategory.objects.get(code="ENTERPRISE"),
        "complementary": ReferralCategory.objects.get(code="COMPLEMENTARY_SERVICE"),
        "other_category": ReferralCategory.objects.get(code="OTHER"),
        "training_completion": OutcomeType.objects.get(code="TRAINING_COMPLETION"),
        "job_placement": OutcomeType.objects.get(code="JOB_PLACEMENT"),
        "other_outcome": OutcomeType.objects.get(code="OTHER"),
        "no_show": FailureReasonCode.objects.get(code="YOUTH_NO_SHOW"),
        "capacity": FailureReasonCode.objects.get(code="PARTNER_CAPACITY"),
        "other_failure": FailureReasonCode.objects.get(code="OTHER"),
    }


@pytest.fixture
def make_partner(db, locations):
    from apps.partners.models import Partner, PartnerType

    counter = {"n": 0}

    def _make(name=None, partner_type=None, woredas=None, **kwargs):
        counter["n"] += 1
        n = counter["n"]
        return Partner.objects.create(
            partner_name=name or f"Partner {n}",
            partner_type=partner_type or PartnerType.TVET_INSTITUTION,
            woreda_coverage=woredas or ["Adama"],
            contact_name=f"Contact {n}",
            phone=f"+25191100{n:04d}",
            email=f"partner{n}@example.et",
            **kwargs,
        )

    return _make


@pytest.fixture
def partner(make_partner):
    return make_partner(name="Adama Polytechnic College")


@pytest.fixture
def make_referral(db, taxonomy, partner, case_manager):
    """A referral in Pending Confirmation, created the way the API creates one."""
    from apps.referrals import services

    def _make(case, category=None, receiving_partner=None, initiated_by=None, **fields):
        return services.initiate_referral(
            case=case,
            referral_category=category or taxonomy["training"],
            receiving_partner=receiving_partner or partner,
            initiated_by=initiated_by or case_manager,
            **fields,
        )

    return _make
