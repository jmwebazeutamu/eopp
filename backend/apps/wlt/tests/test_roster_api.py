"""The roster over HTTP — listing it, adding a woman, and closing a membership.

The services underneath were tested from stage 1; what is here is the route
layer, which is what a facilitator actually reaches. `exit_member` in
particular was written, tested and then never routed, so the only way to close
a membership was a test or a shell.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.wlt.models import (
    BeneficiaryProfile,
    ExitReason,
    GroupMembership,
    Loan,
    LoanPurpose,
    LoanStatus,
    ServiceChargeBasis,
)
from apps.wlt.services import formation as formation_service

pytestmark = pytest.mark.django_db


def _roster(client, group):
    response = client.get(f"/api/v1/wlt/groups/{group.pk}/members/")
    assert response.status_code == 200
    return response.data


# ---------------------------------------------------------------------------
# Reading the roster
# ---------------------------------------------------------------------------


def test_the_roster_lists_every_member_with_her_join_date(as_user, facilitator, wlt_group, wlt_members):
    rows = _roster(as_user(facilitator), wlt_group)

    assert len(rows) == len(wlt_members)
    assert {row["full_name"] for row in rows} == {person.full_name for person in wlt_members}
    assert all(row["joined_on"] == "2025-12-20" for row in rows)
    assert all(row["exited_on"] is None for row in rows)


def test_a_woman_who_has_left_stays_on_the_roster_with_her_reason(as_user, facilitator, wlt_group, wlt_members):
    """The membership is a dated range, so an exit is a closed row, not a gone one.

    An indicator computed against March has to see the woman who left in April.
    """
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[-1])
    formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date(2026, 4, 1))

    rows = _roster(as_user(facilitator), wlt_group)
    exited = [row for row in rows if row["exited_on"] is not None]

    assert len(rows) == len(wlt_members)
    assert len(exited) == 1
    assert exited[0]["full_name"] == wlt_members[-1].full_name
    assert exited[0]["exit_reason"] == ExitReason.MOVED
    assert exited[0]["exit_reason_display"] == "Moved away"


# ---------------------------------------------------------------------------
# Adding a woman
# ---------------------------------------------------------------------------


def test_a_facilitator_adds_a_woman_from_the_candidate_pool(as_user, facilitator, wlt_group, make_wlt_member):
    joiner = make_wlt_member("Late Joiner")

    client = as_user(facilitator)
    pool = client.get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})
    assert pool.status_code == 200
    assert str(joiner.pk) in {str(row["person"]) for row in pool.data}

    created = client.post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(joiner.pk)})
    assert created.status_code == 201
    assert created.data["full_name"] == "Late Joiner"

    assert GroupMembership.objects.filter(group=wlt_group, person=joiner, exited_on__isnull=True).exists()


def test_the_pool_drops_a_woman_once_she_is_added(as_user, facilitator, wlt_group, make_wlt_member):
    joiner = make_wlt_member("Late Joiner")
    client = as_user(facilitator)

    client.post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(joiner.pk)})

    pool = client.get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})
    assert str(joiner.pk) not in {str(row["person"]) for row in pool.data}


def test_a_woman_who_left_a_group_returns_to_the_candidate_pool(as_user, facilitator, wlt_group, wlt_members):
    """The pool asks whether she is *currently* assigned, never whether she ever was.

    An earlier `wlt_memberships__isnull=True` made an exit permanent: a woman
    who moved away and came back could not be re-added by any screen.
    """
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0])
    formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date(2026, 4, 1))

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert str(wlt_members[0].pk) in {str(row["person"]) for row in pool.data}


def test_a_woman_never_in_any_group_is_unassigned(wlt_group, make_wlt_member):
    """The queryset directly, because the pool reads it and so does `candidate_pool`.

    `unassigned()` once compiled to a subquery whose LEFT JOIN gave a
    never-assigned woman a NULL `exited_on`, so she matched "has an open
    membership" and was excluded. Every profile in the database failed it.
    """
    fresh = make_wlt_member("Never Assigned")
    seated = wlt_group.current_members.first()

    pool = BeneficiaryProfile.objects.programme_eligible().verified().unassigned()
    in_pool = {profile.person_id for profile in pool}

    # She has never been in a group, so she is available.
    assert fresh.pk in in_pool
    # A woman currently on a roster is not — the condition the method exists for.
    assert seated.pk not in in_pool


def test_the_pool_never_offers_a_woman_the_service_would_refuse(as_user, facilitator, wlt_group, make_wlt_member):
    """Eligibility is filtered in the pool, not only enforced on the add."""
    ineligible = make_wlt_member("No ELS Grant", els_grant_received_on=None)

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})
    assert str(ineligible.pk) not in {str(row["person"]) for row in pool.data}

    refused = as_user(facilitator).post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(ineligible.pk)})
    assert refused.status_code == 400


# ---------------------------------------------------------------------------
# Closing a membership
# ---------------------------------------------------------------------------


def test_a_facilitator_closes_a_membership_with_a_reason(as_user, facilitator, wlt_group, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[-1])

    response = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/",
        {"reason": ExitReason.MARRIED_OUT, "note": "Moved to her husband's kebele."},
    )

    assert response.status_code == 200
    membership.refresh_from_db()
    assert membership.exited_on is not None
    assert membership.exit_reason == ExitReason.MARRIED_OUT
    assert membership.exit_note == "Moved to her husband's kebele."


def test_an_exit_with_no_reason_is_refused(as_user, facilitator, wlt_group, wlt_members):
    """The check constraint can only say "not blank". The route says which reasons exist."""
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[-1])

    blank = as_user(facilitator).post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/", {})
    unknown = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/", {"reason": "BORED"}
    )

    assert blank.status_code == 400
    assert unknown.status_code == 400
    membership.refresh_from_db()
    assert membership.exited_on is None


def test_a_woman_who_owes_on_a_loan_cannot_be_exited(as_user, facilitator, wlt_group, wlt_members):
    """A11, surfaced as a sentence rather than an IntegrityError."""
    borrower = wlt_members[0]
    Loan.objects.create(
        group=wlt_group,
        person=borrower,
        cycle_batch=1,
        principal_etb=Decimal("500.00"),
        charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        charge_rate=Decimal("0.0500"),
        purpose=LoanPurpose.IGA,
        disbursed_on=date(2026, 3, 2),
        due_on=date(2026, 6, 1),
        status=LoanStatus.DISBURSED,
    )
    membership = GroupMembership.objects.get(group=wlt_group, person=borrower)

    response = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/", {"reason": ExitReason.MOVED}
    )

    assert response.status_code == 400
    assert "500" in str(response.data)
    membership.refresh_from_db()
    assert membership.exited_on is None


def test_a_membership_cannot_be_exited_twice(as_user, facilitator, wlt_group, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[-1])
    path = f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/"

    assert as_user(facilitator).post(path, {"reason": ExitReason.MOVED}).status_code == 200
    again = as_user(facilitator).post(path, {"reason": ExitReason.DIED})

    assert again.status_code == 400
    membership.refresh_from_db()
    assert membership.exit_reason == ExitReason.MOVED


def test_a_membership_on_another_group_is_not_reachable_through_this_one(
    as_user, facilitator, wlt_group, wlt_locations, make_wlt_member
):
    """The membership id is looked up *through* the group, so it inherits its scoping."""
    other = formation_service.open_draft(
        name="Other SHG", kebele=wlt_locations["kebele"], facilitator=facilitator, on_date=date(2026, 1, 5)
    )
    outsider = make_wlt_member("Other Group Member")
    membership = formation_service.add_member(other, outsider, on_date=date(2026, 1, 6))

    response = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/", {"reason": ExitReason.MOVED}
    )

    assert response.status_code == 400
    membership.refresh_from_db()
    assert membership.exited_on is None


# ---------------------------------------------------------------------------
# Who may do it
# ---------------------------------------------------------------------------


def test_a_role_that_cannot_write_groups_may_read_the_roster_but_not_change_it(
    as_user, region_officer, wlt_group, wlt_members, make_wlt_member
):
    """`CanAccessGroups` allows every safe method and gates the rest on `group_write`."""
    client = as_user(region_officer)
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[-1])

    assert client.get(f"/api/v1/wlt/groups/{wlt_group.pk}/members/").status_code == 200
    assert (
        client.post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(make_wlt_member("X").pk)}).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/", {"reason": ExitReason.MOVED}
        ).status_code
        == 403
    )


def test_a_case_manager_cannot_reach_the_roster_at_all(as_user, case_manager, wlt_group):
    assert as_user(case_manager).get(f"/api/v1/wlt/groups/{wlt_group.pk}/members/").status_code == 403
