"""Programme dashboard API — the handoff's screen 8.

Spec §2 puts "supervisor and programme manager dashboards" on the React
frontend; §8's nine analytical dashboards are a separate Metabase deliverable in
Sprint 7. This serves the first, and does not duplicate the second.
"""

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.models import Scope
from apps.users.permissions import IsOperational

from .services import programme_dashboard


class CanReadProgrammeFigures(BasePermission):
    """Anyone whose §7 case scope covers case records at all.

    Not a role list: the figures are aggregates of exactly the rows the caller
    could already list one by one, so the question "may they see the total?" has
    the same answer as "may they see the rows?". A LINKED or NONE scope — partner
    staff, trainers — has no case population to total, and gets 403 rather than
    a screen of zeros that looks like a programme with no youth in it.
    """

    message = "Your role does not have a case population to report on."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        return user.case_scope() in {Scope.ALL, Scope.OWN_WOREDA, Scope.OWN_CASELOAD}


@extend_schema(
    tags=["dashboard"],
    responses={200: OpenApiTypes.OBJECT},
    description=(
        "Programme dashboard figures, scoped to the caller's §7 case scope. Panels whose source entity has not "
        "been built yet report `available: false` with a reason rather than a zero."
    ),
)
class ProgrammeDashboardView(APIView):
    """One request for the whole screen — the brief's users are on 3G."""

    permission_classes = [IsOperational, CanReadProgrammeFigures]

    def get(self, request):
        return Response(programme_dashboard(request.user))


@extend_schema(
    tags=["dashboard"],
    responses={200: OpenApiTypes.OBJECT},
    description="Tier 1 — the case manager work queue, as JSON. The server-rendered page is at /dashboard/.",
)
class MyWorkView(APIView):
    """Tier 1 as data, so the React shell can render it under /dashboard too.

    The same `queues` module the server-rendered page uses, so the two cannot
    drift: one definition of "needs action today", two renderings of it.
    """

    permission_classes = [IsOperational, CanReadProgrammeFigures]

    def get(self, request):
        from . import queues

        user = request.user
        needs, awaiting, risk = queues.needs_action(user), queues.awaiting_partner(user), queues.at_risk(user)
        return Response(
            {
                "needs_action": [
                    {
                        "id": str(alert.pk),
                        "case": str(alert.case_id),
                        "youth_name": alert.case.youth.full_name,
                        "reason": str(queues.ALERT_REASON.get(alert.alert_type, alert.get_alert_type_display())),
                        "days_overdue": alert.days_overdue,
                    }
                    for alert in needs[:6]
                ],
                "needs_action_count": needs.count(),
                "awaiting_partner": [
                    {
                        "id": str(referral.pk),
                        "case": str(referral.case_id),
                        "youth_name": referral.case.youth.full_name,
                        "partner": referral.receiving_partner.partner_name,
                        "days_waiting": referral.days_waiting,
                    }
                    for referral in awaiting[:6]
                ],
                "awaiting_partner_count": awaiting.count(),
                "at_risk": [
                    {
                        "case": str(item.case_id),
                        "youth_name": item.youth_name,
                        "reason": item.reason,
                        "badge": item.badge,
                    }
                    for item in queues.to_risk_items(risk[:6])
                ],
                "at_risk_count": risk.count(),
                # CM-2's tile subtitle is computed, not written into a string:
                # moving REFERRAL_CONFIRMATION_OVERDUE_DAYS moves the number.
                "awaiting_over_threshold": queues.awaiting_over_threshold(user),
                "open_alerts_in_scope": queues.open_alerts_in_scope(user),
                "confirmation_threshold": settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS,
                # CM-5's missing tile: active referrals, and the youth they cover.
                "active": queues.active_referrals(user),
                "uninstrumented_risk": [str(c) for c in queues.UNINSTRUMENTED_RISK_CONDITIONS],
                "caseload_by_status": queues.caseload_by_status(user),
                # 4.4: whose cases these are. "My caseload" is only true for a
                # case manager.
                "caseload_basis": queues.caseload_basis(user),
                # 4.3: the at-risk list measures the clock, the table measures
                # the recorded status. They differ legitimately (§6.2) and the
                # screen has to say which is which.
                "at_risk_basis": str(_("threshold reached")),
                "week": queues.week_counts(user),
                "outcomes_verified": queues.outcomes_verified(user),
                "woredas": list(user.woreda_assignment or []),
                # Tier 1 is live rather than refreshed on a schedule, but a
                # dashboard that does not state its age invites the reader to
                # assume it is current.
                "generated_at": timezone.now().isoformat(),
            }
        )


@extend_schema(tags=["dashboard"], responses={200: OpenApiTypes.OBJECT}, description="Tier 2 — woreda supervisor.")
class WoredaSupervisorView(APIView):
    permission_classes = [IsOperational, CanReadProgrammeFigures]

    def get(self, request):
        from .services import scope_label, scoped_bases
        from .tiers import woreda_supervisor

        youth, cases, referrals = scoped_bases(request.user)
        return Response({"scope_label": scope_label(request.user), **woreda_supervisor(youth, cases, referrals)})


@extend_schema(tags=["dashboard"], responses={200: OpenApiTypes.OBJECT}, description="Tier 3 — programme manager.")
class ProgrammeManagerView(APIView):
    permission_classes = [IsOperational, CanReadProgrammeFigures]

    def get(self, request):
        from .services import programme_dashboard, scoped_bases
        from .tiers import programme_manager

        youth, cases, referrals = scoped_bases(request.user)
        return Response({**programme_dashboard(request.user), **programme_manager(youth, cases, referrals)})


@extend_schema(tags=["dashboard"], responses={200: OpenApiTypes.OBJECT}, description="Tier 4 — M&E and donor.")
class DonorView(APIView):
    permission_classes = [IsOperational, CanReadProgrammeFigures]

    def get(self, request):
        from django.conf import settings
        from django.utils import timezone

        from .services import scope_label, scoped_bases
        from .tiers import donor

        youth, _cases, referrals = scoped_bases(request.user)
        return Response(
            {
                "scope_label": scope_label(request.user),
                **donor(youth, referrals, timezone.localdate(), settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS),
            }
        )
