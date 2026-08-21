"""The role switcher's gates.

The tool itself is a convenience; these tests are not. It mints a token for any
account without a password, so what is worth pinning is that it refuses to do
so anywhere it should not — and that the token it mints is indistinguishable
from a real one, because a switcher that produces a subtly different session
misrepresents the thing it exists to preview.

There are two independent gates and they are tested separately, because they
fail differently:

* **Routing.** `config/urls.py` only adds the paths when DEBUG and the flag are
  both on *at import*. In production neither is, so the path does not exist.
  pytest imports the URLconf with DEBUG false, so the default state of this
  module is "no route at all" — which `TestRouting` asserts directly.
* **The view.** Re-checks both settings at call time. This is the gate that
  matters if the URLconf is ever built under a different settings module, and
  the only way to test it is to rebuild the URLconf with the gates open and
  then close one. `TestViewGate` does exactly that.

Testing only the routing layer would leave the view's check unexercised, and it
is the check that has to hold when somebody adds a second URLconf.
"""

import importlib

import pytest
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import config.urls

from apps.users.models import AccountStatus, Role, User

pytestmark = pytest.mark.django_db

# Hardcoded rather than reversed: reverse() cannot express "this path should
# not resolve", which is half of what is being asserted here.
ACCOUNTS = "/api/v1/dev/accounts/"
IMPERSONATE = "/api/v1/dev/impersonate/"


def _rebuild_urlconf():
    clear_url_caches()
    importlib.reload(config.urls)


@pytest.fixture(autouse=True)
def _silence_debug_toolbar(settings):
    """These tests turn DEBUG on, which makes debug_toolbar try to render.

    `config/urls.py` only registers the `djdt` namespace when DEBUG is true at
    import, and pytest imports it with DEBUG false — so a test that flips DEBUG
    on gets `NoReverseMatch: 'djdt' is not a registered namespace` from the
    toolbar's own template, on every HTML response.

    Overriding the callback rather than stripping the middleware: the callback
    is the documented seam (`development.py::_show_toolbar`), and removing
    middleware would change the request path under test.
    """
    settings.DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": lambda request: False}


@pytest.fixture
def caller(db):
    return User.objects.create_user(
        username="switcher-caller",
        password="correct-horse-battery",
        full_name="Switcher Caller",
        role=Role.SYSTEM_ADMIN,
    )


@pytest.fixture
def target(db):
    return User.objects.create_user(
        username="switch-target",
        password="correct-horse-battery",
        full_name="Switch Target",
        role=Role.CASE_MANAGER,
    )


@pytest.fixture
def client_as(caller):
    client = APIClient()
    client.force_authenticate(caller)
    return client


@pytest.fixture
def routed(settings):
    """Rebuild the URLconf with both gates open, and tear it back down.

    The teardown reload matters as much as the setup one: leaving the dev
    routes registered would let a later test in the same session reach them by
    accident, which is the failure this whole module exists to prevent.
    """
    settings.DEBUG = True
    settings.DEV_ROLE_SWITCHER = True
    _rebuild_urlconf()
    yield
    settings.DEBUG = False
    settings.DEV_ROLE_SWITCHER = False
    _rebuild_urlconf()


class TestRouting:
    """The outer gate: with DEBUG off at import, the paths do not exist."""

    def test_no_route_exists_in_the_default_test_configuration(self, client_as):
        """pytest imports the URLconf with DEBUG false, as production does."""
        assert client_as.get(ACCOUNTS).status_code == 404
        assert client_as.post(IMPERSONATE, {"username": "anyone"}, format="json").status_code == 404

    def test_the_routes_appear_only_when_both_gates_are_open(self, client_as, settings):
        settings.DEBUG = True
        settings.DEV_ROLE_SWITCHER = False
        _rebuild_urlconf()
        try:
            assert client_as.get(ACCOUNTS).status_code == 404

            settings.DEV_ROLE_SWITCHER = True
            _rebuild_urlconf()
            assert client_as.get(ACCOUNTS).status_code == 200
        finally:
            settings.DEBUG = False
            settings.DEV_ROLE_SWITCHER = False
            _rebuild_urlconf()

    def test_production_settings_disable_it_as_a_literal(self):
        """Not `config(...)` — no .env line may turn impersonation on.

        Read as source rather than by importing production settings, which
        would require Sentry and the production environment to be present.
        """
        from pathlib import Path

        source = (Path(__file__).resolve().parents[3] / "config" / "settings" / "production.py").read_text()
        assert "DEV_ROLE_SWITCHER = False" in source
        assert 'config("DEV_ROLE_SWITCHER' not in source


