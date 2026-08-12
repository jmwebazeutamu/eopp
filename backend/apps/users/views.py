"""User management API — spec §10 Sprint 2 builds the admin UI on top of this."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import Role, User
from .permissions import HasRole, IsOperational
from .serializers import CurrentUserSerializer, ScopedTokenObtainPairSerializer, UserSerializer


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

    @extend_schema(responses=CurrentUserSerializer)
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticated], serializer_class=CurrentUserSerializer)
    def me(self, request):
        """The requesting user's own record.

        Open to any authenticated role — including system administrators, who are
        otherwise barred from case content but still need their own profile.
        """
        return Response(CurrentUserSerializer(request.user).data)
