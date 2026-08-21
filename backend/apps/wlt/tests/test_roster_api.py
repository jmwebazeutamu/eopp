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
    assert str(joiner.pk) in {str(row["person"]) for row in pool.data["results"]}

    created = client.post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(joiner.pk)})
    assert created.status_code == 201
    assert created.data["full_name"] == "Late Joiner"

    assert GroupMembership.objects.filter(group=wlt_group, person=joiner, exited_on__isnull=True).exists()


def test_the_pool_drops_a_woman_once_she_is_added(as_user, facilitator, wlt_group, make_wlt_member):
    joiner = make_wlt_member("Late Joiner")
    client = as_user(facilitator)

    client.post(f"/api/v1/wlt/groups/{wlt_group.pk}/members/", {"person": str(joiner.pk)})

    pool = client.get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})
    assert str(joiner.pk) not in {str(row["person"]) for row in pool.data["results"]}


def test_a_woman_who_left_a_group_returns_to_the_candidate_pool(as_user, facilitator, wlt_group, wlt_members):
    """The pool asks whether she is *currently* assigned, never whether she ever was.

    An earlier `wlt_memberships__isnull=True` made an exit permanent: a woman
    who moved away and came back could not be re-added by any screen.
    """
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0])
    formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date(2026, 4, 1))

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert str(wlt_members[0].pk) in {str(row["person"]) for row in pool.data["results"]}


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
    assert str(ineligible.pk) not in {str(row["person"]) for row in pool.data["results"]}

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


# ---------------------------------------------------------------------------
# "Is she in a group?" on the register
# ---------------------------------------------------------------------------


def _profiles(client, **params):
    # A big page on purpose: these assertions are about a particular woman, and
    # a default page would silently drop her onto page two.
    response = client.get("/api/v1/wlt/profiles/", {"page_size": 200, **params})
    assert response.status_code == 200
    return response.data["results"]


def test_the_register_says_which_group_each_woman_is_in(as_user, facilitator, wlt_group, wlt_members):
    """The question the register is actually asked, answered on the row.

    Not derivable from `is_assignable`: a woman can be unassignable for four
    other reasons, so a blank there would name the wrong problem.
    """
    seated = _profiles(as_user(facilitator))
    row = next(r for r in seated if str(r["person"]) == str(wlt_members[0].pk))

    assert row["current_group"]["id"] == str(wlt_group.pk)
    assert row["current_group"]["name"] == wlt_group.name
    assert row["current_group"]["joined_on"] is not None


def test_a_woman_in_no_group_reports_null_rather_than_a_blank_name(
    as_user, facilitator, wlt_group, wlt_locations, make_wlt_member
):
    # `wlt_group` is not scenery: a facilitator's register is scoped to the
    # kebeles of the groups she runs, so with no group she sees no women at all.
    person = make_wlt_member("Unseated Woman")
    rows = _profiles(as_user(facilitator))
    row = next(r for r in rows if str(r["person"]) == str(person.pk))

    assert row["current_group"] is None


def test_an_exit_empties_the_column_immediately(as_user, facilitator, wlt_group, wlt_members):
    """Membership is a dated range, never a flag. She left, so she is not in it.

    Her closed row stays on the roster — February's attendance denominator is
    the roster as it stood then — but the register answers about today.
    """
    member = wlt_members[0]
    membership = GroupMembership.objects.get(person=member, group=wlt_group, exited_on__isnull=True)

    exited = as_user(facilitator).post(
        f"/api/v1/wlt/groups/{wlt_group.pk}/members/{membership.pk}/exit/",
        {"reason": ExitReason.MOVED},
    )
    assert exited.status_code in (200, 201)

    row = next(r for r in _profiles(as_user(facilitator)) if str(r["person"]) == str(member.pk))
    assert row["current_group"] is None


def test_in_group_false_is_the_women_waiting_to_be_seated(
    as_user, facilitator, wlt_group, wlt_members, make_wlt_member
):
    waiting = make_wlt_member("Waiting Woman")

    unseated = {str(r["person"]) for r in _profiles(as_user(facilitator), in_group="false")}
    seated = {str(r["person"]) for r in _profiles(as_user(facilitator), in_group="true")}

    assert str(waiting.pk) in unseated
    assert str(wlt_members[0].pk) in seated
    assert not (unseated & seated)


def test_the_group_column_costs_the_same_whether_or_not_she_is_in_a_group(
    as_user, facilitator, wlt_group, wlt_members, make_wlt_member
):
    """The property that matters, stated as a comparison rather than a budget.

    Twenty women in a group and twenty women in none must cost the same number
    of queries. If the prefetch stopped working, the seated list would cost
    twenty more — one `exists()` per row from `is_assignable`, which is what it
    used to do. A fixed ceiling would instead fail on any unrelated
    `select_related` somebody adds later.
    """
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client = as_user(facilitator)

    with CaptureQueriesContext(connection) as seated:
        client.get("/api/v1/wlt/profiles/", {"page_size": 200, "in_group": "true"})

    for index in range(20):
        make_wlt_member(f"Unseated {index:02d}")

    with CaptureQueriesContext(connection) as unseated:
        client.get("/api/v1/wlt/profiles/", {"page_size": 200, "in_group": "false"})

    assert len(seated.captured_queries) == len(unseated.captured_queries)


