"""Tier 1 — the case manager dashboard. Server-rendered.

`CASE_MANAGER_DASHBOARD.md` §3. Deliberately not a Metabase dashboard and not a
React route:

* this screen shows named youth, and the per-youth boundary belongs in the
  Django ORM where it is enforced and tested, not in a BI tool's paid row-level
  security;
* it is one request under 100 KB — six BI cards is six round-trips, and the
  brief's users are on 3G;
* every element links into a filtered list or a case. A BI tool renders numbers;
  this renders work.

It is also the reason the React app is not the right home: this page has to work
with CSS disabled and inside a 12-query budget, which a client-rendered route
cannot claim. The React app keeps the case-facing screens; this is an operational
work queue that happens to live at the same origin as the API.
"""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView

from apps.cases.models import CaseStatus
from apps.users.models import Scope

from . import queues
from .scoping import scoped_cases

# How many rows each card shows before "View all N →". The count is a separate
# cheap query; slicing a queryset and calling len() on it would fetch every row
# to display six.
CARD_ROWS = 6


class CaseFacingMixin(LoginRequiredMixin):
    """Refuse anyone whose §7 scope has no case population.

    A LINKED or NONE scope would render six empty cards, which reads as a case
    manager with nothing to do rather than as a screen that is not for them.
    """

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_authenticated:
            if not user.is_operational:
                raise PermissionDenied("This account is not active.")
            if user.case_scope() not in {Scope.ALL, Scope.OWN_WOREDA, Scope.OWN_CASELOAD}:
                raise PermissionDenied("Your role does not have a caseload to show.")
        return super().dispatch(request, *args, **kwargs)


class CaseManagerDashboardView(CaseFacingMixin, TemplateView):
    """CM-1 to CM-6 in one request."""

    template_name = "dashboard/case_manager.html"

    def get_context_data(self, **kwargs):
        user = self.request.user

        needs = queues.needs_action(user)
        awaiting = queues.awaiting_partner(user)
        risk = queues.at_risk(user)

        return {
            **super().get_context_data(**kwargs),
            "needs_action": [
                {"alert": alert, "reason": queues.ALERT_REASON.get(alert.alert_type, alert.get_alert_type_display())}
                for alert in needs[:CARD_ROWS]
            ],
            "needs_action_count": needs.count(),
            "awaiting_partner": awaiting[:CARD_ROWS],
            "awaiting_partner_count": awaiting.count(),
            "at_risk": queues.to_risk_items(risk[:CARD_ROWS]),
            "at_risk_count": risk.count(),
            "uninstrumented_risk": queues.UNINSTRUMENTED_RISK_CONDITIONS,
            "caseload_by_status": queues.caseload_by_status(user),
            "week": queues.week_counts(user),
            "outcomes_verified": queues.outcomes_verified(user),
            # §11 placeholder, not an agreed value; the badge reads it rather
            # than hard-coding 7 (CASE_MANAGER_DASHBOARD.md §5, CM-2).
            "confirmation_threshold": settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS,
        }


class WorkQueueListView(CaseFacingMixin, TemplateView):
    """The drill-down every card links into.

    §2 of the contract: a number that cannot be clicked to produce a list of
    named youth should be deleted. This is where those clicks land.
    """

    template_name = "dashboard/queue.html"

    QUEUES = {
        "needs-action": ("Needs action today", "alerts"),
        "awaiting-partner": ("Referrals awaiting partner response", "referrals"),
        "at-risk": ("Youth at risk of dropping out", "risk"),
    }

    def get_context_data(self, **kwargs):
        user = self.request.user
        slug = kwargs["queue_slug"]

        if slug in self.QUEUES:
            title, kind = self.QUEUES[slug]
            rows = {
                "alerts": lambda: [
                    {"alert": a, "reason": queues.ALERT_REASON.get(a.alert_type, a.get_alert_type_display())}
                    for a in queues.needs_action(user)
                ],
                "referrals": lambda: list(queues.awaiting_partner(user)),
                "risk": lambda: queues.to_risk_items(queues.at_risk(user)),
            }[kind]()
            return {**super().get_context_data(**kwargs), "title": title, "kind": kind, "rows": rows}

        # A case status slug — the caseload table links here.
        status = slug.upper()
        valid = {choice.value for choice in CaseStatus}
        if status not in valid:
            raise PermissionDenied("Unknown queue.")
        cases = scoped_cases(user).filter(case_status=status).order_by("-last_activity_date")
        return {
            **super().get_context_data(**kwargs),
            "title": f"{CaseStatus(status).label} cases",
            "kind": "cases",
            "rows": list(cases),
        }


def case_or_404(user, case_id):
    """Out-of-scope records 404 rather than 403 — the API does not confirm that
    a record the caller cannot see exists, and this screen must not either."""
    return get_object_or_404(scoped_cases(user), pk=case_id)
