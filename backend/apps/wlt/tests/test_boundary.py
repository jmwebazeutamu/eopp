"""The module boundary — backlog S0.3, and the handoff's fifth "will bite" item.

> A facilitator who can see a group roster must not thereby see those women's
> youth-side case files. The join is one line of ORM. Test both directions.

Both directions are here. The join really is one line — a WLT member is a
`Youth`, and a `Youth` may hold a `Case` — so nothing about the schema prevents
it and only the access matrix does.
"""

import pytest

from apps.users.models import ACCESS_MATRIX, GroupScope, Role, Scope
from apps.users.permissions import scope_group_queryset
from apps.wlt.models import Group, MobilisationEvent
from apps.wlt.services import formation as formation_service

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# WLT staff cannot read case content
# ---------------------------------------------------------------------------


def test_a_facilitator_seeing_a_roster_cannot_open_those_women_s_case_files(
    as_user, facilitator, wlt_group, wlt_members, make_case, case_manager
):
    """The exact leak S0.3 names, tested on the same person from both sides."""
    member = wlt_members[0]
    case = make_case(case_manager, youth=member)

    roster = as_user(facilitator).get(f"/api/v1/wlt/groups/{wlt_group.pk}/members/")
    assert roster.status_code == 200
    assert any(str(row["person"]) == str(member.pk) for row in roster.data)

    assert as_user(facilitator).get("/api/v1/cases/").status_code == 403
    assert as_user(facilitator).get(f"/api/v1/cases/{case.pk}/").status_code == 403


def test_a_facilitator_cannot_read_the_youth_referral_list(as_user, facilitator):
    assert as_user(facilitator).get("/api/v1/referrals/").status_code == 403


def test_a_woreda_officer_cannot_read_case_content_either(as_user, woreda_officer):
    """Scope in the group domain does not become scope in the case domain."""
    assert as_user(woreda_officer).get("/api/v1/cases/").status_code == 403
    assert ACCESS_MATRIX[Role.WLT_WOREDA_OFFICER]["case_scope"] == Scope.NONE


# ---------------------------------------------------------------------------
# Youth staff cannot read WLT ledger data
# ---------------------------------------------------------------------------


def test_a_case_manager_cannot_read_wlt_groups_or_their_ledger(as_user, case_manager, wlt_group):
    assert as_user(case_manager).get("/api/v1/wlt/groups/").status_code == 403
    assert as_user(case_manager).get(f"/api/v1/wlt/groups/{wlt_group.pk}/ledger/").status_code == 403


def test_a_supervisor_cannot_read_wlt_groups(as_user, supervisor, wlt_group):
    assert as_user(supervisor).get("/api/v1/wlt/groups/").status_code == 403


def test_a_programme_manager_with_scope_all_still_has_no_group_scope(as_user, programme_manager, wlt_group):
    """`Scope.ALL` is a statement about case records, not about the platform.

    This is the mirror of the administrator test on the referral side: reading
    everything in one domain does not imply reading anything in the other.
    """
    assert ACCESS_MATRIX[Role.PROGRAMME_MANAGER]["group_scope"] == GroupScope.NONE
    assert as_user(programme_manager).get("/api/v1/wlt/groups/").status_code == 403


# ---------------------------------------------------------------------------
# Scoping inside the module
# ---------------------------------------------------------------------------


def test_a_facilitator_sees_only_the_groups_she_runs(as_user, facilitator, other_facilitator, wlt_group, wlt_locations):
    theirs = formation_service.open_draft(
        name="Another SHG", kebele=wlt_locations["kebele"], facilitator=other_facilitator
    )

    mine = as_user(facilitator).get("/api/v1/wlt/groups/")
    assert {row["id"] for row in mine.data["results"]} == {str(wlt_group.pk)}

    assert as_user(facilitator).get(f"/api/v1/wlt/groups/{theirs.pk}/").status_code == 404


def test_a_woreda_officer_sees_every_group_in_her_woreda(
    as_user, woreda_officer, facilitator, other_facilitator, wlt_group, wlt_locations
):
    other = formation_service.open_draft(
        name="Another SHG", kebele=wlt_locations["other_kebele"], facilitator=other_facilitator
    )
    response = as_user(woreda_officer).get("/api/v1/wlt/groups/")
    assert {row["id"] for row in response.data["results"]} == {str(wlt_group.pk), str(other.pk)}


def test_a_woreda_officer_sees_nothing_in_a_woreda_she_is_not_assigned_to(db, as_user, wlt_locations, facilitator):
    from apps.locations.models import Location, LocationLevel
    from apps.users.models import User

    elsewhere_woreda = Location.objects.create(
        code="ET-AM-SW-KX", name="Kutaber", level=LocationLevel.WOREDA, parent=wlt_locations["zone"]
    )
    elsewhere_kebele = Location.objects.create(
        code="ET-AM-SW-KX-01", name="Kutaber 01", level=LocationLevel.KEBELE, parent=elsewhere_woreda
    )
    formation_service.open_draft(name="Kutaber SHG", kebele=elsewhere_kebele, facilitator=facilitator)

    officer = User.objects.create_user(
        "wlt-elsewhere",
        "pw-Test-12345",
        full_name="Other Woreda Officer",
        role=Role.WLT_WOREDA_OFFICER,
        wlt_scope_location=wlt_locations["woreda"],
    )
    response = as_user(officer).get("/api/v1/wlt/groups/")
    assert all(row["kebele"] != str(elsewhere_kebele.pk) for row in response.data["results"])


def test_a_region_officer_sees_the_whole_region(as_user, region_officer, wlt_group):
    response = as_user(region_officer).get("/api/v1/wlt/groups/")
    assert str(wlt_group.pk) in {row["id"] for row in response.data["results"]}


def test_scoping_fails_closed_when_the_key_is_missing(db, wlt_group, wlt_locations):
    """A woreda officer with no assigned geography sees nothing, not everything.

    `User.clean` refuses to create one, so this is a backstop against a row
    written before that rule existed or by a direct database edit — the case
    where failing open would be a financial disclosure.
    """
    from apps.users.models import User

    unscoped = User(username="broken", full_name="Broken", role=Role.WLT_WOREDA_OFFICER)
    assert not scope_group_queryset(Group.objects.all(), unscoped).exists()


def test_a_facilitator_may_write_and_an_officer_may_not(as_user, facilitator, woreda_officer, wlt_locations):
    """Read and approve, not record. An officer who could post a ledger entry
    could also settle a discrepancy nobody witnessed."""
    # A group is drafted from an endorsed community meeting, so the payload
    # carries one. The kebele is not sent: it is derived from the meeting.
    event = MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"],
        held_on="2026-01-20",
        facilitator=facilitator,
        endorsement_obtained=True,
    )
    payload = {
        "name": "New SHG",
        "mobilisation_event": str(event.pk),
        "facilitator": str(facilitator.pk),
        "drafted_on": "2026-02-01",
    }
    assert as_user(facilitator).post("/api/v1/wlt/groups/", payload, format="json").status_code == 201
    assert as_user(woreda_officer).post("/api/v1/wlt/groups/", payload, format="json").status_code == 403
