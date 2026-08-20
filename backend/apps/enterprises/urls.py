from rest_framework.routers import DefaultRouter

from .views import EnterpriseViewSet, MilestoneViewSet

app_name = "enterprises"

router = DefaultRouter()
router.register("milestones", MilestoneViewSet, basename="milestone")
router.register("", EnterpriseViewSet, basename="enterprise")

urlpatterns = router.urls
