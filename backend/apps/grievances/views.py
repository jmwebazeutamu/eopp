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
from django_filters.rest_framework import CharFilter, DjangoFilterBackend, FilterSet
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanAccessGrievances, IsOperational

from . import safeguarding, services
from .models import Grievance, ResolutionStatus
from .scoping import scope_grievances
from .serializers import CloseSerializer, GrievanceSerializer, ResolveSerializer


class GrievanceFilter(FilterSet):
    """Explicit, because `subject_type` is a generated column.

    django-filter cannot build a filter for a `GeneratedField` and raises at
    request time rather than at startup, so the whole list 500s. Named here
    instead — the same fix `ServiceLinkageFilter` carries, and for the same
    reason.
    """

    subject_type = CharFilter(field_name="subject_type", lookup_expr="exact")

    class Meta:
        model = Grievance
        fields = {
            "resolution_status": ["exact", "in"],
            "complaint_type": ["exact"],
            "raised_by": ["exact"],
            "about_partner": ["exact"],
            "referral_quality_feedback_flag": ["exact"],
            "woreda": ["exact"],
            "subject_group": ["exact"],
            "is_restricted": ["exact"],
        }


def _as_drf_error(exc):
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


class GrievanceViewSet(viewsets.ModelViewSet):
    """§4.10 — one channel, both modules, scoped by caseload *or* by group.

    Not `ScopedQuerySetMixin`. That mixin applies one scope; this needs the
    union of two, because a facilitator is scoped by the groups she runs and a
    supervisor by her woreda, and neither vocabulary can express the other. The
    union lives in `scoping.scope_grievances` and fails closed on both sides.
    """

    queryset = Grievance.objects.select_related(
        "case",
        "case__youth",
        "subject_youth",
        "subject_group",
        "assigned_staff",
        "about_partner",
        "related_referral",
    )
    serializer_class = GrievanceSerializer
    permission_classes = [IsOperational, CanAccessGrievances]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = GrievanceFilter
    # `summary` is searchable and a restricted record's summary is not returned
    # — but a substring search would still *confirm* its contents by which rows
    # come back. Restricted rows are excluded from text search for that reason;
    # they are found by reference, date or woreda.
    search_fields = ["complainant_name", "case__youth__full_name", "subject_group__name"]
    ordering_fields = ["date_raised", "resolution_status"]
    ordering = ["-date_raised"]

    def get_queryset(self):
        """Scope by caseload or by group, then hide what must not be read.

        `visible_to` still removes staff-conduct complaints from everyone but
        their assignee. Safeguarding is handled differently and deliberately:
        the row stays and the serializer redacts it, so the queue can show that
        a disclosure was received without showing what it said.
        """
        queryset = scope_grievances(super().get_queryset(), self.request.user)
        return queryset.visible_to(self.request.user)

    def retrieve(self, request, *args, **kwargs):
        """Opening a restricted record is an event, and it is written down.

        Recorded on the detail route only. A list request touches every row and
        would fill the log with noise that hides the one opening somebody has to
        answer for.
        """
        grievance = self.get_object()
        if grievance.is_restricted:
            safeguarding.record_access(
                grievance,
                request.user,
                granted=safeguarding.may_read_content(request.user, grievance),
            )
        return Response(self.get_serializer(grievance).data)

    def filter_queryset(self, queryset):
        """Keep restricted rows out of free-text search results.

        Not out of the list — out of *search*. A search box that returns a
        restricted row for the word in its summary has published the summary one
        word at a time.
        """
        queryset = super().filter_queryset(queryset)
        if self.request.query_params.get("search"):
            queryset = queryset.exclude(is_restricted=True)
        return queryset

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
        scoped = self.get_queryset()
        queryset = self.filter_queryset(scoped).filter(pk__in=services.overdue(scoped).values("pk"))
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
