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

    def distinct(self):
        """Part of the contract since the LINKED scope joins through a case.

        The join fans out — one case, three training enrolments — so the real
        scope calls `.distinct()`. A double that did not answer it would pass a
        test the production path fails.
        """
        return self


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
    """A role missing here would silently fall back to NO_ACCESS.

    Ten roles from spec §7, plus the four the WLT group module adds — a separate
    programme with a separate subject and its own approval chain, so it carries
    its own roles rather than overloading the supervisor's.
    """
    assert set(ACCESS_MATRIX) == set(Role)
    assert len(Role) == 14
    assert len(Role.wlt_roles()) == 4


def test_every_matrix_row_answers_every_question():
    """A row missing a key raises `KeyError` at the call site, not a denial.

    `User.access` returns the row whole; a partial row would fail loudly on the
    scope it forgot, which is the right failure but a late one. This catches it
    at the table.
    """
    keys = {
        "case_scope",
        "case_write",
        "referral_scope",
        "referral_write",
        "group_scope",
        "group_write",
        "delivery_write",
    }
    for role, row in ACCESS_MATRIX.items():
        assert set(row) == keys, role


def test_wlt_roles_have_no_case_access():
    """The module boundary, stated once.

    A facilitator who can see a group roster must not thereby see those women's
    youth-side case files (WLT handoff §9, backlog S0.3). Making it a property
    of the matrix means it holds for every viewset, including ones not yet
    written, rather than for the ones that remembered to check.
    """
    for role in Role.wlt_roles():
        assert ACCESS_MATRIX[role]["case_scope"] == Scope.NONE
        assert ACCESS_MATRIX[role]["referral_scope"] == Scope.NONE
        assert not ACCESS_MATRIX[role]["case_write"]


def test_youth_roles_have_no_group_access():
    """And the same boundary from the other side.

    A youth case worker cannot read WLT ledger data. Tested in both directions
    because a leak between the modules would appear in whichever direction was
    not covered.
    """
    from apps.users.models import GroupScope

    for role in set(Role) - Role.wlt_roles() - {Role.SYSTEM_ADMIN}:
        assert ACCESS_MATRIX[role]["group_scope"] == GroupScope.NONE
        assert not ACCESS_MATRIX[role]["group_write"]


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


def test_a_trainer_is_linked_through_the_enrolments_she_recorded():
    """§7 LINKED, resolved through the entity the role owns (Sprint 5).

    Not through the training *provider*: `User.partner` is reserved for partner
    staff (§4.12), so a trainer has no institution to scope to. Her own records
    are what §9 attributes to her, and what she is accountable for.
    """
    view = ScopedView(scope_kind="case")
    user = make_user(Role.TRAINER)
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"training_enrolments__recorded_by": user.pk}


def test_an_employer_liaison_is_linked_through_the_placements_she_recorded():
    view = ScopedView(scope_kind="case")
    user = make_user(Role.EMPLOYER_LIAISON)
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"placements__recorded_by": user.pk}


def test_a_viewset_off_the_case_walks_back_to_it():
    """A referral is scoped through its case, not through itself."""
    view = ScopedView(scope_kind="referral", linked_case_prefix="case__")
    user = make_user(Role.EMPLOYER_LIAISON)
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"case__placements__recorded_by": user.pk}


def test_an_enterprise_officer_is_linked_through_her_own_enterprises():
    """Sprint 6 gave the last LINKED role something to be linked through."""
    view = ScopedView(scope_kind="case")
    user = make_user(Role.ENTERPRISE_OFFICER)
    result = view.apply_scope(RecordingQuerySet(), user)
    assert result.filters == {"enterprises__recorded_by": user.pk}


def test_a_role_with_no_entry_still_fails_closed():
    """The table is the whole rule.

    A role added to `Role` and forgotten in `LINKED_THROUGH` sees an empty list,
    never an unfiltered one. Now that every listed role resolves, this is the
    only test left holding that default in place.
    """
    from apps.users.permissions import LINKED_THROUGH, linked_scope

    unlisted = make_user(Role.PROGRAMME_MANAGER)
    unlisted.role = "A_ROLE_NOBODY_ADDED"
    assert unlisted.role not in LINKED_THROUGH

    # Called directly, because reaching the LINKED branch through the matrix
    # would need a role the matrix also does not know — and that one fails
    # closed a step earlier, for a different reason. This is the branch itself.
    assert linked_scope(RecordingQuerySet(), unlisted, partner_field=None).is_none is True


def test_the_roles_that_deliver_may_record_what_they_delivered():
    """Sprint 5. `delivery_write` is not `case_write`, and §7 separates them.

    An employer liaison may not edit a case record and **is** the person who
    records the placement and makes the 30/60/90-day calls. Gating her on
    `case_write` left her unable to action her own queue, which is the one thing
    that screen exists for.
    """
    for role in (Role.CASE_MANAGER, Role.TRAINER, Role.EMPLOYER_LIAISON, Role.ENTERPRISE_OFFICER):
        assert make_user(role).can_record_delivery(), role

    # And it is not a general widening: an employer liaison still cannot write
    # the case record itself.
    assert not make_user(Role.EMPLOYER_LIAISON).can_write_cases()


