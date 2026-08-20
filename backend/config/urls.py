"""URL configuration.

All REST endpoints live under /api/v1/<app>/ (spec §2). The OpenAPI schema and
docs are served alongside so the React web app and the Flutter client have a
versioned contract to build against.
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

# The admin is a working surface, not a debug tool: §9 puts the referral
# taxonomy under the system administrator, who edits it here. Unbranded it
# still read "Django administration".
admin.site.site_header = "Economic Opportunities Pathway Platform"
admin.site.site_title = "EOPP"
admin.site.index_title = "Administration"

api_v1_patterns = [
    path("users/", include("apps.users.urls")),
    path("locations/", include("apps.locations.urls")),
    path("youth/", include("apps.youth.urls")),
    path("partners/", include("apps.partners.urls")),
    path("cases/", include("apps.cases.urls")),
    path("referrals/", include("apps.referrals.urls")),
    path("alerts/", include("apps.alerts.urls")),
    path("training/", include("apps.training.urls")),
    path("placements/", include("apps.placements.urls")),
    path("enterprises/", include("apps.enterprises.urls")),
    path("followups/", include("apps.followups.urls")),
    path("grievances/", include("apps.grievances.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    # PSNP 6 Women's Livelihoods Transformation — the group module. A second
    # programme on the same platform; see docs/wlt_module_handoff/.
    path("wlt/", include("apps.wlt.api.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # Tier 1 of the dashboard handoff: a server-rendered page, not an API
    # endpoint, so it sits outside the /api/v1/ namespace.
    # Mounted at /ops/dashboard/ rather than /dashboard/.
    #
    # Both this and the React tiers answered to /dashboard/, which never
    # collided while the client ran on its own origin in development. On one
    # origin the client wins that path — it is what a supervisor navigates to —
    # so the server-rendered page, which exists to work with CSS disabled and
    # in one request, keeps its own prefix.
    path("ops/dashboard/", include("apps.dashboard.dashboard_urls")),
    path("api/v1/", include((api_v1_patterns, "v1"), namespace="v1")),
    # api_version is required because DEFAULT_VERSIONING_CLASS is
    # NamespaceVersioning: this view sits outside the "v1" namespace, so without
    # it the generator resolves no version, matches no endpoints, and serves an
    # empty schema with a 200.
    path("api/schema/", SpectacularAPIView.as_view(api_version="v1"), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("healthz/", include("apps.common.urls")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
