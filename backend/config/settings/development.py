"""Development settings — Multipass VM + Docker Compose (spec §2.1)."""

from decouple import config

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE, STORAGES

DEBUG = True

# base.py uses manifest static storage, which refuses to serve any file absent
# from a collectstatic manifest. In development nothing has been collected, so
# every HTML response — the admin, DRF's browsable API, the test client — would
# raise. Hashing is a production cache-busting concern; drop it here.
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS += ["django_extensions", "debug_toolbar"]
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]


def _show_toolbar(request):
    """Containers get an unpredictable IP, so INTERNAL_IPS cannot be used.

    Reads `settings.DEBUG` at call time rather than closing over the module-level
    literal: pytest-django forces DEBUG=False, and a captured True would make the
    toolbar render during tests and reverse its `djdt` namespace, which
    config/urls.py only registers when DEBUG is on.
    """
    from django.conf import settings as active_settings

    return active_settings.DEBUG


DEBUG_TOOLBAR_CONFIG = {"SHOW_TOOLBAR_CALLBACK": _show_toolbar}

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

CORS_ALLOW_ALL_ORIGINS = True

# Lockouts during development make debugging auth painful.
AXES_ENABLED = False

# The role switcher: sign in as any account without a password, to check what a
# role sees. See apps/users/dev_views.py for why it is gated as heavily as it
# is. Env-overridable so it can be turned off in a shared dev environment.
DEV_ROLE_SWITCHER = config("DEV_ROLE_SWITCHER", default=True, cast=bool)
