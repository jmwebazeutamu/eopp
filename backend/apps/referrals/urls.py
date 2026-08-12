from rest_framework.routers import DefaultRouter

from .views import (
    FailureReasonCodeViewSet,
    OutcomeTypeViewSet,
    ReferralCategoryViewSet,
    ReferralViewSet,
)

router = DefaultRouter()
# Taxonomy prefixes are registered first: the referral router uses an empty
# prefix, which would otherwise capture "categories/" as a referral id lookup.
router.register("categories", ReferralCategoryViewSet, basename="referral-category")
router.register("outcome-types", OutcomeTypeViewSet, basename="outcome-type")
router.register("failure-reasons", FailureReasonCodeViewSet, basename="failure-reason")
router.register("", ReferralViewSet, basename="referral")

urlpatterns = router.urls