class TestViewGate:
    """The inner gate: the view re-checks, at call time, with routes in place."""

    def test_debug_off_refuses_even_though_the_route_resolves(self, client_as, routed, settings):
        settings.DEBUG = False
        assert client_as.get(ACCOUNTS).status_code == 404
        assert client_as.post(IMPERSONATE, {"username": "anyone"}, format="json").status_code == 404

    def test_flag_off_refuses_even_though_the_route_resolves(self, client_as, routed, settings):
        settings.DEV_ROLE_SWITCHER = False
        assert client_as.get(ACCOUNTS).status_code == 404
        assert client_as.post(IMPERSONATE, {"username": "anyone"}, format="json").status_code == 404

    def test_the_check_is_read_at_call_time_not_captured_at_import(self, client_as, routed, settings):
        """The debug-toolbar lesson, applied here.

        `development.py` documents it: a module-level capture of DEBUG stays
        True while pytest-django sets it False at runtime. If the view had
        captured either setting at import, flipping it here would not change
        the answer and the production gate would be decorative.
        """
        assert client_as.get(ACCOUNTS).status_code == 200

        settings.DEBUG = False
        assert client_as.get(ACCOUNTS).status_code == 404

        settings.DEBUG = True
        assert client_as.get(ACCOUNTS).status_code == 200

    def test_anonymous_callers_are_refused(self, routed, target):
        """It escalates an existing session; it does not create one."""
        anonymous = APIClient()
        assert anonymous.get(ACCOUNTS).status_code in (401, 403)
        assert anonymous.post(IMPERSONATE, {"username": target.username}, format="json").status_code in (401, 403)


class TestImpersonation:
    def test_returns_a_usable_token_for_the_target(self, client_as, routed, target):
        response = client_as.post(IMPERSONATE, {"username": target.username}, format="json")
        assert response.status_code == 200

        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me = fresh.get("/api/v1/users/me/")
        assert me.status_code == 200
        assert me.data["username"] == target.username

    def test_the_token_carries_the_same_claims_a_real_login_would(self, client_as, routed, target):
        """The mobile client reads `role` and `full_name` offline.

        Minting by hand with `RefreshToken.for_user` would omit both, and the
        switcher would produce a session that behaves differently from the one
        it claims to be previewing.
        """
        from rest_framework_simplejwt.tokens import AccessToken

        response = client_as.post(IMPERSONATE, {"username": target.username}, format="json")
        claims = AccessToken(response.data["access"])

        assert claims["role"] == target.role
        assert claims["full_name"] == target.full_name

    def test_suspended_accounts_are_refused_as_the_real_login_refuses_them(self, client_as, routed, target):
        target.account_status = AccountStatus.SUSPENDED
        target.save(update_fields=["account_status"])

        response = client_as.post(IMPERSONATE, {"username": target.username}, format="json")
        assert response.status_code == 400
        assert "suspended" in response.data["detail"].lower()

    def test_an_unknown_username_is_a_404_not_a_500(self, client_as, routed):
        assert client_as.post(IMPERSONATE, {"username": "nobody-here"}, format="json").status_code == 404

    def test_accounts_carry_the_resolved_access_row(self, client_as, routed, target):
        """The panel previews §7 from this, so it must be the resolved row.

        Same serializer as /users/me/, which is what stops the preview drifting
        from what the app reports after the switch.
        """
        response = client_as.get(ACCOUNTS)
        row = next(a for a in response.data["accounts"] if a["username"] == target.username)

        assert row["access"]["case_scope"] == "OWN_CASELOAD"
        assert row["access"]["delivery_write"] is True
        assert row["access"]["group_scope"] == "NONE"
        assert response.data["signed_in_as"] == "switcher-caller"