def test_reading_a_programme_does_not_let_you_record_in_it():
    """A supervisor and an M&E account read delivery records; neither writes one.

    Recording a placement is a claim about something that happened, made by
    whoever was there. A read-only role adding one would put a figure into the
    donor tier that nobody witnessed.
    """
    for role in (Role.SUPERVISOR, Role.PROGRAMME_MANAGER, Role.MNE_STAFF, Role.OUTREACH_WORKER):
        assert not make_user(role).can_record_delivery(), role


def test_wlt_roles_record_nothing_on_the_youth_side():
    for role in Role.wlt_roles():
        assert not make_user(role).can_record_delivery(), role


# ---------------------------------------------------------------------------
# The facilitator picker behind the draft-group form (defect P1)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFacilitatorPicker:
    """It answered every request with a 500, and the caller rendered that as
    "no facilitator covers this kebele" — so the fault read as an answer.

    Two independent faults: the lookup was on `pk` while every WLT client sends
    a location `code`, and an unscoped facilitator matched no kebele at all.
    """

    URL = "/api/v1/users/wlt-facilitators/"

    @pytest.fixture
    def places(self, db):
        from apps.locations.models import Location, LocationLevel

        region = Location.objects.create(code="ET-XX", name="Region", level=LocationLevel.REGION)
        zone = Location.objects.create(code="ET-XX-Z", name="Zone", level=LocationLevel.ZONE, parent=region)
        woreda = Location.objects.create(code="ET-XX-Z-W", name="Woreda", level=LocationLevel.WOREDA, parent=zone)
        other_woreda = Location.objects.create(
            code="ET-XX-Z-W2", name="Woreda Two", level=LocationLevel.WOREDA, parent=zone
        )
        return {
            "woreda": woreda,
            "kebele": Location.objects.create(
                code="ET-XX-Z-W-01", name="Kebele One", level=LocationLevel.KEBELE, parent=woreda
            ),
            "elsewhere": Location.objects.create(
                code="ET-XX-Z-W2-01", name="Kebele Two", level=LocationLevel.KEBELE, parent=other_woreda
            ),
        }

    def _facilitator(self, username, scope=None):
        from apps.users.models import Role, User

        return User.objects.create_user(
            username, "pw-Test-12345", full_name=f"Fac {username}", role=Role.WLT_FACILITATOR, wlt_scope_location=scope
        )

    def test_a_kebele_code_resolves_rather_than_raising(self, as_user, places):
        """The blocker itself. `filter(pk="ET-XX-Z-W-01")` raised ValueError on
        an integer pk, so the endpoint 500'd on every call the form made."""
        scoped = self._facilitator("fac-woreda", places["woreda"])

        response = as_user(scoped).get(self.URL, {"kebele": places["kebele"].code})

        assert response.status_code == 200
        assert str(scoped.pk) in {str(row["id"]) for row in response.data}

    def test_a_facilitator_scoped_to_a_woreda_covers_its_kebeles_only(self, as_user, places):
        scoped = self._facilitator("fac-woreda", places["woreda"])

        covered = as_user(scoped).get(self.URL, {"kebele": places["kebele"].code})
        not_covered = as_user(scoped).get(self.URL, {"kebele": places["elsewhere"].code})

        assert str(scoped.pk) in {str(row["id"]) for row in covered.data}
        assert str(scoped.pk) not in {str(row["id"]) for row in not_covered.data}

    def test_an_unscoped_facilitator_covers_every_kebele(self, as_user, places):
        """No scope is not "nowhere", it is "everywhere". An inner match on
        explicit scope rows excluded exactly the national accounts."""
        national = self._facilitator("fac-national", None)

        for kebele in (places["kebele"], places["elsewhere"]):
            response = as_user(national).get(self.URL, {"kebele": kebele.code})
            assert str(national.pk) in {str(row["id"]) for row in response.data}

    def test_an_unknown_kebele_is_an_empty_list_not_an_error(self, as_user, places):
        national = self._facilitator("fac-national", None)
        response = as_user(national).get(self.URL, {"kebele": "ET-NOPE-01"})

        assert response.status_code == 200
        assert response.data == []

    def test_a_kebele_with_genuinely_nobody_returns_nobody(self, as_user, places):
        """The message the form shows has to stay true when it is true."""
        scoped = self._facilitator("fac-woreda", places["woreda"])

        response = as_user(scoped).get(self.URL, {"kebele": places["elsewhere"].code})
        assert response.data == []

    def test_the_integer_pk_still_works(self, as_user, places):
        """Kept as a fallback so anything already calling it by id is not broken."""
        national = self._facilitator("fac-national", None)
        response = as_user(national).get(self.URL, {"kebele": str(places["kebele"].pk)})

        assert response.status_code == 200
        assert str(national.pk) in {str(row["id"]) for row in response.data}
