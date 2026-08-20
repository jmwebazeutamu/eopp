from rest_framework.routers import DefaultRouter

from .views import FollowUpViewSet

app_name = "followups"

router = DefaultRouter()
router.register("", FollowUpViewSet, basename="followup")

urlpatterns = router.urls
