"""RBAC boundary tests — spec §7, required by the §10.1 Definition of Done.

The queryset-scoping tests use a recording double rather than a real model,
because the entities these scopes apply to (Case, Referral) land in Sprints 1
and 3. Testing the mixin's decision logic now means the rules are already
pinned when those viewsets are wired to it.
"""

import pytest
from rest_framework.test import APIRequestFactory

from apps.users.models import ACCESS_MATRIX, AccountStatus, Role, Scope, User
from apps.users.permissions import CanAccessCases, CanAccessReferrals, IsOperational, ScopedQuerySetMixin

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class RecordingQuerySet:
    """Captures filter calls so scope decisions can be asserted without a model."""

    def __init__(self):
        self.filters = None
        self.is_none = False

    def filter(self, **kwargs):
        clone = RecordingQuerySet()
        clone.filters = kwargs
        return clone

    def none(self):
        clone = RecordingQuerySet()
        clone.is_none = True
        return clone


class ScopedView(ScopedQuerySetMixin):
    def __init__(self, **attrs):
        for key, value in attrs.items():
            setattr(self, key, value)


def make_user(role, woredas=None, pk="00000000-0000-0000-0000-000000000001", **kwargs):
    """An unsaved User — these tests exercise pure logic, no database needed."""
    return User(
        id=pk, username=f"u-{role}", full_name="Test User", role=role, woreda_assignment=woredas or [], **kwargs
    )


# ---------------------------------------------------------------------------
# Access matrix
# ---------------------------------------------------------------------------


def test_access_matrix_covers_every_role():
    """Spec §7 defines ten roles. A role missing here would silently fall back."""
    assert set(ACCESS_MATRIX) == set(Role)
    assert len(Role) == 10


def test_system_admin_has_full_access():
    """Deviation from §7, decided 2026-08-16 — see the ACCESS_MATRIX comment.

    §7 as written gives this role no case content. The programme asked for full
    access instead, so the administrator reads and writes every case and referral
    in every woreda. Pinned here so the departure is visible in the test names
    rather than only in a diff.
    """
    admin = make_user(Role.SYSTEM_ADMIN)
    assert admin.case_scope() == Scope.ALL
    assert admin.referral_scope() == Scope.ALL
    assert admin.can_write_cases()
    assert admin.can_write_referrals()


def test_an_unlisted_role_still_gets_nothing():
    """The fallback fails closed, independently of what any real role may do.

    `User.access` returns NO_ACCESS for a role the matrix does not cover. It used
    to return the system administrator's row, which was safe only while that row
    was empty; widening the administrator would otherwise have turned every
    unrecognised role into a full-access one.
    """
    stray = make_user("NOT_A_ROLE")
    assert stray.case_scope() == Scope.NONE
    assert stray.referral_scope() == Scope.NONE
    assert not stray.can_write_cases()
    assert not stray.can_write_referrals()

    view = ScopedView(scope_kind="case")
    assert view.apply_scope(RecordingQuerySet(), stray).is_none is True


@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OUTREACH_WORKER, Scope.OWN_WOREDA),
        (Role.CASE_MANAGER, Scope.OWN_CASELOAD),
        (Role.TRAINER, Scope.LINKED),
        (Role.SUPERVISOR, Scope.OWN_WOREDA),
        (Role.PROGRAMME_MANAGER, Scope.ALL),
        (Role.MNE_STAFF, Scope.ALL),
    ],
)
def test_case_scope_matches_spec_table(role, expected):
    assert make_user(role).case_scope() == expected


def test_outreach_worker_cannot_write_referrals():
    """§7 gives the outreach worker 'View only' on referrals."""
    user = make_user(Role.OUTREACH_WORKER, woredas=["Woreda A"])
    assert user.can_write_cases() is True  # intake and registration
    assert user.can_write_referrals() is False


def test_supervisor_is_read_only():
    """§7: supervisors oversee; they do not edit case or referral records."""
    user = make_user(Role.SUPERVISOR, woredas=["Woreda A"])
    assert user.can_write_cases() is False
    assert user.can_write_referrals() is False


def test_partner_staff_may_update_referrals():
    """§7: 'Referral receipt confirmation, service recording, outcome feedback'."""
    assert make_user(Role.PARTNER_STAFF).can_write_referrals() is True


# ---------------------------------------------------------------------------
# IsOperational
# ---------------------------------------------------------------------------


