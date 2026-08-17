"""Programme dashboard API — the handoff's screen 8.

Spec §2 puts "supervisor and programme manager dashboards" on the React
frontend; §8's nine analytical dashboards are a separate Metabase deliverable in
Sprint 7. This serves the first, and does not duplicate the second.
"""

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
