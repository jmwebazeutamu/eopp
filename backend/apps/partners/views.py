"""Partner API — spec §4.11, §10 Sprint 2."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import SAFE_METHODS, BasePermission
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.models import Role
from apps.users.permissions import IsOperational

from .models import MouStatus, Partner
from .serializers import PartnerSerializer


class CanManagePartners(BasePermission):
    """Partner records sit outside the §7 case/referral matrix.

    §7 scopes *case content*; a partner directory is organisational reference
    data. Every operational user needs to read it — a case manager choosing a
    referral destination, a supervisor reviewing coverage. Writing is limited to
    the roles that own partner relationships: the system administrator
    (configuration, §7) and the programme manager, who §7 gives "partner
    performance decisions".

    Flagged for Phase 1 confirmation: §7's table does not cover this entity.
    """

    message = "Your role does not permit changes to partner records."
    write_roles = {Role.SYSTEM_ADMIN, Role.PROGRAMME_MANAGER}

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_operational):
            return False
        if request.method in SAFE_METHODS:
            return True
        return user.role in self.write_roles


@extend_schema(tags=["partners"])
class PartnerViewSet(viewsets.ModelViewSet):
    queryset = Partner.objects.all()
    serializer_class = PartnerSerializer
    permission_classes = [IsOperational, CanManagePartners]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["partner_type", "active_status", "mou_status"]
    search_fields = ["partner_name", "contact_name", "email"]
    ordering_fields = ["partner_name", "partner_type", "created_at"]
    ordering = ["partner_name"]

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Partner counts by the two things a supervisor chases: MOU and capacity.

        Whether a partner can take a referral today, and whether the paperwork
        behind that is signed, are different questions — a partner can be
        accepting referrals on a draft MOU, which is exactly the gap worth
        seeing on the screen.
        """
        visible = self.filter_queryset(self.get_queryset())
        counters = [
            {
                "param": "active_status",
                "value": "true",
                "label": "Accepting referrals",
                "count": visible.filter(active_status=True).count(),
            },
            {
                "param": "active_status",
                "value": "false",
                "label": "Paused",
                "count": visible.filter(active_status=False).count(),
            },
        ]
        counters += counters_for(visible, param="mou_status", field="mou_status", choices=MouStatus, include_zero=False)
        return Response(summary_response(visible, counters))

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "woreda",
                str,
                description="Return only partners whose coverage includes this woreda.",
            )
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()
        woreda = self.request.query_params.get("woreda")
        if woreda:
            queryset = queryset.covering(woreda)
        return queryset

    def perform_destroy(self, instance):
        raise MethodNotAllowed(
            "DELETE",
            detail=(
                "Partners are deactivated, not deleted — referral history and the §8 "
                "partner performance dashboards depend on the record."
            ),
        )
