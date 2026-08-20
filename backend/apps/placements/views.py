"""Placement API — spec §4.7, Sprint 5.

Scoped as case content (§7). An employer liaison sees the placements she
recorded — the LINKED scope the role has carried since Sprint 0 with nothing to
resolve it through until now.

Two endpoints matter beyond the list:

* `GET /placements/checks/due/` — the retention queue, which is what an employer
  liaison works from. It is the same condition the alert job materialises, so
  the screen and the inbox cannot disagree.
* `POST /placements/{id}/exit/` — records the exit *and* closes the outstanding
  checkpoints, because once she has left, "still there at 90 days" is answered.
"""

from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanRecordDelivery, IsOperational, ScopedQuerySetMixin

from . import services
from .models import Placement, PlacementType, RetentionCheck
from .serializers import (
    ExitSerializer,
    PlacementSerializer,
    RecordCheckSerializer,
    RetentionCheckSerializer,
)


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class PlacementViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """§4.7, scoped per §7."""

    queryset = Placement.objects.select_related(
        "case", "case__youth", "case__case_manager", "recorded_by", "source_referral"
    ).prefetch_related("retention_checks")
    serializer_class = PlacementSerializer
    permission_classes = [IsOperational, CanRecordDelivery]

    scope_kind = "case"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"
    linked_case_prefix = "case__"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "case": ["exact"],
        "placement_type": ["exact"],
        "is_subsidised": ["exact"],
        "case__woreda": ["exact"],
    }
    search_fields = ["case__youth__full_name", "employer_name", "sector"]
    ordering_fields = ["placement_date", "employer_name"]
    ordering = ["-placement_date"]

    def perform_create(self, serializer):
        """Save through the service, so the checkpoints open with the placement.

        A placement written without its three checks is a placement nobody will
        follow up: the queue, the reminders and the retention figure all read
        `RetentionCheck`, and none of them would ever see it.
        """
        placement = serializer.save(recorded_by=self.request.user)
        services.open_checkpoints(placement)
        services._mark_case_placed(placement)
        placement.case.touch()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="placement_type", field="placement_type", choices=PlacementType),
            )
        )

    @action(detail=True, methods=["post"])
    def exit(self, request, pk=None):
        placement = self.get_object()
        payload = ExitSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.record_exit(
                placement,
                exit_date=payload.validated_data["exit_date"],
                exit_reason=payload.validated_data["exit_reason"],
                note=payload.validated_data.get("exit_note", ""),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PlacementSerializer(placement).data)


class RetentionCheckViewSet(
    ScopedQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """The 30/60/90-day checkpoints, and the queue of the ones that are due."""

    queryset = RetentionCheck.objects.select_related(
        "placement", "placement__case", "placement__case__youth", "checked_by"
    )
    serializer_class = RetentionCheckSerializer
    permission_classes = [IsOperational, CanRecordDelivery]

    scope_kind = "case"
    woreda_field = "placement__case__woreda"
    case_manager_field = "placement__case__case_manager_id"
    linked_case_prefix = "placement__case__"

    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = {"status": ["exact"], "checkpoint": ["exact"], "placement": ["exact"]}
    ordering_fields = ["due_date", "checkpoint"]
    ordering = ["due_date"]

    @action(detail=False, methods=["get"], url_path="due")
    def due(self, request):
        """Checks whose date has passed and which nobody has answered.

        The same queryset the alert job materialises, scoped to this user. The
        screen and the inbox read one condition, so a check cleared in one
        cannot linger in the other.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(pk__in=RetentionCheck.objects.due().values("pk"))
        page = self.paginate_queryset(queryset)
        serializer = RetentionCheckSerializer(page if page is not None else queryset, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="record")
    def record(self, request, pk=None):
        check = self.get_object()
        payload = RecordCheckSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.record_check(
                check,
                status=payload.validated_data["status"],
                checked_on=payload.validated_data.get("checked_on"),
                note=payload.validated_data.get("note", ""),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(RetentionCheckSerializer(check).data)
