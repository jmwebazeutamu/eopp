"""Case API — spec §4.2, §10 Sprint 1."""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.users.models import Role, User
from apps.users.permissions import CanAccessCases, IsOperational, ScopedQuerySetMixin

from .models import Case, CaseStatus, PathwayAssignment, ProfilingRecord
from .serializers import (
    CaseAssignmentSerializer,
    CaseListSerializer,
    CaseSerializer,
    PathwayAssignmentSerializer,
    PathwayRevisionSerializer,
    ProfilingRecordSerializer,
)


@extend_schema(tags=["cases"])
class CaseViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """The case record, scoped per spec §7."""

    queryset = Case.objects.select_related("youth", "case_manager", "next_action_owner")
    serializer_class = CaseSerializer
    permission_classes = [IsOperational, CanAccessCases]

    scope_kind = "case"
    woreda_field = "woreda"
    case_manager_field = "case_manager_id"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["case_status", "woreda", "case_manager"]
    search_fields = ["youth__full_name", "youth__phone_number", "youth__national_or_kebele_id"]
    ordering_fields = ["last_activity_date", "opened_date", "case_status"]
    ordering = ["-last_activity_date"]

    def get_serializer_class(self):
        if self.action == "list":
            return CaseListSerializer
        if self.action == "assign":
            return CaseAssignmentSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        case = serializer.save()
        case.touch()

    def perform_update(self, serializer):
        case = serializer.save()
        case.touch()

    def perform_destroy(self, instance):
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed(
            "DELETE",
            detail="Cases are closed with a status of Exited and an exit reason, never deleted (spec §9).",
        )

    @extend_schema(request=CaseAssignmentSerializer, responses=CaseSerializer)
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Reassign the case to another case manager.

        Reassignment is a case event, so it moves `last_activity_date`. The
        history row written by django-simple-history carries the actor.
        """
        case = self.get_object()
        serializer = CaseAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        case.case_manager = serializer.validated_data["case_manager"]
        reason = serializer.validated_data.get("reason", "")
        if reason:
            case._change_reason = reason  # picked up by simple_history
        case.save()
        case.touch()

        return Response(CaseSerializer(case, context=self.get_serializer_context()).data)

    @extend_schema(responses=CaseListSerializer(many=True))
    @action(detail=False, methods=["get"], url_path="my-caseload")
    def my_caseload(self, request):
        """Open cases assigned to the requesting user.

        Distinct from the scoped list: a supervisor's list covers their whole
        woreda, but this always answers "what is on *my* desk".
        """
        cases = self.filter_queryset(self.get_queryset()).filter(case_manager=request.user).open()
        page = self.paginate_queryset(cases)
        serializer = CaseListSerializer(page if page is not None else cases, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def stalled(self, request):
        """Cases past the stall threshold — the §8 'Stalled case alerts' dashboard."""
        cases = self.filter_queryset(self.get_queryset()).stalled_beyond_threshold()
        page = self.paginate_queryset(cases)
        serializer = CaseListSerializer(page if page is not None else cases, many=True)
        payload = self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)
        if isinstance(payload.data, dict):
            payload.data["threshold_days"] = settings.STALL_ALERT_THRESHOLD_DAYS
        return payload

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"], url_path="caseload-summary")
    def caseload_summary(self, request):
        """Open cases per case manager, flagged above the ceiling.

        The §8 'Caseload by case manager / woreda' dashboard. Counts respect the
        caller's scope, so a supervisor sees only their own woredas.
        """
        visible = self.filter_queryset(self.get_queryset())
        rows = (
            User.objects.filter(role=Role.CASE_MANAGER)
            .annotate(
                open_cases=Count(
                    "managed_cases",
                    filter=Q(managed_cases__in=visible, managed_cases__case_status__in=CaseStatus.open_statuses()),
                )
            )
            .values("id", "full_name", "woreda_assignment", "open_cases")
            .order_by("-open_cases")
        )
        ceiling = settings.CASELOAD_CEILING
        return Response(
            {
                "caseload_ceiling": ceiling,
                "case_managers": [{**row, "over_ceiling": row["open_cases"] > ceiling} for row in rows],
            },
            status=status.HTTP_200_OK,
        )


class _CaseChildViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """Shared scoping for records hanging off a Case.

    Profiling and pathway rows carry no woreda or case manager of their own, so
    every scope resolves through the parent case. Declaring the lookups once
    keeps a future child entity from accidentally shipping unscoped.
    """

    permission_classes = [IsOperational, CanAccessCases]
    scope_kind = "case"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"

    def perform_destroy(self, instance):
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed(
            "DELETE",
            detail="Assessment history is retained (spec §9). Record a new assessment instead.",
        )


@extend_schema(tags=["cases"])
class ProfilingRecordViewSet(_CaseChildViewSet):
    """Profiling and Eligibility Records — spec §4.3.

    Revisable: posting a new record for a case supersedes the previous one by
    recency rather than overwriting it, so the assessment history survives.
    """

    queryset = ProfilingRecord.objects.select_related("case", "case__youth", "assessor")
    serializer_class = ProfilingRecordSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["case", "priority_flag"]
    ordering_fields = ["assessed_date", "created_at"]
    ordering = ["-assessed_date"]


@extend_schema(tags=["cases"])
class PathwayAssignmentViewSet(_CaseChildViewSet):
    """Pathway Assignments — spec §4.4."""

    queryset = PathwayAssignment.objects.select_related("case", "case__youth", "assessor")
    serializer_class = PathwayAssignmentSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["case", "selected_pathway", "is_current"]
    ordering_fields = ["assessment_date", "created_at"]
    ordering = ["-assessment_date"]

    @extend_schema(request=PathwayRevisionSerializer, responses=PathwayAssignmentSerializer)
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        """Supersede this assignment with a new current one.

        Modelled as an explicit action rather than a PATCH: a revision creates a
        second row and rewires three references atomically (§4.4). Expressing
        that as a field update would invite a client to half-apply it.
        """
        assignment = self.get_object()
        serializer = PathwayRevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            replacement = assignment.revise(
                selected_pathway=data["selected_pathway"],
                assessor=request.user,
                revision_reason=data["revision_reason"],
                **{k: v for k, v in data.items() if k in {"assessed_interests", "capacities", "barriers"}},
            )
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)

        return Response(
            PathwayAssignmentSerializer(replacement, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )
