from rest_framework.routers import DefaultRouter

from .views import TrainingEnrolmentViewSet

app_name = "training"

router = DefaultRouter()
router.register("", TrainingEnrolmentViewSet, basename="training-enrolment")

urlpatterns = router.urls
