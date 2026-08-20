"""WLT fixtures.

`wlt_group` rebuilds the handoff's `sql/900` seed through the **service layer**
rather than by inserting rows: twenty women, bylaws, three officers, twelve
weekly meetings each closing on a balanced till with every member contributing
ETB 20. That is 12 × 20 × 20 = ETB 4,800, which is what assertion A3 checks.

Going through the services is the point. Rows inserted directly would test the
constraints and nothing else; a fixture built the way the field builds one also
tests that the field's route produces the numbers the assertions expect.
"""

from datetime import date, timedelta

import pytest
from django.core.management import call_command

from apps.locations.models import Location, LocationLevel
from apps.users.models import Role, User
from apps.wlt.models import (
    AttendanceStatus,
    BeneficiaryProfile,
    EnrolmentRoute,
    MeetingCadence,
    OfficeRole,
    ServiceChargeBasis,
    VerificationStatus,
)
from apps.wlt.services import formation as formation_service
from apps.wlt.services import ledger as ledger_service
from apps.youth.models import PsnpStatus, Sex, Youth

FIRST_MEETING = date(2026, 1, 6)
CONTRIBUTION = 20


@pytest.fixture
def wlt_policy(db, wlt_locations):
    """The seeded policy layer, loaded the way production gets it.

    Depends on the locations because the allocation rows point at regions: with
    no Amhara row the seed writes no allocation, and the ceiling tests would
    pass for the wrong reason.
    """
    call_command("seed_wlt_policy", verbosity=0)
    call_command("seed_wlt_taxonomy", verbosity=0)


@pytest.fixture
def wlt_locations(db):
    region = Location.objects.create(code="ET-AM", name="Amhara", level=LocationLevel.REGION)
    zone = Location.objects.create(code="ET-AM-SW", name="South Wollo", level=LocationLevel.ZONE, parent=region)
    woreda = Location.objects.create(code="ET-AM-SW-DZ", name="Dessie Zuria", level=LocationLevel.WOREDA, parent=zone)
    kebele = Location.objects.create(
        code="ET-AM-SW-DZ-01", name="Dessie Zuria 01", level=LocationLevel.KEBELE, parent=woreda
    )
    other_kebele = Location.objects.create(
        code="ET-AM-SW-DZ-02", name="Dessie Zuria 02", level=LocationLevel.KEBELE, parent=woreda
    )
    return {
        "region": region,
        "zone": zone,
        "woreda": woreda,
        "kebele": kebele,
        "other_kebele": other_kebele,
    }


@pytest.fixture
def facilitator(db, wlt_locations):
    return User.objects.create_user("wlt-fac", "pw-Test-12345", full_name="Facilitator One", role=Role.WLT_FACILITATOR)


@pytest.fixture
def other_facilitator(db, wlt_locations):
    return User.objects.create_user("wlt-fac2", "pw-Test-12345", full_name="Facilitator Two", role=Role.WLT_FACILITATOR)


@pytest.fixture
def woreda_officer(db, wlt_locations):
    return User.objects.create_user(
        "wlt-woreda",
        "pw-Test-12345",
        full_name="Woreda Officer",
        role=Role.WLT_WOREDA_OFFICER,
        wlt_scope_location=wlt_locations["woreda"],
    )


@pytest.fixture
def second_woreda_officer(db, wlt_locations):
    return User.objects.create_user(
        "wlt-woreda2",
        "pw-Test-12345",
        full_name="Second Woreda Officer",
        role=Role.WLT_WOREDA_OFFICER,
        wlt_scope_location=wlt_locations["woreda"],
    )


@pytest.fixture
def region_officer(db, wlt_locations):
    return User.objects.create_user(
        "wlt-region",
        "pw-Test-12345",
        full_name="Region Officer",
        role=Role.WLT_REGION_OFFICER,
        wlt_scope_location=wlt_locations["region"],
    )


