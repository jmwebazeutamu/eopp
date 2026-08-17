from django.urls import path

from .views import ProgrammeDashboardView

urlpatterns = [
    path("", ProgrammeDashboardView.as_view(), name="programme-dashboard"),
]
