"""User management API — spec §10 Sprint 2 builds the admin UI on top of this."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AccountStatus, Role, Scope, User
from .permissions import CanAccessCases, HasRole, IsOperational
from .serializers import (
    AssignableUserSerializer,
    CurrentUserSerializer,
    ScopedTokenObtainPairSerializer,
    UserSerializer,
)


class ScopedTokenObtainPairView(TokenObtainPairView):
    """JWT login. Rejects suspended accounts — see the serializer."""

    serializer_class = ScopedTokenObtainPairSerializer


@extend_schema(tags=["users"])
class UserViewSet(viewsets.ModelViewSet):
    """User administration.

    Restricted to system administrators: §7 gives only that role user management.
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsOperational, HasRole.of(Role.SYSTEM_ADMIN)]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["role", "account_status"]
    search_fields = ["full_name", "username", "email"]
    ordering_fields = ["full_name", "date_joined", "last_login"]

    def perform_destroy(self, instance):
        """Accounts are deactivated, never deleted.

        `registered_youth`, `managed_cases` and `initiated_referrals` are all
        PROTECT, so a real delete would fail at the database for any user who
        has done anything — and succeed for one who has not, quietly removing an
        account the §9 audit trail may still reference. Setting
        `account_status = INACTIVE` stops them acting and keeps the record.
        """
        raise MethodNotAllowed(
            "DELETE",
            detail="Accounts are deactivated, not deleted. Set account_status to INACTIVE or SUSPENDED.",
        )

    @extend_schema(responses=AssignableUserSerializer(many=True))
    @action(
        detail=False,
        methods=["get"],
        url_path="case-managers",
        permission_classes=[IsOperational, CanAccessCases],
        serializer_class=AssignableUserSerializer,
        pagination_class=None,
    )
    def case_managers(self, request):
        """Active case managers, for the assignment picker.

        §7 restricts *user management* to the system administrator, but anyone
        who can open or reassign a case needs to see who they may assign it to.
        This exposes name and woredas only — not contact details, account status
        or anything else the admin screen shows.
        """
        queryset = User.objects.filter(role=Role.CASE_MANAGER, account_status=AccountStatus.ACTIVE, is_active=True)

        # A woreda-scoped user only sees managers who cover a woreda they work
        # in, so a supervisor in Adama is not offered a manager from Bishoftu.
        if request.user.case_scope() in {Scope.OWN_WOREDA, Scope.OWN_CASELOAD} and request.user.woreda_assignment:
            queryset = queryset.filter(woreda_assignment__overlap=request.user.woreda_assignment)

        return Response(AssignableUserSerializer(queryset.order_by("full_name"), many=True).data)

    @extend_schema(responses=CurrentUserSerializer)
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated], serializer_class=CurrentUserSerializer)
    def me(self, request):
        """The requesting user's own record.

        Open to any authenticated role — including system administrators, who are
        otherwise barred from case content but still need their own profile.
        """
        return Response(CurrentUserSerializer(request.user).data)
