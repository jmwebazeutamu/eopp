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


class ScopedQuerySetMixin:
    """Narrow a viewset's queryset to the rows the user's scope allows.

    Declare on the viewset which fields carry the scoping keys, using ORM lookup
    paths relative to the queryset's model::

        class ReferralViewSet(ScopedQuerySetMixin, ModelViewSet):
            scope_kind = "referral"                       # or "case"
            woreda_field = "case__woreda"
            case_manager_field = "case__case_manager_id"
            partner_field = "receiving_partner_id"

    A viewset that omits a field needed by the requesting user's scope gets an
    empty queryset, never an unfiltered one. Failing closed matters here: these
    are personal case records (§9), and the cost of a silent over-broad filter is
    a data protection incident rather than a bug report.
    """

    scope_kind = "case"
    woreda_field = None
    case_manager_field = None
    partner_field = None

    def get_queryset(self):
        queryset = super().get_queryset()
        return self.apply_scope(queryset, self.request.user)

    def apply_scope(self, queryset, user):
        scope = user.case_scope() if self.scope_kind == "case" else user.referral_scope()

        if scope == Scope.ALL:
            return queryset

        if scope == Scope.NONE:
            return queryset.none()

        if scope == Scope.OWN_WOREDA:
            if not self.woreda_field:
                return queryset.none()
            return queryset.filter(**{f"{self.woreda_field}__in": user.woreda_assignment})

        if scope == Scope.OWN_CASELOAD:
            if not self.case_manager_field:
                return queryset.none()
            return queryset.filter(**{self.case_manager_field: user.pk})

        if scope == Scope.LINKED:
            return self.apply_linked_scope(queryset, user)

        return queryset.none()

    def apply_linked_scope(self, queryset, user):
        """Rows linked to this user's own organisation or activity.

        Partner staff are scoped to their own institution's referrals (§7). A
        partner-staff account with no `partner` set sees nothing — User.clean
        refuses to create one, so this is a backstop against rows written before
        that rule existed, or by a direct database edit.
        """
        if user.role == Role.PARTNER_STAFF:
            if not (user.partner_id and self.partner_field):
                return queryset.none()
            return queryset.filter(**{self.partner_field: user.partner_id})

        # TRAINER, EMPLOYER_LIAISON and ENTERPRISE_OFFICER are linked through the
        # entity they own — Training Enrolment (Sprint 5), Placement (Sprint 5),
        # Enterprise (Sprint 6). Each of those viewsets overrides this method
        # when its sprint lands.
        return queryset.none()
