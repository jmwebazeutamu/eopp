from rest_framework.routers import DefaultRouter

from .views import PlacementViewSet, RetentionCheckViewSet

app_name = "placements"

router = DefaultRouter()
router.register("checks", RetentionCheckViewSet, basename="retention-check")
router.register("", PlacementViewSet, basename="placement")

urlpatterns = router.urls
