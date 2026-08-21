"""The role switcher — a development-only account switcher and §7 previewer.

Signing in and out to check a scope is slow enough that it does not get done,
and the memory of what each role sees is the thing being tested. This mints a
token for another account without a password, so a permission boundary can be
crossed in one click and crossed back.

That is an impersonation endpoint. These are personal case records for
vulnerable young people, and an unauthenticated token faucet against this
database would be a data protection incident of the first order. It is
therefore gated four ways, and every gate is independent:

1. `settings.DEBUG` must be true.
2. `settings.DEV_ROLE_SWITCHER` must be true. `base.py` defaults it False,
   `development.py` turns it on, and `production.py` sets it False as a
   literal — not from the environment, so no stray `.env` line can turn it on.
3. `config/urls.py` only routes to it when both of the above hold, so in
   production the path does not exist at all rather than existing and refusing.
4. The caller must already be authenticated. It escalates an existing session;
   it does not create one from nothing.

Both checks are read at *call* time, never captured at import. `development.py`
already carries that lesson for the debug toolbar: pytest-django forces
`DEBUG=False` at runtime, so a module-level capture stays True and the gate
silently stops gating. `test_dev_switcher.py` pins the 404.

The token is minted through `ScopedTokenObtainPairSerializer.get_token`, the
same path `POST /users/token/` uses, so an impersonated session carries the
identical `role` and `full_name` claims the mobile client reads offline. Minting
it by hand here would produce a token that behaves subtly differently from a
real one, which would make this tool lie about the thing it exists to show.

A suspended account is refused, because the real login refuses it. A switcher
that can reach a state the product cannot is not previewing the product.
"""

import logging

from django.conf import settings
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AccountStatus, User
from .serializers import CurrentUserSerializer, ScopedTokenObtainPairSerializer

logger = logging.getLogger(__name__)


def dev_switcher_enabled() -> bool:
    """Both gates, read now rather than at import. See the module docstring."""
    return bool(settings.DEBUG) and bool(getattr(settings, "DEV_ROLE_SWITCHER", False))


class _DevToolView(APIView):
    """Shared gate. 404 rather than 403: the endpoint does not exist here."""

    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        if not dev_switcher_enabled():
            raise Http404
        super().initial(request, *args, **kwargs)


@extend_schema(exclude=True)
class DevAccountsView(_DevToolView):
    """Every account, with the §7 row each one resolves to.

    Serialised with `CurrentUserSerializer` — the same shape `/users/me/`
    returns — so the panel's preview of a role cannot drift from what the app
    will actually report after switching to it. A second, simpler serializer
    here would be a second description of §7, and the one that gets forgotten
    is always the one on screen.
    """

    def get(self, request):
        accounts = User.objects.order_by("role", "full_name")
        return Response(
            {
                "accounts": CurrentUserSerializer(accounts, many=True).data,
                "signed_in_as": request.user.username,
            }
        )


class _ImpersonateSerializer(serializers.Serializer):
    username = serializers.CharField()


@extend_schema(exclude=True)
class DevImpersonateView(_DevToolView):
    """Mint a token pair for another account, no password.

    Returns the same body as `POST /users/token/` so the client can store it
    through exactly the same code path as a real sign-in.
    """

    def post(self, request):
        form = _ImpersonateSerializer(data=request.data)
        form.is_valid(raise_exception=True)
        username = form.validated_data["username"]

        try:
            target = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({"detail": f"No account named {username!r}."}, status=status.HTTP_404_NOT_FOUND)

        if target.account_status != AccountStatus.ACTIVE:
            # Named rather than generic: "this account is suspended" is the
            # answer somebody is looking for when the switch does not work.
            return Response(
                {"detail": f"{username} is {target.get_account_status_display().lower()} and cannot hold a token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Loud on purpose. A line in the log is what makes it obvious if this
        # ever runs somewhere it should not.
        logger.warning("dev role switcher: %s -> %s", request.user.username, target.username)

        refresh = ScopedTokenObtainPairSerializer.get_token(target)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": CurrentUserSerializer(target).data,
            }
        )
