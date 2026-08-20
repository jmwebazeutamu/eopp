"""The security boundary for the case manager dashboard.

`dashboard_handoff_youth_employment/django/CASE_MANAGER_DASHBOARD.md` §4 requires
one helper used by every queue: "a queryset that filters Case.objects directly is
a security defect, not a style problem."

That contract sketches the scoping as a chain of `if user.role == ...` branches.
This repository forbids exactly that — CLAUDE.md: "RBAC reads
`apps/users/models.ACCESS_MATRIX`. Never test roles inline at a call site." Both
rules are satisfied by delegating to `apps.users.permissions.scope_queryset`,
which is the one place §7 is decided and the place the existing RBAC tests
already cover. The contract gets its single entry point; the matrix stays the
only description of who sees what.

The difference matters in one visible way. The contract restates §7's
"system administrator: configuration only, no case content" as a hard
`qs.none()`. `ACCESS_MATRIX` was deliberately widened on 2026-08-16, at the
programme's request, to give that role full case access. Hard-coding the
contract's version here would silently revert a decision somebody made on
purpose. It follows the matrix, and if the widening is reversed at Phase 1
sign-off, this follows that too, with no edit here.
"""

from apps.cases.models import Case
from apps.referrals.models import Referral
from apps.users.permissions import scope_queryset


def scoped_cases(user):
    """The single entry point for case visibility (§7).

    Every queryset in `queues.py` starts here.
    """
    return scope_queryset(
        Case.objects.select_related("youth", "case_manager"),
        user,
        scope_kind="case",
        woreda_field="woreda",
        case_manager_field="case_manager_id",
    )


def scoped_referrals(user):
    """The single entry point for referral visibility.

    Case-level scoping is not sufficient, and the contract is right about why:
    §7 restricts partner staff to their own institution's referrals, and one
    youth can hold referrals to several partners at once. Filtering only on
    `case__in=scoped_cases(user)` would show Partner A every referral on a
    shared youth, including the ones sent to Partner B.

    So this scopes on the *referral* kind, which routes a LINKED user through
    `partner_field` rather than through the case. `apps/dashboard/tests` pins the
    shared-youth case that case-level scoping alone would fail.
    """
    return scope_queryset(
        Referral.objects.youth_side().select_related("case", "case__youth", "receiving_partner"),
        user,
        scope_kind="referral",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
        partner_field="receiving_partner_id",
    )
