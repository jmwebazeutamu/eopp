"""RBAC scaffolding — spec §7.

Two layers:

* **Permission classes** answer "may this user touch this kind of record at all?"
* **`ScopedQuerySetMixin`** answers "which rows?" by narrowing the queryset.

Both read `ACCESS_MATRIX` in models.py rather than testing roles inline. Adding a
role, or changing what one may see, is a one-line edit to that table.

The entity apps land in later sprints (Case in Sprint 1, Referral in Sprint 3),
so this module is deliberately entity-agnostic: a viewset declares which of its
fields carry the woreda, the case manager, and the owning partner, and the mixin
does the filtering.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role, Scope


class IsOperational(BasePermission):
    """Authenticated *and* not suspended.

    `is_active` alone is not enough: spec §4.12 carries a separate
    `account_status`, and a SUSPENDED account must stop acting immediately
    without deleting the row the audit trail points at.
    """

    message = "This account is not active."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_operational)


class HasRole(BasePermission):
    """Restrict a view to an explicit set of roles.

    Use as `permission_classes = [IsOperational, HasRole.of(Role.CASE_MANAGER)]`.
    """

    allowed_roles = frozenset()

    @classmethod
    def of(cls, *roles):
        return type("HasRoleSpecific", (cls,), {"allowed_roles": frozenset(roles)})

    def has_permission(self, request, view):
        return bool(request.user and request.user.role in self.allowed_roles)


class _MatrixPermission(BasePermission):
    """Shared logic for the case and referral permission classes."""

    scope_attr = ""  # "case_scope" or "referral_scope"
    write_attr = ""  # "can_write_cases" or "can_write_referrals"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        if getattr(user, self.scope_attr)() == Scope.NONE:
            # System administrators are configuration-only (§7).
            return False
        if request.method in SAFE_METHODS:
            return True
        return getattr(user, self.write_attr)()


class CanRecordDelivery(BasePermission):
    """Read a case's delivery records if you can see the case; write if you deliver.

    Sprint 5. Reading follows the case scope, so a supervisor sees her woreda's
    enrolments and placements. Writing follows `delivery_write`, which is a
    different question and has a different answer: §7 gives an employer liaison
    LINKED case scope and no case write, and she is exactly the person who
    records a placement and makes the retention calls.
    """

    message = "Your role does not permit recording training or placement records."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        if user.case_scope() == Scope.NONE:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.can_record_delivery()


class CanAccessCases(_MatrixPermission):
    """Case record access per the §7 matrix."""

    message = "Your role does not permit this action on case records."
    scope_attr = "case_scope"
    write_attr = "can_write_cases"


class CanAccessReferrals(_MatrixPermission):
    """Referral access per the §7 matrix."""

    message = "Your role does not permit this action on referrals."
    scope_attr = "referral_scope"
    write_attr = "can_write_referrals"


# What "linked" means for the three roles that are not partner staff — §7's
# LINKED scope, resolved through the entity each role owns.
#
# The lookup is expressed relative to a **Case**, and a viewset over some other
# model declares the path from its own rows to the case (`linked_case_prefix`).
# One table rather than a branch per viewset: "a trainer sees the cases she has
# a training enrolment on" is a statement about the access model, and it belongs
# beside the matrix that makes it.
#
# `recorded_by` rather than the provider organisation: `User.partner` is
# reserved for PARTNER_STAFF accounts (§4.12, and `User.clean` enforces it), so a
# trainer has no institution to scope to. Her own records are what she is
# accountable for, which is also what §9 attributes to her.
LINKED_THROUGH = {
    Role.TRAINER: "training_enrolments__recorded_by",
    Role.EMPLOYER_LIAISON: "placements__recorded_by",
    # Sprint 6. Every LINKED role now resolves through something; a role added
    # to `Role` and forgotten here still falls through to `none()`.
    Role.ENTERPRISE_OFFICER: "enterprises__recorded_by",
}


def linked_scope(queryset, user, partner_field, case_prefix=""):
    """Rows linked to this user's own organisation or activity.

    Partner staff are scoped to their own institution's referrals (§7). A
    partner-staff account with no `partner` set sees nothing — User.clean
    refuses to create one, so this is a backstop against rows written before
    that rule existed, or by a direct database edit.

    The other LINKED roles resolve through `LINKED_THROUGH`. A role with no
    entry sees nothing, which is the fail-closed default: an enterprise officer
    gets an empty list until Sprint 6 gives her something to be linked through,
    rather than everything.
    """
    if user.role == Role.PARTNER_STAFF:
        if not (user.partner_id and partner_field):
            return queryset.none()
        return queryset.filter(**{partner_field: user.partner_id})

    lookup = LINKED_THROUGH.get(user.role)
    if lookup is None:
        return queryset.none()
    # `.distinct()` because the join fans out: a trainer with three enrolments on
    # one case would otherwise see that case three times, and a paginated list
    # would overlap between pages.
    return queryset.filter(**{f"{case_prefix}{lookup}": user.pk}).distinct()


def scope_queryset(
    queryset,
    user,
    *,
    scope_kind="case",
    woreda_field=None,
    case_manager_field=None,
    partner_field=None,
    linked_case_prefix="",
    linked=linked_scope,
):
    """Narrow `queryset` to the rows `user`'s §7 scope allows.

    A module function rather than only a mixin method, because scoping is not
    only a viewset concern: the programme dashboard aggregates across several
    models at once and must count exactly the rows the user could have listed.
    One implementation, so "fails closed" is decided in one place.

    A caller that omits a field needed by the requesting user's scope gets an
    empty queryset, never an unfiltered one. Failing closed matters here: these
    are personal case records (§9), and the cost of a silent over-broad filter is
    a data protection incident rather than a bug report.
    """
    scope = user.case_scope() if scope_kind == "case" else user.referral_scope()

    if scope == Scope.ALL:
        return queryset

    if scope == Scope.NONE:
        return queryset.none()

    if scope == Scope.OWN_WOREDA:
        if not woreda_field:
            return queryset.none()
        return queryset.filter(**{f"{woreda_field}__in": user.woreda_assignment})

    if scope == Scope.OWN_CASELOAD:
        if not case_manager_field:
            return queryset.none()
        return queryset.filter(**{case_manager_field: user.pk})

    if scope == Scope.LINKED:
        # `linked_case_prefix` is the ORM path from *this* queryset's model to
        # the Case a LINKED role is linked through: empty on Case, "case__" on
        # a referral or a placement, "case__" again on Youth. A caller that
        # omits it on a model that needs it gets a `FieldError` rather than a
        # wrong answer, which is the right way round for a scoping bug.
        if linked is linked_scope:
            return linked_scope(queryset, user, partner_field, case_prefix=linked_case_prefix)
        return linked(queryset, user, partner_field)

    return queryset.none()


class ScopedQuerySetMixin:
    """Narrow a viewset's queryset to the rows the user's scope allows.

    Declare on the viewset which fields carry the scoping keys, using ORM lookup
    paths relative to the queryset's model::

        class ReferralViewSet(ScopedQuerySetMixin, ModelViewSet):
            scope_kind = "referral"                       # or "case"
            woreda_field = "case__woreda"
            case_manager_field = "case__case_manager_id"
            partner_field = "receiving_partner_id"

    The decision itself lives in `scope_queryset`; this is the viewset's way in.
    """

    scope_kind = "case"
    woreda_field = None
    case_manager_field = None
    partner_field = None
    # The ORM path from this viewset's model to the Case a LINKED role is linked
    # through. Empty on a Case viewset, "case__" on anything hanging off one.
    linked_case_prefix = ""

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.apply_scope(queryset, self.request.user)

    def apply_scope(self, queryset, user):
        return scope_queryset(
            queryset,
            user,
            scope_kind=self.scope_kind,
            woreda_field=self.woreda_field,
            case_manager_field=self.case_manager_field,
            partner_field=self.partner_field,
            # Subclasses override `apply_linked_scope`, so route through the
            # instance rather than the module function.
            linked=lambda qs, u, field: self.apply_linked_scope(qs, u),
        )

    def apply_linked_scope(self, queryset, user):
        return linked_scope(queryset, user, self.partner_field, case_prefix=self.linked_case_prefix)


# ---------------------------------------------------------------------------
# WLT group module (see apps/wlt). Group records scope differently from case
# records, so they get their own entry point rather than a fifth `scope_kind`
# on `scope_queryset` — the keys have nothing in common, and overloading one
# function would mean a caller could pass `woreda_field` to a group queryset and
# get a filter that silently matched nothing.
# ---------------------------------------------------------------------------


def location_subtree_filter(field, location):
    """Rows whose `field` (a kebele FK path) sits at or under `location`.

    The hierarchy is exactly four levels deep and fixed (`locations.PARENT_LEVEL`),
    so the descent is written out rather than walked. A recursive query would be
    more general and would also mean every group list ran a CTE; this compiles to
    one indexed join per level.

    Returns ``None`` for a level that cannot contain a kebele, so the caller can
    fail closed rather than filter on nothing.
    """
    from apps.locations.models import LocationLevel

    depth = {
        LocationLevel.KEBELE: "",
        LocationLevel.WOREDA: "__parent",
        LocationLevel.ZONE: "__parent__parent",
        LocationLevel.REGION: "__parent__parent__parent",
    }.get(location.level)
    if depth is None:
        return None
    return {f"{field}{depth}": location}


def scope_group_queryset(queryset, user, *, kebele_field="kebele", facilitator_field="facilitator"):
    """Narrow `queryset` to the WLT groups `user` may see (WLT handoff §9).

    Fails closed exactly as `scope_queryset` does: a caller that cannot express
    the key the user's scope needs gets nothing. These records carry a group's
    savings ledger, so an over-broad filter is a financial disclosure.
    """
    from .models import GroupScope

    scope = user.group_scope()

    if scope == GroupScope.ALL:
        return queryset

    if scope == GroupScope.NONE:
        return queryset.none()

    if scope == GroupScope.OWN_GROUPS:
        if not facilitator_field:
            return queryset.none()
        return queryset.filter(**{facilitator_field: user.pk})

    if scope == GroupScope.OWN_GEOGRAPHY:
        if not (user.wlt_scope_location_id and kebele_field):
            return queryset.none()
        lookup = location_subtree_filter(kebele_field, user.wlt_scope_location)
        if lookup is None:
            return queryset.none()
        return queryset.filter(**lookup)

    return queryset.none()


class CanEnrolBeneficiaries(BasePermission):
    """May put a woman on the WLT register — which is not `group_write`.

    `group_write` is deliberately false for a woreda officer: meetings and the
    ledger belong to the facilitator who was in the room, and an officer who
    could post a ledger entry could settle a discrepancy nobody witnessed. But
    loading a PSNP ELS extract is not recording what happened in a meeting. It is
    an administrative act at woreda level, and the officer is the person who
    holds the extract and verifies against it.

    Gating enrolment on `group_write` therefore left the extract importable by
    nobody who has one: a facilitator's scope is the kebeles of groups she
    already runs, so she cannot seed the first group's kebele either.

    Same shape as `delivery_write` on the youth side — §7's write column did not
    fit the person actually doing the work, so the permission is named for the
    work rather than stretched to cover it. It does **not** widen anything else:
    an officer still cannot write a group record, a meeting or a ledger entry.
    """

    message = "Your role does not enrol women onto the WLT register."

    def has_permission(self, request, view):
        from .models import GroupScope

        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        if user.group_scope() == GroupScope.NONE:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.can_write_groups() or user.wlt_approval_level is not None


class CanAccessGroups(BasePermission):
    """WLT group access per the handoff's §9 table."""

    message = "Your role does not permit this action on WLT group records."

    def has_permission(self, request, view):
        from .models import GroupScope

        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        if user.group_scope() == GroupScope.NONE:
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.can_write_groups()


class ScopedGroupQuerySetMixin:
    """Viewset counterpart of `scope_group_queryset`.

    Declare the ORM paths from *this* viewset's model to the group's kebele and
    facilitator::

        class MeetingViewSet(ScopedGroupQuerySetMixin, ModelViewSet):
            kebele_field = "group__kebele"
            facilitator_field = "group__facilitator_id"
    """

    kebele_field = "kebele"
    facilitator_field = "facilitator_id"

    def get_queryset(self):
        return self.apply_group_scope(super().get_queryset(), self.request.user)

    def apply_group_scope(self, queryset, user):
        return scope_group_queryset(
            queryset,
            user,
            kebele_field=self.kebele_field,
            facilitator_field=self.facilitator_field,
        )