def test_an_empty_pool_says_how_many_women_wait_in_other_kebeles(
    as_user, facilitator, wlt_group, wlt_members, wlt_locations, make_wlt_member
):
    """The reported fault: the picker showed nothing and looked broken.

    A group recruits from its own kebele — it meets weekly in person — so the
    usual reason for an empty list is geography, not eligibility. The screen
    could not say so because the endpoint did not tell it.
    """
    # A second group of hers, so the other kebele is inside her scope at all.
    # Without one she cannot see those women, and must not be told they exist.
    formation_service.open_draft(
        name="Second SHG", kebele=wlt_locations["other_kebele"], facilitator=facilitator
    )
    make_wlt_member("Woman Elsewhere", kebele=wlt_locations["other_kebele"])

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    # Everyone eligible in this kebele is already seated by `wlt_group`.
    assert pool.data["results"] == []
    assert pool.data["kebele"]["name"] == wlt_group.kebele.name
    assert pool.data["waiting_elsewhere"] == 1


def test_the_count_of_women_elsewhere_excludes_the_ones_it_is_offering(
    as_user, facilitator, wlt_group, wlt_locations, make_wlt_member
):
    """`waiting_elsewhere` is elsewhere, not everywhere.

    Adding the two together has to give the whole waiting pool, or the message
    double-counts the women already on the list in front of you.
    """
    formation_service.open_draft(
        name="Second SHG", kebele=wlt_locations["other_kebele"], facilitator=facilitator
    )
    make_wlt_member("Here One")
    make_wlt_member("Here Two")
    make_wlt_member("There One", kebele=wlt_locations["other_kebele"])

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert {row["full_name"] for row in pool.data["results"]} == {"Here One", "Here Two"}
    assert pool.data["waiting_elsewhere"] == 1


def test_the_count_never_reports_women_outside_her_scope(
    as_user, facilitator, wlt_group, wlt_locations, make_wlt_member
):
    """"Elsewhere" means elsewhere *that she can see*.

    A facilitator's register is the kebeles of the groups she runs. Counting
    women in a kebele she has no group in would disclose the size of a
    population she is not entitled to read — an aggregate is still a
    disclosure — and would offer her a number she can do nothing about.
    """
    make_wlt_member("Invisible Woman", kebele=wlt_locations["other_kebele"])

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert pool.data["waiting_elsewhere"] == 0


def test_a_pool_with_no_kebele_asked_for_makes_no_claim_about_elsewhere(as_user, facilitator, wlt_group):
    """No kebele means no "somewhere else" to count, so it reports zero rather
    than a number that would mean something different from the same field
    when a kebele *was* named."""
    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/")

    assert pool.data["kebele"] is None
    assert pool.data["waiting_elsewhere"] == 0


def test_the_context_counts_are_scoped_like_every_other_aggregate(
    as_user, facilitator, wlt_group, wlt_members, wlt_locations, make_wlt_member
):
    """`registered_here` and `already_grouped_here` narrow the scoped queryset.

    They were briefly built on `BeneficiaryProfile.objects`, which counts women
    the caller may not read. "40 women registered here" told to somebody
    entitled to see four is a disclosure, not a hint — the same rule the
    dashboard states and `waiting_elsewhere` already followed.
    """
    # A woman in a kebele this facilitator runs no group in.
    make_wlt_member("Out Of Scope", kebele=wlt_locations["other_kebele"])

    pool = as_user(facilitator).get(
        "/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_locations["other_kebele"].pk)}
    )

    assert pool.data["registered_here"] == 0
    assert pool.data["already_grouped_here"] == 0


def test_the_context_counts_separate_nobody_registered_from_everybody_placed(
    as_user, facilitator, wlt_group, wlt_members
):
    """Two very different empty pools, and they need opposite next steps."""
    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert pool.data["registered_here"] == len(wlt_members)
    assert pool.data["already_grouped_here"] == len(wlt_members)


def test_a_seated_woman_is_counted_once_not_once_per_membership(
    as_user, facilitator, wlt_group, wlt_members
):
    """A membership join multiplies the row — the lesson `unassigned()` carries.

    She has one open membership and one closed one; a join would count her
    twice and report more women grouped here than are registered here.
    """
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0])
    formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date(2026, 4, 1))
    formation_service.add_member(wlt_group, wlt_members[0], on_date=date(2026, 5, 1))

    pool = as_user(facilitator).get("/api/v1/wlt/profiles/candidates/", {"kebele": str(wlt_group.kebele_id)})

    assert pool.data["already_grouped_here"] <= pool.data["registered_here"]
    assert pool.data["already_grouped_here"] == len(wlt_members)
