"""Grievance API — spec §4.10, Sprint 6.

Scoped by **woreda**, not by caseload, because §4.10 makes the case optional: a
complaint from an employer about a partner names no youth, and a channel only
its complainant's case manager can see is not a channel.

Two narrowings on top of that:

* **Sensitive types** — safeguarding and staff conduct — are visible only to the
  assigned staff member and the administrator. The person complained about may
  be the supervisor who would otherwise read it.
* **A LINKED role sees nothing here.** A trainer or a partner-staff account has
  no business reading complaints about other people's cases, and the fail-closed
  default gives that for free.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanAccessCases, IsOperational, ScopedQuerySetMixin

from . import services
from .models import Grievance, ResolutionStatus
from .serializers import CloseSerializer, GrievanceSerializer, ResolveSerializer


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class GrievanceViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """§4.10, scoped by woreda and narrowed for sensitive types."""

    queryset = Grievance.objects.select_related(
        "case", "case__youth", "assigned_staff", "about_partner", "related_referral"
    )
    serializer_class = GrievanceSerializer
    permission_classes = [IsOperational, CanAccessCases]

    scope_kind = "case"
    # The grievance's own woreda, not the case's: most complaints have no case.
    woreda_field = "woreda"
    case_manager_field = "case__case_manager_id"
    linked_case_prefix = "case__"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "resolution_status": ["exact", "in"],
        "complaint_type": ["exact"],
        "raised_by": ["exact"],
        "about_partner": ["exact"],
        "referral_quality_feedback_flag": ["exact"],
        "woreda": ["exact"],
    }
    search_fields = ["summary", "complainant_name", "case__youth__full_name"]
    ordering_fields = ["date_raised", "resolution_status"]
    ordering = ["-date_raised"]

    def get_queryset(self):
        """Scope by place, then hide what this user must not read."""
        return super().get_queryset().visible_to(self.request.user)

    def perform_create(self, serializer):
        grievance = serializer.save(recorded_by=self.request.user)
        if grievance.case_id:
            grievance.case.touch()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="resolution_status", field="resolution_status", choices=ResolutionStatus),
            )
        )

    @action(detail=False, methods=["get"])
    def overdue(self, request):
        """Open past the service standard.

        A complaints process nobody answers is worse than none: it collects the
        complaint, creates the expectation, and does nothing with it.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(
            pk__in=services.overdue(Grievance.objects.all()).values("pk")
        )
        return Response(
            {
                "threshold_days": settings.GRIEVANCE_RESPONSE_DAYS,
                "results": GrievanceSerializer(queryset, many=True).data,
            }
        )

    @action(detail=False, methods=["get"], url_path="partner-feedback")
    def partner_feedback(self, request):
        """Referral-quality complaints, by partner.

        The qualitative counterpart to §8's failure rates. A partner with a good
        confirmation median and six quality complaints is not a good partner.
        """
        return Response({"rows": services.partner_quality_feedback()})

    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        grievance = self.get_object()
        try:
            services.start_work(grievance, actor=request.user)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GrievanceSerializer(grievance).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        grievance = self.get_object()
        payload = ResolveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.resolve(grievance, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GrievanceSerializer(grievance).data)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        """Shut the file without resolving it.

        Kept apart from `resolve` because §4.10 keeps them apart: folding the
        two would inflate the resolution rate with every complaint whose
        complainant withdrew or could not be traced.
        """
        grievance = self.get_object()
        payload = CloseSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.close_without_resolution(grievance, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GrievanceSerializer(grievance).data)
