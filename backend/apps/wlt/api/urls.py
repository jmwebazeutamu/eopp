"""WLT routes, under /api/v1/wlt/."""

from rest_framework.routers import DefaultRouter

from .views import (
    BeneficiaryProfileViewSet,
    GroupViewSet,
    MeetingViewSet,
    PhaseEventViewSet,
    ReportViewSet,
    ServiceLinkageViewSet,
    SyncConflictViewSet,
)

app_name = "wlt"

router = DefaultRouter()
router.register("groups", GroupViewSet, basename="group")
router.register("meetings", MeetingViewSet, basename="meeting")
router.register("linkages", ServiceLinkageViewSet, basename="linkage")
router.register("phase-events", PhaseEventViewSet, basename="phase-event")
router.register("profiles", BeneficiaryProfileViewSet, basename="profile")
router.register("sync-conflicts", SyncConflictViewSet, basename="sync-conflict")
router.register("reports", ReportViewSet, basename="report")

urlpatterns = router.urls
