from rest_framework.routers import DefaultRouter

from .views import GrievanceViewSet

app_name = "grievances"

router = DefaultRouter()
router.register("", GrievanceViewSet, basename="grievance")

urlpatterns = router.urls
