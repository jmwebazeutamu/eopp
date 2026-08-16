"""Youth intake and registration API — spec §4.1, §10 Sprint 1."""

from django.db.models import Exists, OuterRef, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.cases.models import Case, CaseStatus
from apps.common.summaries import summary_response
from apps.users.permissions import CanAccessCases, IsOperational, ScopedQuerySetMixin

from .models import Youth
from .serializers import YouthIntakeSerializer, YouthSerializer


@extend_schema(tags=["youth"])
class YouthViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """The youth record.

    Scoped as case content (§7): a case manager sees the youth on their own
    caseload, an outreach worker and a supervisor see their woredas, programme
    managers and M&E see everything, and system administrators see none of it.
    """

    queryset = Youth.objects.select_related("registering_worker").all()
    serializer_class = YouthSerializer
    permission_classes = [IsOperational, CanAccessCases]

    scope_kind = "case"
    woreda_field = "woreda"
    # A case manager's caseload is defined by the Case, not the Youth record.
    case_manager_field = "case__case_manager_id"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["woreda", "sex", "psnp_status", "disability_status", "consent_given"]
    search_fields = ["full_name", "phone_number", "national_or_kebele_id", "household_id"]
    ordering_fields = ["full_name", "registration_date", "date_of_birth"]
    ordering = ["full_name"]

    def get_queryset(self):
        """`?without_case=true` lists youth who have no case yet.

        Case is one-to-one with Youth (§3), so the "open a case" picker must not
        offer someone who already has one — the create would fail on the unique
        constraint only after the user had filled in the whole form.

        `super()` is ScopedQuerySetMixin, so §7 scoping is applied first and this
        narrows within it rather than around it.
        """
        queryset = super().get_queryset()
        # Annotated rather than resolved per row: the registry screen shows an
        # "open case" pill on every card, and a property would be one query per
        # youth on a page of forty.
        # Both annotated from the same subquery: the registry shows an "open
        # case" pill on every card, and the pill has to be able to open the case
        # it names, which needs the id rather than just the fact.
        open_case = Case.objects.filter(youth_id=OuterRef("pk"), case_status__in=CaseStatus.open_statuses())
        queryset = queryset.annotate(
            has_open_case=Exists(open_case),
            open_case_id=Subquery(open_case.values("pk")[:1]),
        )
        flag = self.request.query_params.get("without_case")
        if flag is not None:
            wants_uncased = flag.lower() in {"1", "true", "yes"}
            queryset = queryset.filter(case__isnull=wants_uncased)
        return queryset

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Registry counts, split on the one thing the screen filters by.

        `without_case` is the registry's only real question — who is registered
        but not yet being case-managed — so the counters answer it directly
        rather than restating the woreda filter that already has chips.
        """
        visible = self.filter_queryset(self.get_queryset())
        with_case = visible.filter(case__isnull=False).count()
        counters = [
            {"param": "without_case", "value": "false", "label": "With a case", "count": with_case},
            {
                "param": "without_case",
                "value": "true",
                "label": "No case yet",
                "count": visible.filter(case__isnull=True).count(),
            },
        ]
        return Response(summary_response(visible, counters))

    def get_serializer_class(self):
        if self.action == "create":
            return YouthIntakeSerializer
        return super().get_serializer_class()

    def perform_destroy(self, instance):
        """Deleting a youth would orphan the audit trail §9 requires.

        Case exit is modelled on the Case (§4.2 `closed_date` / `exit_reason`),
        and consent withdrawal is an open question in §11. Neither is a delete.
        """
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed(
            "DELETE",
            detail=(
                "Youth records are not deleted. Close the case with an exit reason. "
                "Consent-withdrawal handling is pending sign-off (spec §11)."
            ),
        )
