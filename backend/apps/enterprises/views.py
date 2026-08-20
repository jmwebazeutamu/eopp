"""Enterprise API — spec §4.8, Sprint 6.

Scoped as case content. An **enterprise development officer** sees the
enterprises she recorded — the §7 LINKED scope her role has carried since
Sprint 0 with nothing to resolve it through until now.

Everything that changes state is an action, because each one does more than set
a field: approving a plan is a decision, disbursing moves money and moves the
case to Placed, and closing a business is a fact somebody has to explain.
"""

from django.core.exceptions import ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanRecordDelivery, IsOperational, ScopedQuerySetMixin

from . import services
from .models import BusinessPlanStatus, Enterprise, EnterpriseMilestone
from .serializers import (
    CloseEnterpriseSerializer,
    DisbursementSerializer,
    EnterpriseMilestoneSerializer,
    EnterpriseSerializer,
    MilestoneOutcomeSerializer,
    MissMilestoneSerializer,
    PlanStatusSerializer,
    TradingSerializer,
)


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class EnterpriseViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """§4.8, scoped per §7."""

    queryset = Enterprise.objects.select_related(
        "case", "case__youth", "case__case_manager", "recorded_by", "source_referral"
    ).prefetch_related("milestones")
    serializer_class = EnterpriseSerializer
    permission_classes = [IsOperational, CanRecordDelivery]

    scope_kind = "case"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"
    linked_case_prefix = "case__"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = {
        "case": ["exact"],
        "business_plan_status": ["exact", "in"],
        "market_linkage_status": ["exact"],
        "case__woreda": ["exact"],
    }
    search_fields = ["case__youth__full_name", "business_name", "sector"]
    ordering_fields = ["created_at", "disbursement_date"]

    def perform_create(self, serializer):
        enterprise = serializer.save(recorded_by=self.request.user)
        enterprise.case.touch()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(
                    queryset, param="business_plan_status", field="business_plan_status", choices=BusinessPlanStatus
                ),
            )
        )

    @action(detail=False, methods=["get"], url_path="awaiting-disbursement")
    def awaiting_disbursement(self, request):
        """Approved plans with no money against them.

        The officer's queue: a youth with an approved plan and nothing
        disbursed is waiting on the programme, not on herself.
        """
        queryset = self.filter_queryset(self.get_queryset()).filter(
            pk__in=Enterprise.objects.awaiting_disbursement().values("pk")
        )
        return Response(EnterpriseSerializer(queryset, many=True).data)

    @action(detail=True, methods=["post"], url_path="plan-status")
    def plan_status(self, request, pk=None):
        enterprise = self.get_object()
        payload = PlanStatusSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.set_plan_status(enterprise, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseSerializer(enterprise).data)

    @action(detail=True, methods=["post"])
    def disburse(self, request, pk=None):
        enterprise = self.get_object()
        payload = DisbursementSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.record_disbursement(enterprise, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseSerializer(enterprise).data)

    @action(detail=True, methods=["post"])
    def trading(self, request, pk=None):
        enterprise = self.get_object()
        payload = TradingSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.record_trading(enterprise, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseSerializer(enterprise).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        enterprise = self.get_object()
        payload = CloseEnterpriseSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.close_enterprise(enterprise, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseSerializer(enterprise).data)

    @action(detail=True, methods=["get", "post"])
    def milestones(self, request, pk=None):
        enterprise = self.get_object()
        if request.method == "GET":
            return Response(EnterpriseMilestoneSerializer(enterprise.milestones.all(), many=True).data)

        serializer = EnterpriseMilestoneSerializer(data={**request.data, "enterprise": str(enterprise.pk)})
        serializer.is_valid(raise_exception=True)
        try:
            milestone = services.add_milestone(
                enterprise,
                milestone_name=serializer.validated_data["milestone_name"],
                target_date=serializer.validated_data["target_date"],
                note=serializer.validated_data.get("note", ""),
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseMilestoneSerializer(milestone).data, status=201)


class MilestoneViewSet(ScopedQuerySetMixin, viewsets.GenericViewSet):
    """Settling one milestone. Achieved or missed — never deleted."""

    queryset = EnterpriseMilestone.objects.select_related("enterprise", "enterprise__case")
    serializer_class = EnterpriseMilestoneSerializer
    permission_classes = [IsOperational, CanRecordDelivery]

    scope_kind = "case"
    woreda_field = "enterprise__case__woreda"
    case_manager_field = "enterprise__case__case_manager_id"
    linked_case_prefix = "enterprise__case__"

    @action(detail=True, methods=["post"])
    def achieve(self, request, pk=None):
        milestone = self.get_object()
        payload = MilestoneOutcomeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.achieve_milestone(milestone, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseMilestoneSerializer(milestone).data)

    @action(detail=True, methods=["post"])
    def miss(self, request, pk=None):
        """Record that it was not met, with the reason. Not a deletion.

        A plan whose missed milestones disappear reads as a plan that went well.
        """
        milestone = self.get_object()
        payload = MissMilestoneSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.miss_milestone(milestone, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(EnterpriseMilestoneSerializer(milestone).data)
