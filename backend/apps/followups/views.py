"""Follow-up API — spec §4.9, Sprint 6.

Two queues hang off this, and they belong to different people:

* `GET /followups/due/` — Active referrals nobody has contacted. The case
  manager's, and the same condition the §4.13 alert materialises.
* `GET /followups/unverified/` — Completed referrals whose outcome nobody has
  stood behind. **M&E's**, and the work that stands between the recorded
  placement rate and the reportable one.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.referrals.models import Referral
from apps.users.permissions import CanAccessCases, IsOperational, ScopedQuerySetMixin, scope_queryset

from . import services
from .models import ContactOutcome, FollowUp
from .serializers import FollowUpSerializer, VerifyOutcomeSerializer


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class FollowUpViewSet(
    ScopedQuerySetMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """§4.9, scoped per §7.

    No update and no delete. A contact log is a record of attempts, and an
    attempt that can be edited afterwards is not evidence of anything —
    including the "4+ failed attempts" CM-4 counts.
    """

    queryset = FollowUp.objects.select_related(
        "case", "case__youth", "case__case_manager", "conducted_by", "related_referral"
    )
    serializer_class = FollowUpSerializer
    permission_classes = [IsOperational, CanAccessCases]

    scope_kind = "case"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"
    linked_case_prefix = "case__"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "case": ["exact"],
        "contact_outcome": ["exact", "in"],
        "contact_method": ["exact"],
        "related_referral": ["exact"],
        "pathway_revision_flag": ["exact"],
        "case__woreda": ["exact"],
    }
    search_fields = ["case__youth__full_name", "notes"]
    ordering_fields = ["attempt_date"]
    ordering = ["-attempt_date"]

    def perform_create(self, serializer):
        follow_up = serializer.save(conducted_by=self.request.user)
        # Trying to reach a youth is work on the case, whether or not she
        # answered. A case manager who called four times should not have the
        # case counted as stalled for want of activity.
        follow_up.case.touch()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="contact_outcome", field="contact_outcome", choices=ContactOutcome),
            )
        )

    def _scoped_referrals(self):
        return scope_queryset(
            Referral.objects.youth_side().select_related("case", "case__youth", "receiving_partner", "outcome_type"),
            self.request.user,
            scope_kind="case",
            woreda_field="case__woreda",
            case_manager_field="case__case_manager_id",
            linked_case_prefix="case__",
        )

    @action(detail=False, methods=["get"])
    def due(self, request):
        """Active referrals nobody has followed up since the service started."""
        from apps.referrals.serializers import ReferralSerializer

        referrals = services.awaiting_follow_up(self._scoped_referrals(), settings.FOLLOW_UP_DUE_DAYS)
        page = self.paginate_queryset(referrals)
        serializer = ReferralSerializer(page if page is not None else referrals, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=["get"])
    def unverified(self, request):
        """Recorded outcomes nobody has stood behind — the M&E queue.

        This is the gap between the placement rate the platform can compute and
        the one §8.3 says is reportable. It was invisible before Sprint 6,
        because there was no follow-up to close it with.
        """
        from apps.referrals.serializers import ReferralSerializer

        referrals = services.unverified_outcomes(self._scoped_referrals())
        page = self.paginate_queryset(referrals)
        serializer = ReferralSerializer(page if page is not None else referrals, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="verify")
    def verify(self, request, pk=None):
        """Verify the referral outcome this contact concerned — §6.2, §8.3."""
        follow_up = self.get_object()
        payload = VerifyOutcomeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            referral = services.verify_referral_outcome(follow_up, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)

        from apps.referrals.serializers import ReferralSerializer

        return Response(ReferralSerializer(referral).data)
