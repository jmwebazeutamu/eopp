"""Training enrolment API — spec §4.5, Sprint 5.

Scoped as case content (§7): a case manager sees her caseload's enrolments, a
supervisor her woreda's, and a **trainer sees the ones she recorded** — the
LINKED scope §7 gives the role, resolved through the entity the role owns.

Status moves through actions rather than through PATCH. `POST .../complete/`
stamps the completion date, sets `triggers_onward_referral` and touches the
case; a PATCH setting `completion_status` would do none of it.
"""

from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanRecordDelivery, IsOperational, ScopedQuerySetMixin

from . import services
from .models import CompletionStatus, TrainingEnrolment
from .serializers import (
    CompleteSerializer,
    DropOutSerializer,
    FailAssessmentSerializer,
    TrainingEnrolmentSerializer,
)


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class TrainingEnrolmentViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """§4.5, scoped per §7."""

    queryset = TrainingEnrolment.objects.select_related(
        "case", "case__youth", "case__case_manager", "training_provider", "recorded_by", "source_referral"
    )
    serializer_class = TrainingEnrolmentSerializer
    permission_classes = [IsOperational, CanRecordDelivery]

    scope_kind = "case"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"
    # A trainer is linked through her own enrolments, and this viewset's rows
    # hang off a case, so the lookup walks back through it.
    linked_case_prefix = "case__"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "case": ["exact"],
        "completion_status": ["exact", "in"],
        "training_type": ["exact"],
        "training_provider": ["exact"],
        "case__woreda": ["exact"],
    }
    search_fields = ["case__youth__full_name", "training_provider__partner_name", "trade_or_skill_area"]
    ordering_fields = ["enrolment_date", "end_date", "completion_status"]
    ordering = ["-enrolment_date"]

    def perform_create(self, serializer):
        # §4.5 has no "recorded by" field; §9 requires an actor on every record,
        # and it is also what scopes a trainer's own list.
        enrolment = serializer.save(recorded_by=self.request.user)
        enrolment.case.touch()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="completion_status", field="completion_status", choices=CompletionStatus),
            )
        )

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Finish the course. This is what raises the onward-referral prompt."""
        enrolment = self.get_object()
        payload = CompleteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.complete(enrolment, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(TrainingEnrolmentSerializer(enrolment).data)

    @action(detail=True, methods=["post"], url_path="drop-out")
    def drop_out(self, request, pk=None):
        enrolment = self.get_object()
        payload = DropOutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.drop_out(
                enrolment,
                reason=payload.validated_data["dropout_reason"],
                dropout_date=payload.validated_data.get("dropout_date"),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(TrainingEnrolmentSerializer(enrolment).data)

    @action(detail=True, methods=["post"], url_path="fail-assessment")
    def fail_assessment(self, request, pk=None):
        """Attended to the end and did not pass — not a dropout."""
        enrolment = self.get_object()
        payload = FailAssessmentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.fail_assessment(enrolment, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(TrainingEnrolmentSerializer(enrolment).data)

    @action(detail=True, methods=["post"], url_path="attendance")
    def attendance(self, request, pk=None):
        enrolment = self.get_object()
        try:
            services.record_attendance_rate(
                enrolment, attendance_rate=request.data.get("attendance_rate"), actor=request.user
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(TrainingEnrolmentSerializer(enrolment).data, status=status.HTTP_200_OK)
