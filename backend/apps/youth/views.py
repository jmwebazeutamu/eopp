"""Youth intake and registration API — spec §4.1, §10 Sprint 1."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets

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
        flag = self.request.query_params.get("without_case")
        if flag is not None:
            wants_uncased = flag.lower() in {"1", "true", "yes"}
            queryset = queryset.filter(case__isnull=wants_uncased)
        return queryset

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
