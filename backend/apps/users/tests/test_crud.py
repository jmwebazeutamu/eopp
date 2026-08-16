"""CRUD-support endpoint tests — the assignment picker, account deactivation,
and the youth `without_case` filter that the create-case screen depends on.
"""

import pytest

from apps.users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Case-manager picker
# ---------------------------------------------------------------------------


def test_case_manager_can_list_assignable_managers(case_manager, other_case_manager, as_user):
    """§7 keeps user *management* with the admin, but assigning a case needs a picker."""
    response = as_user(case_manager).get("/api/v1/users/case-managers/")
    assert response.status_code == 200
    names = {row["full_name"] for row in response.data}
    assert {"Manager A", "Manager B"} <= names


def test_picker_exposes_no_sensitive_fields(case_manager, as_user):
    response = as_user(case_manager).get("/api/v1/users/case-managers/")
    assert set(response.data[0]) == {"id", "full_name", "woreda_assignment"}


def test_picker_excludes_non_case_manager_roles(case_manager, supervisor, system_admin, as_user):
    response = as_user(case_manager).get("/api/v1/users/case-managers/")
    names = {row["full_name"] for row in response.data}
    assert "Supervisor A" not in names
    assert "Sys Admin" not in names


def test_picker_excludes_suspended_accounts(case_manager, other_case_manager, as_user):
    other_case_manager.account_status = AccountStatus.SUSPENDED
    other_case_manager.save()
    response = as_user(case_manager).get("/api/v1/users/case-managers/")
    assert "Manager B" not in {row["full_name"] for row in response.data}


def test_picker_is_narrowed_to_overlapping_woredas(case_manager, as_user, db):
    """A manager in another woreda is not an assignable option."""
    User.objects.create_user(
        "cm-far", "pw-Test-12345", full_name="Far Manager", role=Role.CASE_MANAGER, woreda_assignment=["Mekelle"]
    )
    response = as_user(case_manager).get("/api/v1/users/case-managers/")
    assert "Far Manager" not in {row["full_name"] for row in response.data}


def test_system_admin_can_use_the_case_picker(system_admin, case_manager, as_user):
    """Follows from the §7 deviation of 2026-08-16 — see ACCESS_MATRIX.

    The picker is gated on case access, so widening the administrator to write
    cases necessarily hands them the assignment picker too: assigning a case is
    meaningless without seeing who may take it. Their scope is ALL, so no woreda
    narrowing applies and every active manager is offered.
    """
    response = as_user(system_admin).get("/api/v1/users/case-managers/")
    assert response.status_code == 200
    assert "Manager A" in {row["full_name"] for row in response.data}


# ---------------------------------------------------------------------------
# Accounts are deactivated, not deleted
# ---------------------------------------------------------------------------


def test_users_cannot_be_deleted(system_admin, case_manager, as_user):
    """PROTECT FKs would fail for an active user and silently succeed for a new
    one, removing an account the audit trail still references."""
    response = as_user(system_admin).delete(f"/api/v1/users/{case_manager.pk}/")
    assert response.status_code == 405


def test_deactivating_an_account_blocks_login(system_admin, case_manager, as_user, api):
    as_user(system_admin).patch(
        f"/api/v1/users/{case_manager.pk}/", {"account_status": AccountStatus.INACTIVE}, format="json"
    )
    api.force_authenticate(user=None)
    response = api.post(
        "/api/v1/users/token/", {"username": case_manager.username, "password": "pw-Test-12345"}, format="json"
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Youth without_case filter — feeds the "open a case" picker
# ---------------------------------------------------------------------------


def test_without_case_filter_lists_uncased_youth_for_woreda_roles(
    make_youth, make_case, outreach_worker, case_manager, as_user, locations
):
    """The picker is driven by a woreda-scoped role.

    §7 gives the outreach worker "Create; view own woreda" on case records, and
    that is the role this filter serves: registration and case opening.
    """
    uncased = make_youth(name="No Case Yet")
    make_case(case_manager, name="Has A Case")

    response = as_user(outreach_worker).get("/api/v1/youth/?without_case=true")
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [str(uncased.pk)]


def test_case_manager_cannot_browse_uncased_youth(make_youth, case_manager, as_user, locations):
    """A consequence of §7 worth pinning down.

    The case manager's youth scope resolves through `case__case_manager_id`, so
    a youth with no case matches nothing. Opening a case is therefore an
    outreach-worker or supervisor action, not a case-manager one — the UI puts
    the "New case" control accordingly.
    """
    make_youth(name="No Case Yet")
    response = as_user(case_manager).get("/api/v1/youth/?without_case=true")
    assert response.data["count"] == 0


def test_without_case_false_returns_only_youth_with_cases(make_youth, make_case, case_manager, as_user, locations):
    make_youth(name="No Case Yet")
    cased = make_case(case_manager, name="Has A Case")

    response = as_user(case_manager).get("/api/v1/youth/?without_case=false")
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [str(cased.youth.pk)]


def test_without_case_filter_still_respects_scope(make_youth, make_case, case_manager, other_case_manager, as_user):
    """The filter narrows within §7 scoping, never around it."""
    make_case(other_case_manager, name="Someone Elses")
    response = as_user(case_manager).get("/api/v1/youth/?without_case=false")
    assert response.data["count"] == 0


# ---------------------------------------------------------------------------
# Caseload on the user list
# ---------------------------------------------------------------------------


def test_user_list_carries_each_account_s_open_caseload(system_admin, case_manager, make_case, as_user):
    """§11 sets a caseload ceiling; an administrator cannot apply it unseen."""
    make_case(case_manager, name="One")
    make_case(case_manager, name="Two")

    response = as_user(system_admin).get("/api/v1/users/")
    row = next(item for item in response.data["results"] if item["username"] == case_manager.username)
    assert row["caseload_count"] == 2


def test_closed_cases_do_not_count_toward_the_caseload(system_admin, case_manager, make_case, as_user):
    from apps.cases.models import CaseStatus

    case = make_case(case_manager, name="Closed One")
    case.case_status = CaseStatus.EXITED
    case.save(update_fields=["case_status"])

    response = as_user(system_admin).get("/api/v1/users/")
    row = next(item for item in response.data["results"] if item["username"] == case_manager.username)
    assert row["caseload_count"] == 0


def test_the_user_list_stays_ordered_under_the_caseload_annotation(system_admin, case_manager, as_user):
    """Django drops Meta.ordering on an aggregate query, and unordered
    pagination silently repeats and skips rows between pages."""
    response = as_user(system_admin).get("/api/v1/users/")
    names = [row["full_name"] for row in response.data["results"]]
    assert names == sorted(names)