def test_suspended_account_is_not_operational():
    user = make_user(Role.CASE_MANAGER, account_status=AccountStatus.SUSPENDED)
    assert user.is_operational is False


def test_is_operational_rejects_suspended_user():
    request = APIRequestFactory().get("/")
    # A User instance reports is_authenticated True regardless of save state, so
    # this isolates the account_status check from the authentication check.
    request.user = make_user(Role.CASE_MANAGER, woredas=["A"], account_status=AccountStatus.SUSPENDED)
    assert IsOperational().has_permission(request, None) is False


def test_is_operational_accepts_active_user():
    request = APIRequestFactory().get("/")
    request.user = make_user(Role.CASE_MANAGER, woredas=["A"])
    assert IsOperational().has_permission(request, None) is True


# ---------------------------------------------------------------------------
# Permission classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_supervisor_blocked_from_case_writes(method):
    request = getattr(APIRequestFactory(), method)("/")
    request.user = make_user(Role.SUPERVISOR, woredas=["A"])
    assert CanAccessCases().has_permission(request, None) is False


def test_supervisor_allowed_case_reads():
    request = APIRequestFactory().get("/")
    request.user = make_user(Role.SUPERVISOR, woredas=["A"])
    assert CanAccessCases().has_permission(request, None) is True


def test_system_admin_allowed_case_and_referral_writes():
    """Deviation from §7 — see test_system_admin_has_full_access."""
    request = APIRequestFactory().post("/")
    request.user = make_user(Role.SYSTEM_ADMIN)
    assert CanAccessCases().has_permission(request, None) is True
    assert CanAccessReferrals().has_permission(request, None) is True


def test_an_unlisted_role_is_blocked_from_case_reads():
    request = APIRequestFactory().get("/")
    request.user = make_user("NOT_A_ROLE")
    assert CanAccessCases().has_permission(request, None) is False
    assert CanAccessReferrals().has_permission(request, None) is False


def test_case_manager_may_write_referrals():
    request = APIRequestFactory().post("/")
    request.user = make_user(Role.CASE_MANAGER, woredas=["A"])
    assert CanAccessReferrals().has_permission(request, None) is True


# ---------------------------------------------------------------------------
# Queryset scoping
# ---------------------------------------------------------------------------


def test_programme_manager_scope_is_unfiltered():
    view = ScopedView(scope_kind="case")
    result = view.apply_scope(RecordingQuerySet(), make_user(Role.PROGRAMME_MANAGER))
    assert result.filters is None and result.is_none is False


def test_system_admin_scope_is_unfiltered():
    """Deviation from §7 — see test_system_admin_has_full_access."""
    view = ScopedView(scope_kind="case")
    result = view.apply_scope(RecordingQuerySet(), make_user(Role.SYSTEM_ADMIN))
    assert result.filters is None and result.is_none is False


def test_woreda_scope_filters_to_assigned_woredas():
    view = ScopedView(scope_kind="case", woreda_field="woreda")
    user = make_user(Role.SUPERVISOR, woredas=["Woreda A", "Woreda B"])
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"woreda__in": ["Woreda A", "Woreda B"]}


def test_caseload_scope_filters_to_own_cases():
    view = ScopedView(scope_kind="case", case_manager_field="case_manager_id")
    user = make_user(Role.CASE_MANAGER, woredas=["A"])
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"case_manager_id": user.pk}


def test_scope_fails_closed_when_view_omits_the_field():
    """A misconfigured viewset must return nothing, never everything."""
    view = ScopedView(scope_kind="case")  # no woreda_field declared
    result = view.apply_scope(RecordingQuerySet(), make_user(Role.SUPERVISOR, woredas=["A"]))
    assert result.is_none is True


def test_partner_staff_scope_is_empty_until_partner_fk_exists():
    """Sprint 2 adds User.partner. Until then partner staff see nothing."""
    view = ScopedView(scope_kind="referral", partner_field="receiving_partner_id")
    result = view.apply_scope(RecordingQuerySet(), make_user(Role.PARTNER_STAFF))
    assert result.is_none is True


def test_linked_roles_scope_is_empty_until_their_entities_exist():
    """Trainer / employer liaison / enterprise officer link through Sprint 5-6 entities."""
    view = ScopedView(scope_kind="case")
    for role in (Role.TRAINER, Role.EMPLOYER_LIAISON, Role.ENTERPRISE_OFFICER):
        assert view.apply_scope(RecordingQuerySet(), make_user(role)).is_none is True
