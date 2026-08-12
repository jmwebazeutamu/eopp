"""Partner API — spec §4.11, §10 Sprint 2."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, viewsets
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.users.models import Role
from apps.users.permissions import IsOperational

from .models import Partner
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
