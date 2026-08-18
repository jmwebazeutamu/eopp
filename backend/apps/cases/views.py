"""Case API — spec §4.2, §10 Sprint 1."""

from django.utils import timezone
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.models import Role, User
from apps.users.permissions import CanAccessCases, IsOperational, ScopedQuerySetMixin

from .models import Case, CaseAction, CaseActionStatus, CaseActionType, CaseStatus, PathwayAssignment, ProfilingRecord
from .serializers import (
    CaseAssignmentSerializer,
    CaseActionSerializer,
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
    # `case_status` keeps its exact lookup for existing links; `__in` is what
    # the filter chip row uses to select more than one status at a time.
    filterset_fields = {
        "case_status": ["exact", "in"],
        "woreda": ["exact"],
        "case_manager": ["exact"],
    }
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
        previous_action = serializer.instance.next_action
        case = serializer.save()
        new_action = serializer.validated_data.get("next_action")
        if new_action is not None and not new_action.strip():
            case.next_action_owner = None
            case.save(update_fields=["next_action_owner", "updated_at"])
        if new_action is not None and new_action != previous_action and new_action.strip():
            CaseAction.objects.filter(
                case=case,
                action_type=CaseActionType.NEXT_ACTION,
                status=CaseActionStatus.OPEN,
            ).update(status=CaseActionStatus.SUPERSEDED)
            CaseAction.objects.create(
                case=case,
                action_type=CaseActionType.NEXT_ACTION,
                body=new_action,
                created_by=self.request.user,
                assigned_to=case.next_action_owner,
            )
            CaseAction.sync_case_summary(case)
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
    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Caseload counts by status, for the screen's counter row.

        Filtered by `filter_queryset`, so a search narrows the counters with the
        list — but the client omits `case_status` when asking, because a counter
        that only ever counts the status already selected cannot tell you where
        to look next.
        """
        visible = self.filter_queryset(self.get_queryset())
        counters = counters_for(visible, param="case_status__in", field="case_status", choices=CaseStatus)
        return Response(summary_response(visible, counters))

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
class CaseActionViewSet(_CaseChildViewSet):
    """Case action and feedback history."""

    queryset = CaseAction.objects.select_related("case", "case__youth", "created_by", "assigned_to")
    serializer_class = CaseActionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["case", "action_type", "status", "assigned_to"]
    ordering_fields = ["created_at", "due_date"]
    ordering = ["-created_at"]

    @extend_schema(responses=CaseActionSerializer)
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        action = self.get_object()
        action.status = CaseActionStatus.DONE
        action.resolved_at = timezone.now()
        action.full_clean()
        action.save(update_fields=["status", "resolved_at", "updated_at"])
        CaseAction.sync_case_summary(action.case)
        action.case.touch()
        return Response(CaseActionSerializer(action, context=self.get_serializer_context()).data)


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
