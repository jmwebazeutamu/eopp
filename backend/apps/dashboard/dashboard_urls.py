"""Tier 1 routes — server-rendered, outside /api/v1/.

`CASE_MANAGER_DASHBOARD.md` §3. These are pages, not API endpoints, so they sit
at the site root rather than under the versioned API namespace.
"""

from django.urls import path

from .case_manager import CaseManagerDashboardView, WorkQueueListView

app_name = "dashboard"

urlpatterns = [
    path("", CaseManagerDashboardView.as_view(), name="case-manager"),
    path("queue/<slug:queue_slug>/", WorkQueueListView.as_view(), name="queue"),
]
