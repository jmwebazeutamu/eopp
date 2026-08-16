"""Tests for the mini-dashboard counter summaries.

Every list screen carries a counter row that doubles as a filter, so these
counts are load-bearing twice over: they tell a case manager where the work is,
and clicking one is how they get there.
"""

import pytest

from apps.cases.models import CaseStatus
from apps.users.models import AccountStatus

pytestmark = pytest.mark.django_db


def counters(response):
    return {row["label"]: row["count"] for row in response.data["counters"]}


# ---------------------------------------------------------------------------
# The counts must add up
# ---------------------------------------------------------------------------


def test_case_counters_sum_to_the_total(case_manager, make_case, as_user):
    """A regression test for a real fault: CaseViewSet's queryset carries
    annotations, and grouping an annotated queryset adds them to the GROUP BY,
    which split each status across several rows and dropped all but the last.
    The symptom was a total of 14 over counters summing to 4."""
    for _ in range(3):
        make_case(case_manager)
    stalled = make_case(case_manager, name="Stalled One")
    stalled.case_status = CaseStatus.STALLED
    stalled.save(update_fields=["case_status"])

    response = as_user(case_manager).get("/api/v1/cases/summary/")
    assert response.status_code == 200
    assert response.data["total"] == 4
    assert sum(row["count"] for row in response.data["counters"]) == 4
    assert counters(response)["Stalled"] == 1
    assert counters(response)["Active"] == 3


def test_user_counters_are_not_inflated_by_the_caseload_join(system_admin, case_manager, make_case, as_user):
    """UserViewSet annotates a Count over managed_cases. A naive group-by would
    count the joined rows, reporting one case manager as fourteen."""
    from apps.users.models import User

    for _ in range(5):
        make_case(case_manager)

    response = as_user(system_admin).get("/api/v1/users/summary/")
    assert counters(response)["Youth case manager"] == 1
    assert response.data["total"] == User.objects.count()


def test_referral_counters_sum_to_the_total(make_case, make_referral, case_manager, as_user, taxonomy):
    case = make_case(case_manager)
    make_referral(case)
    make_referral(case, category=taxonomy["employment"])

    response = as_user(case_manager).get("/api/v1/referrals/summary/")
    assert response.data["total"] == 2
    assert sum(row["count"] for row in response.data["counters"]) == 2


# ---------------------------------------------------------------------------
# Each counter names the filter it applies
# ---------------------------------------------------------------------------


def test_a_counter_carries_the_query_parameter_that_reproduces_it(case_manager, make_case, as_user):
    """The counter is only useful if clicking it returns exactly what it counted."""
    stalled = make_case(case_manager, name="Stalled One")
    stalled.case_status = CaseStatus.STALLED
    stalled.save(update_fields=["case_status"])
    make_case(case_manager, name="Active One")

    summary = as_user(case_manager).get("/api/v1/cases/summary/")
    row = next(item for item in summary.data["counters"] if item["label"] == "Stalled")

    listing = as_user(case_manager).get(f"/api/v1/cases/?{row['param']}={row['value']}")
    assert listing.data["count"] == row["count"] == 1


def test_youth_counters_reproduce_through_without_case(case_manager, make_youth, make_case, as_user):
    make_case(case_manager, youth=make_youth(name="Has A Case"))
    make_youth(name="No Case Yet")

    summary = as_user(case_manager).get("/api/v1/youth/summary/")
    row = next(item for item in summary.data["counters"] if item["label"] == "No case yet")
    listing = as_user(case_manager).get(f"/api/v1/youth/?{row['param']}={row['value']}")
    assert listing.data["count"] == row["count"]


# ---------------------------------------------------------------------------
# Scope and search
# ---------------------------------------------------------------------------


def test_counters_respect_the_caller_s_scope(case_manager, other_case_manager, make_case, as_user):
    """§7 again: a counter that counted the whole programme would leak the size
    of another manager's caseload."""
    make_case(case_manager)
    make_case(other_case_manager, name="Someone Else")

    response = as_user(case_manager).get("/api/v1/cases/summary/")
    assert response.data["total"] == 1


def test_counters_narrow_with_a_search(case_manager, make_case, as_user):
    """The counters answer "how do these matches break down?", so search applies."""
    make_case(case_manager, name="Abebe Bekele")
    make_case(case_manager, name="Chaltu Tadesse")

    response = as_user(case_manager).get("/api/v1/cases/summary/?search=Chaltu")
    assert response.data["total"] == 1


def test_partner_counters_cover_both_capacity_and_paperwork(make_partner, case_manager, as_user):
    """A partner can be accepting referrals on an unsigned MOU — that gap is the
    reason both dimensions are on the screen, so the counters overlap by design
    and are not expected to sum to the total."""
    make_partner(name="Signed and open", mou_status="SIGNED")
    make_partner(name="Open, no paperwork", mou_status="NONE")

    response = as_user(case_manager).get("/api/v1/partners/summary/")
    assert counters(response)["Accepting referrals"] == 2
    assert counters(response)["Signed"] == 1


def test_empty_roles_are_dropped_from_the_user_counters(system_admin, as_user):
    """Ten roles, most of them empty on a pilot of twenty, would bury the rest."""
    response = as_user(system_admin).get("/api/v1/users/summary/")
    assert all(row["count"] > 0 for row in response.data["counters"])


def test_suspended_accounts_get_their_own_counter(system_admin, case_manager, as_user):
    case_manager.account_status = AccountStatus.SUSPENDED
    case_manager.save(update_fields=["account_status"])

    response = as_user(system_admin).get("/api/v1/users/summary/")
    assert counters(response)["Suspended"] == 1


def test_summaries_need_authentication(api):
    for url in ["/api/v1/cases/summary/", "/api/v1/referrals/summary/", "/api/v1/youth/summary/"]:
        assert api.get(url).status_code == 401
