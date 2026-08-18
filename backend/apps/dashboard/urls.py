"""The four tiers, one endpoint each.

`dashboard_handoff_youth_employment/README.md` §1: four small dashboards, not one
with role-based hiding. A single dashboard with permissions always converges on
the union of every stakeholder's requirements, and the case manager ends up
looking at donor indicators.

Separate endpoints rather than one fat payload for the same reason the handoff
caps cards per tier: nobody should pay for the donor's disaggregation while
opening their own work queue.
"""

from django.urls import path

from .views import DonorView, MyWorkView, ProgrammeDashboardView, ProgrammeManagerView, WoredaSupervisorView

urlpatterns = [
    # Kept at the root for the screen that shipped first.
    path("", ProgrammeDashboardView.as_view(), name="programme-dashboard"),
    path("my-work/", MyWorkView.as_view(), name="dashboard-my-work"),
    path("woreda/", WoredaSupervisorView.as_view(), name="dashboard-woreda"),
    path("programme/", ProgrammeManagerView.as_view(), name="dashboard-programme"),
    path("results/", DonorView.as_view(), name="dashboard-results"),
]
