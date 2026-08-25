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
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.users.permissions import CanAccessGrievances, IsOperational

from . import safeguarding, services, timeline
from .models import Grievance, GrievanceStatus
from .scoping import scope_grievances
from .serializers import (
    AcknowledgeSerializer,
    AppealSerializer,
    CloseSerializer,
    DecideSerializer,
    EmptySerializer,
    GrievanceNoteSerializer,
    GrievanceSerializer,
    NoteSerializer,
    PauseSerializer,
    ReferOutSerializer,
)


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
            "status": ["exact", "in"],
            "tier": ["exact"],
            "outcome": ["exact"],
            "complaint_type": ["exact"],
            "raised_by": ["exact"],
            "about_partner": ["exact"],
            "referral_quality_feedback_flag": ["exact"],
            "woreda": ["exact"],
            "subject_group": ["exact"],
            "is_restricted": ["exact"],
            "severity": ["exact"],
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
    ordering_fields = ["date_raised", "due_on", "status", "severity", "tier"]
    # The queue answers one question on load: what needs me today. Ordering by
    # deadline puts the answer at the top; ordering by date of receipt buries a
    # case that is four days late under three that arrived this morning.
    ordering = ["due_on", "-date_raised"]

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
                counters_for(queryset, param="status", field="status", choices=GrievanceStatus),
            )
        )

    @action(detail=False, methods=["get"], url_path="queue-counts")
    def queue_counts(self, request):
        """The first row of the queue — the job list, not a summary.

        Counted over the scoped queryset rather than the table: an aggregate is
        a disclosure too, and "4 late" told to somebody entitled to see one
        woreda has to mean four in that woreda.
        """
        return Response(services.queue_counts(self.get_queryset()))

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        """The case file, oldest first, with the original statement at the top.

        Assembled from the records that already exist — history rows, notes, the
        acknowledgement — rather than from an event table. A second copy of the
        truth could disagree with the first, and this is the one place that must
        not happen.
        """
        grievance = self.get_object()
        if grievance.is_restricted and not safeguarding.may_read_content(request.user, grievance):
            safeguarding.record_access(grievance, request.user, granted=False)
            raise PermissionDenied(str(safeguarding.ACCESS_NOTICE))
        if grievance.is_restricted:
            safeguarding.record_access(grievance, request.user, granted=True)
        return Response({"events": timeline.build(grievance)})

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        """Tell the record that the complainant was told.

        Its own step, and its own clock. Action notes capture what staff did;
        nothing used to capture what the complainant was told, which is the step
        most likely to be skipped and the one auditors check.
        """
        grievance = self.get_object()
        payload = AcknowledgeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            services.acknowledge(grievance, actor=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(self.get_serializer(grievance).data)

    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        """Append to the file. No PATCH and no DELETE, deliberately.

        A note that can be edited afterwards is not evidence of anything. A
        correction is another note saying what was corrected, which also records
        that somebody thought the first one was wrong.
        """
        grievance = self.get_object()
        if grievance.is_restricted and not safeguarding.may_read_content(request.user, grievance):
            raise PermissionDenied(str(safeguarding.ACCESS_NOTICE))

        if request.method == "GET":
            rows = grievance.notes.select_related("author")
            return Response(GrievanceNoteSerializer(rows, many=True).data)

        payload = NoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            note = services.add_note(grievance, author=request.user, **payload.validated_data)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GrievanceNoteSerializer(note).data, status=status.HTTP_201_CREATED)

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

    def _move(self, request, service, serializer_class, **extra):
        """One shape for every workflow action.

        Each is a POST to its own path rather than a PATCH of `status`: a PATCH
        would say what the record should become and skip every gate that says
        whether it may. `TransitionError` carries the sentence explaining which
        edge is missing, and it is passed through rather than replaced with a
        generic failure — those messages are the product here.
        """
        grievance = self.get_object()
        payload = serializer_class(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            result = service(grievance, actor=request.user, **payload.validated_data, **extra)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(self.get_serializer(result).data)

    @action(detail=True, methods=["post"], url_path="start-review")
    def start_review(self, request, pk=None):
        """Pick it up. Only from Acknowledged — working a complaint before
        telling the complainant it arrived is the order this refuses."""
        return self._move(request, services.start_review, EmptySerializer)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        """The only pause, and it stops the clock. Needs a reason and a date to
        chase; a pause with no end is a case nobody comes back to."""
        return self._move(request, services.pause_for_complainant, PauseSerializer)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        """The deadline moves by however long the wait lasted."""
        return self._move(request, services.resume, EmptySerializer)

    @action(detail=True, methods=["post"])
    def decide(self, request, pk=None):
        """Record what was decided — not the same as shutting the file."""
        return self._move(request, services.decide, DecideSerializer)

    @action(detail=True, methods=["post"], url_path="close")
    def close(self, request, pk=None):
        """Shut the file, having told the complainant the answer.

        The gate the rebuild turns on. It was possible to close a case having
        told nobody anything; the transition refuses that now, and so does a
        database constraint.
        """
        return self._move(request, services.record_feedback_and_close, CloseSerializer)

    @action(detail=True, methods=["post"])
    def appeal(self, request, pk=None):
        """Create the child at the next tier, with a fresh clock.

        The response is the **child**, because that is the record the officer
        now works. The parent keeps its own decision and its own history, which
        is the only shape in which "the woreda overturned the kebele" is a
        computable fact.
        """
        return self._move(request, services.appeal, AppealSerializer)

    @action(detail=True, methods=["post"], url_path="refer-out")
    def refer_out(self, request, pk=None):
        return self._move(request, services.refer_out, ReferOutSerializer)

    @action(detail=False, methods=["get"], url_path="overturn-rate")
    def overturn_rate(self, request):
        """How often the tier above disagreed with the tier below.

        Reported with its denominator, like every rate in this platform. A zero
        overturn rate is a finding rather than a success: either first-tier
        decisions are always right, or the second tier is not really reviewing
        them, and only somebody who knows the woreda can say which.
        """
        return Response(services.overturn_rate(self.get_queryset()))