@pytest.fixture
def make_wlt_member(db, wlt_locations, facilitator):
    """A verified, programme-eligible woman in the pilot kebele."""

    def _make(name, kebele=None, **profile_fields):
        kebele = kebele or wlt_locations["kebele"]
        person = Youth.objects.create(
            full_name=name,
            sex=Sex.FEMALE,
            date_of_birth=date(1990, 1, 1),
            region=wlt_locations["region"].name,
            zone=wlt_locations["zone"].name,
            woreda=wlt_locations["woreda"].name,
            kebele=kebele.name,
            psnp_status=PsnpStatus.ENROLLED,
            consent_given=True,
            consent_date=date(2025, 11, 1),
            registering_worker=facilitator,
        )
        defaults = {
            "els_completed_on": date(2025, 11, 1),
            "els_grant_received_on": date(2025, 12, 1),
            "literacy_level": "BASIC",
            "has_device": True,
            "enrolment_route": EnrolmentRoute.IMPORT,
            "verification_status": VerificationStatus.VERIFIED,
            "verified_on": date(2025, 12, 2),
            "psnp_kebele": kebele,
            "psnp_woreda": wlt_locations["woreda"],
        }
        defaults.update(profile_fields)
        BeneficiaryProfile.objects.create(person=person, **defaults)
        return person

    return _make


@pytest.fixture
def wlt_members(make_wlt_member):
    """Twenty women, as `sql/900` seeds."""
    return [make_wlt_member(f"Member {index:02d}") for index in range(1, 21)]


@pytest.fixture
def wlt_draft(db, wlt_policy, wlt_locations, facilitator, wlt_members):
    """A constituted group: roster, bylaws, three officers. Not yet active."""
    group = formation_service.open_draft(
        name="Temsalet SHG",
        kebele=wlt_locations["kebele"],
        facilitator=facilitator,
        on_date=date(2025, 12, 15),
    )
    for person in wlt_members:
        formation_service.add_member(group, person, on_date=date(2025, 12, 20))

    formation_service.record_bylaws(
        group,
        effective_from=date(2026, 1, 1),
        recorded_by=facilitator,
        meeting_cadence=MeetingCadence.WEEKLY,
        meeting_day="Monday",
        contribution_etb=CONTRIBUTION,
        service_charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        service_charge_rate="0.0500",
        officer_rotation_months=12,
        max_concurrent_loans=5,
        reserve_buffer_pct=10,
        clauses_local_language="Two signatories, chair and treasurer.",
    )
    for role, person in zip((OfficeRole.CHAIR, OfficeRole.SECRETARY, OfficeRole.TREASURER), wlt_members, strict=False):
        formation_service.elect_officer(group, person=person, role=role, from_date=date(2026, 1, 1))

    formation_service.constitute(group, on_date=date(2026, 1, 2), actor=facilitator)
    return group


def run_meeting(group, members, *, held_on, contribution=CONTRIBUTION, actor=None):
    """One full weekly meeting: attendance, savings, balanced close."""
    meeting = ledger_service.open_meeting(group, held_on=held_on, recorded_by=actor)
    ledger_service.record_attendance(meeting, [(person, AttendanceStatus.PRESENT) for person in members])
    for person in members:
        ledger_service.record_savings(meeting, person=person, amount_etb=contribution, actor=actor)
    expected = ledger_service.expected_cash(meeting)
    ledger_service.close_meeting(meeting, counted_cash_etb=expected, actor=actor)
    return meeting


@pytest.fixture
def wlt_group(db, wlt_draft, wlt_members, facilitator):
    """The `sql/900` group: active, at P1, twelve closed meetings, ETB 4,800 saved."""
    run_meeting(wlt_draft, wlt_members, held_on=FIRST_MEETING, actor=facilitator)
    formation_service.activate(wlt_draft, on_date=FIRST_MEETING, actor=facilitator)

    for week in range(1, 12):
        run_meeting(wlt_draft, wlt_members, held_on=FIRST_MEETING + timedelta(weeks=week), actor=facilitator)

    wlt_draft.refresh_from_db()
    return wlt_draft
