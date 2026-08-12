from rest_framework.routers import DefaultRouter

from .views import CaseViewSet, PathwayAssignmentViewSet, ProfilingRecordViewSet

router = DefaultRouter()
# Registered before the catch-all "" route: DefaultRouter matches in order, and
# an empty prefix would otherwise swallow "profiling/" as a case lookup.
router.register("profiling", ProfilingRecordViewSet, basename="profiling")
router.register("pathways", PathwayAssignmentViewSet, basename="pathway")
router.register("", CaseViewSet, basename="case")

urlpatterns = router.urls
