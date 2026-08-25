"""Which grievances a user may see — the union of two scopes, not one.

The complaints channel is shared by the referral engine and the WLT group
module, and the two scope on different things. A supervisor is scoped by
**woreda**; a facilitator is scoped by **the groups she runs**; a woreda officer
by **the geography she covers**. Neither scope can express the other: §7's
`woreda_assignment` is a list of woreda *names*, which cannot describe a region
without re-listing it, and `wlt_scope_location` is a point in the hierarchy that
says nothing about a caseload.

So this is a union, evaluated once, and it fails closed on both sides — a user
with no case scope and no group scope gets nothing rather than everything.

**A WLT role does not gain case access by reading a grievance.** The group-side
branch matches on `subject_group` alone. A facilitator reading a complaint about
her own savings group is not thereby reading a young person's case file, and
`test_boundary` pins that from the other direction.
"""

from django.db.models import Q

from apps.users.permissions import scope_group_queryset, scope_queryset


def scope_grievances(queryset, user):
    """Narrow to what `user` may see, by caseload *or* by group.

    Both halves are computed against the same base queryset and combined with
    `|`, so a user who happens to hold both scopes — the administrator, or a
    future combined role — sees the union rather than whichever branch ran
    first.
    """
    from apps.wlt.models import Group

    # Case side: the grievance's own woreda, not the case's, because most
    # complaints have no case. `scope_queryset` returns `.none()` for a role
    # with no case scope, which is what every WLT role has.
    case_side = scope_queryset(
        queryset,
        user,
        woreda_field="woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    )

    # Group side: complaints about a group this user may see. Never about a
    # *case*, even if the same woman is on both sides of the platform.
    groups = scope_group_queryset(Group.objects.all(), user)
    group_side = queryset.filter(subject_group__in=groups)

    # Combined through primary keys rather than with `queryset | queryset`.
    # `scope_queryset` returns `.none()` for a role with no case scope and
    # applies `distinct()` on some branches, and Django refuses to OR a unique
    # query with a non-unique one — which surfaced as a 500 on the list route
    # for the first WLT role that read it. Two subqueries over one group's worth
    # of rows is not a cost worth a fragile combine.
    return queryset.filter(Q(pk__in=case_side.values("pk")) | Q(pk__in=group_side.values("pk")))
