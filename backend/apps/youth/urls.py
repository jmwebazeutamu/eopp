from rest_framework.routers import DefaultRouter

from .views import YouthViewSet

router = DefaultRouter()
router.register("", YouthViewSet, basename="youth")

urlpatterns = router.urls
