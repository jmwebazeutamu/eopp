"""User management API — spec §10 Sprint 2 builds the admin UI on top of this."""

from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.cases.models import CaseStatus
from apps.common.summaries import counters_for, summary_response

from .models import AccountStatus, Role, Scope, User
from .permissions import CanAccessCases, HasRole, IsOperational
from .serializers import (
    AssignableUserSerializer,
    CurrentUserSerializer,
    PasswordChangeSerializer,
    ProfileSerializer,
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

    # Annotated because the user list shows each account's live load, and §11's
    # CASELOAD_CEILING is meaningless to an administrator who cannot see it.
    # Open cases only: a closed case is not work in hand.
    # `order_by` restated because Django drops Meta.ordering on an aggregate
    # query, and an unordered queryset makes paginated pages overlap.
    queryset = User.objects.annotate(
        caseload_count=Count(
            "managed_cases",
            filter=Q(managed_cases__case_status__in=CaseStatus.open_statuses()),
            distinct=True,
        )
    ).order_by("full_name")
    serializer_class = UserSerializer
    permission_classes = [IsOperational, HasRole.of(Role.SYSTEM_ADMIN)]
    # SearchFilter added so the screen's "find a person" box works; the fields
    # were already declared but nothing was reading them.
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["role", "account_status"]
    search_fields = ["full_name", "username", "email"]
    ordering_fields = ["full_name", "date_joined", "last_login"]

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Account counts by role, plus the ones that cannot sign in.

        Roles with nobody in them are dropped: ten counters, six of them zero,
        would bury the four that matter on a pilot of twenty users.
        """
        visible = self.filter_queryset(self.get_queryset())
        counters = counters_for(visible, param="role", field="role", choices=Role, include_zero=False)
        suspended = visible.exclude(account_status=AccountStatus.ACTIVE).count()
        if suspended:
            counters.append(
                {"param": "account_status", "value": AccountStatus.SUSPENDED, "label": "Suspended", "count": suspended}
            )
        return Response(summary_response(visible, counters))

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
    @action(
        detail=False,
        methods=["get", "patch"],
        permission_classes=[IsAuthenticated],
        serializer_class=CurrentUserSerializer,
    )
    def me(self, request):
        """The requesting user's own record, and the parts of it they may change.

        Open to any authenticated role — including system administrators, who are
        otherwise barred from case content but still need their own profile.

        PATCH goes through `ProfileSerializer`, which carries only `full_name`
        and `email`. Role, woreda assignment, partner and account status are not
        writable there because they are not fields on it — §7 is the
        administrator's to set, and a self-service route that could touch it
        would be an escalation path. The response is the full `/me/` shape so
        the client can refresh its context in one round trip.
        """
        if request.method == "PATCH":
            serializer = ProfileSerializer(request.user, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            request.user.refresh_from_db()
        return Response(CurrentUserSerializer(request.user).data)

    @action(
        detail=False,
        methods=["post"],
        url_path="me/password",
        permission_classes=[IsAuthenticated],
        serializer_class=PasswordChangeSerializer,
    )
    def change_password(self, request):
        """A user changing their own password.

        Requires the current password: an access token lasts an hour and these
        are shared machines, so an unlocked screen must not be enough to take
        the account over.

        Every other session ends. `set_password` stamps `password_changed_at`
        and authentication refuses any token issued earlier, so a device
        holding a stolen token is cut off — which is the point of changing a
        password when you think you are compromised.

        The device doing the changing is not, though: it gets a fresh token
        pair in the response. Signing someone out of the screen they just used
        correctly would teach them not to.
        """
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh)})
