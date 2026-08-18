"""Referral API — spec §4.6, §6, §10 Sprint 3."""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.cases.models import Case
from apps.common.summaries import counters_for, summary_response
from apps.partners.models import Partner
from apps.users.models import Role
from apps.users.permissions import CanAccessReferrals, IsOperational, ScopedQuerySetMixin

from . import services
from .models import Referral, ReferralStatus, build_referral_stack
from .serializers import (
    CancelReferralSerializer,
    CompleteReferralSerializer,
    ConfirmReferralSerializer,
    DeclineReferralSerializer,
    FailReferralSerializer,
    FailureReasonCodeSerializer,
    InitiateReferralSerializer,
    OnwardReferralSerializer,
    OutcomeTypeSerializer,
    ReferralCategorySerializer,
    ReferralSerializer,
    ReferralStackNodeSerializer,
    ReplacementReferralSerializer,
    describe_transitions,
)
from .taxonomy import FailureReasonCode, OutcomeType, ReferralCategory


def _as_drf_error(exc):
    """Surface a model/service ValidationError as DRF field errors."""
    detail = exc.message_dict if hasattr(exc, "message_dict") else exc.messages
    return ValidationError(detail)


@extend_schema(tags=["referrals"])
class ReferralViewSet(ScopedQuerySetMixin, viewsets.ModelViewSet):
    """The referral record and its state machine.

    Scoped as referral content (§7): a case manager sees their caseload's
    referrals, a supervisor their woreda's, partner staff only their own
    institution's, and system administrators none.
    """

    queryset = Referral.objects.select_related(
        "case",
        "case__youth",
        "referral_category",
        "receiving_partner",
        "outcome_type",
        "failure_reason_code",
        "initiated_by",
    )
    serializer_class = ReferralSerializer
    permission_classes = [IsOperational, CanAccessReferrals]

    scope_kind = "referral"
    woreda_field = "case__woreda"
    case_manager_field = "case__case_manager_id"
    partner_field = "receiving_partner_id"

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    # `case__woreda` backs the shell's woreda scope selector. It is the same
    # column `woreda_field` scopes on, so a narrowed view is always a subset of
    # what §7 already allows — the filter cannot widen anything.
    filterset_fields = ["case", "status", "referral_category", "receiving_partner", "referral_trigger", "case__woreda"]
    search_fields = ["case__youth__full_name", "receiving_partner__partner_name"]
    ordering_fields = ["initiated_date", "status"]
    ordering = ["-initiated_date"]

    # -- creation and deletion --------------------------------------------

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            "POST",
            detail="Use /api/v1/referrals/initiate/ so the referral enters the state machine correctly.",
        )

    def perform_destroy(self, instance):
        raise MethodNotAllowed(
            "DELETE",
            detail=(
                "Referrals are cancelled or failed, never deleted — the §8 partner performance "
                "dashboards and the §6.4 stack both depend on the full history."
            ),
        )

    def _get_case(self, case_id):
        """Resolve a case the caller is actually allowed to act on.

        Looked up through the case viewset's own scoping rather than
        Case.objects, so a case manager cannot initiate a referral on someone
        else's caseload by passing its id.
        """
        from apps.cases.views import CaseViewSet

        scoped = CaseViewSet(request=self.request, kwargs={}, action="retrieve", format_kwarg=None)
        scoped.request = self.request
        return get_object_or_404(scoped.apply_scope(Case.objects.all(), self.request.user), pk=case_id)

    # -- transitions (spec §6.2) ------------------------------------------

    @extend_schema(request=InitiateReferralSerializer, responses=ReferralSerializer)
    @action(detail=False, methods=["post"])
    def initiate(self, request):
        """Create a referral in Pending Confirmation — §6.2, first row."""
        serializer = InitiateReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        case = self._get_case(data["case"])
        partner = get_object_or_404(Partner, pk=data["receiving_partner"])

        try:
            referral = services.initiate_referral(
                case=case,
                referral_category=data["referral_category"],
                receiving_partner=partner,
                initiated_by=request.user,
                receiving_contact_name=data.get("receiving_contact_name", ""),
                notes=data.get("notes", ""),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)

        return Response(self.get_serializer(referral).data, status=status.HTTP_201_CREATED)

    def _transition(self, request, serializer_class, to_status, field_map):
        referral = self.get_object()
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        kwargs = {model_field: data[key] for key, model_field in field_map.items() if key in data}
        if data.get("notes"):
            kwargs["notes"] = data["notes"]

        try:
            referral.transition_to(to_status, actor=request.user, **kwargs)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)

        return Response(self.get_serializer(referral).data)

    @extend_schema(request=ConfirmReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Partner confirms — Pending Confirmation to Active (§6.2).

        This is where the §6.3 parallel cap bites: activation may be refused if
        the case already holds two Active referrals that count toward it.
        """
        return self._transition(
            request,
            ConfirmReferralSerializer,
            ReferralStatus.ACTIVE,
            {"confirmed_by": "confirmed_by", "confirmed_date": "confirmed_date"},
        )

    @extend_schema(request=DeclineReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def decline(self, request, pk=None):
        """Partner declines — Pending Confirmation to Failed (§6.2)."""
        return self._transition(
            request,
            DeclineReferralSerializer,
            ReferralStatus.FAILED,
            {"failure_reason_code": "failure_reason_code"},
        )

    @extend_schema(request=CancelReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Case manager withdraws before confirmation — no replacement prompt (§6.2)."""
        return self._transition(request, CancelReferralSerializer, ReferralStatus.CANCELLED, {})

    @extend_schema(request=CompleteReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Outcome recorded and verified — Active to Completed (§6.2)."""
        return self._transition(
            request,
            CompleteReferralSerializer,
            ReferralStatus.COMPLETED,
            {
                "outcome_type": "outcome_type",
                "outcome_date": "outcome_date",
                "outcome_verification_method": "outcome_verification_method",
            },
        )

    @extend_schema(request=FailReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def fail(self, request, pk=None):
        """Non-attendance, dropout, or other failure — Active to Failed (§6.2)."""
        return self._transition(
            request,
            FailReferralSerializer,
            ReferralStatus.FAILED,
            {"failure_reason_code": "failure_reason_code", "failure_date": "failure_date"},
        )

    @extend_schema(request=OnwardReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def onward(self, request, pk=None):
        """Confirm the Onward prompt on a Completed referral (§6.2)."""
        parent = self.get_object()
        serializer = OnwardReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            referral = services.create_onward_referral(
                parent=parent,
                referral_category=data["referral_category"],
                receiving_partner=get_object_or_404(Partner, pk=data["receiving_partner"]),
                initiated_by=request.user,
                receiving_contact_name=data.get("receiving_contact_name", ""),
                notes=data.get("notes", ""),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)

        return Response(self.get_serializer(referral).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReplacementReferralSerializer, responses=ReferralSerializer)
    @action(detail=True, methods=["post"])
    def replace(self, request, pk=None):
        """Confirm the Replacement prompt on a Failed referral (§6.2)."""
        failed = self.get_object()
        serializer = ReplacementReferralSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            referral = services.create_replacement_referral(
                failed_referral=failed,
                referral_category=data["referral_category"],
                receiving_partner=get_object_or_404(Partner, pk=data["receiving_partner"]),
                initiated_by=request.user,
                receiving_contact_name=data.get("receiving_contact_name", ""),
                notes=data.get("notes", ""),
            )
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)

        return Response(self.get_serializer(referral).data, status=status.HTTP_201_CREATED)

    # -- read-only views ---------------------------------------------------

    @extend_schema(responses={200: None})
    @action(detail=True, methods=["get"])
    def transitions(self, request, pk=None):
        """The legal next statuses for this referral, from the §6.2 table."""
        return Response(describe_transitions(self.get_object()))

    @extend_schema(responses=ReferralStackNodeSerializer(many=True))
    @action(detail=False, methods=["get"], url_path=r"stack/(?P<case_id>[^/.]+)")
    def stack(self, request, case_id=None):
        """The referral stack for a case — spec §6.4.

        Reconstructed by query, never stored, so it is always current.
        """
        case = self._get_case(case_id)
        return Response(ReferralStackNodeSerializer(build_referral_stack(case), many=True).data)

    @extend_schema(responses={200: None})
    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Referral counts by §6.1 status, for the queue's counter row."""
        visible = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(visible, counters_for(visible, param="status", field="status", choices=ReferralStatus))
        )

    @extend_schema(responses={200: None})
    @action(detail=False, methods=["get"], url_path="rules")
    def rules(self, request):
        """The programme rules the case screen has to state out loud (§6.3).

        The parallel cap is a programme decision, not a client constant: the
        case screen shows "2 of 2 parallel referrals in use" and blocks the new
        referral button on it, and if the number is ever revised in settings a
        deployed client must not keep claiming the old one.
        """
        return Response(
            {
                "parallel_limit": settings.MAX_PARALLEL_ACTIVE_REFERRALS,
                "stall_alert_threshold_days": settings.STALL_ALERT_THRESHOLD_DAYS,
                "referral_confirmation_overdue_days": settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS,
                # §11 working default: exempt categories run as a third stream.
                "complementary_service_exempt": settings.COMPLEMENTARY_SERVICE_EXEMPT_FROM_PARALLEL_CAP,
            }
        )

    @action(detail=False, methods=["get"], url_path="prompts")
    def prompts(self, request):
        """Referrals awaiting an onward or replacement decision (§6.2).

        These conditions are the prompts. Sprint 4's Celery job turns them into
        Alert rows; until then this endpoint is how the case screen surfaces
        them, and it keeps the two from drifting apart.
        """
        visible = self.filter_queryset(self.get_queryset())
        return Response(
            {
                "onward": ReferralSerializer(visible.awaiting_onward_prompt(), many=True).data,
                "replacement": ReferralSerializer(visible.awaiting_replacement_prompt(), many=True).data,
            }
        )


class _TaxonomyViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only taxonomy lookups.

    §9 gives the system administrator ownership of these lists through the
    admin, where changes are logged. The API only reads them, so a client can
    populate a dropdown; retired terms are hidden from selection but remain on
    historical referrals.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None
    lookup_field = "code"


@extend_schema(tags=["referrals"])
class ReferralCategoryViewSet(_TaxonomyViewSet):
    queryset = ReferralCategory.objects.active()
    serializer_class = ReferralCategorySerializer


@extend_schema(tags=["referrals"])
class OutcomeTypeViewSet(_TaxonomyViewSet):
    queryset = OutcomeType.objects.active().prefetch_related("applies_to")
    serializer_class = OutcomeTypeSerializer
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        """Optionally narrow to the outcomes valid for one category (§5.3)."""
        queryset = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            from django.db.models import Q

            # An outcome with no category restriction applies everywhere.
            queryset = queryset.filter(Q(applies_to__code=category) | Q(applies_to__isnull=True)).distinct()
        return queryset


@extend_schema(tags=["referrals"])
class FailureReasonCodeViewSet(_TaxonomyViewSet):
    queryset = FailureReasonCode.objects.active()
    serializer_class = FailureReasonCodeSerializer


# Roles that may act on a referral at all — kept for the UI's benefit; the
# authoritative check remains CanAccessReferrals against the §7 matrix.
REFERRAL_ACTING_ROLES = {
    Role.CASE_MANAGER,
    Role.PARTNER_STAFF,
    Role.EMPLOYER_LIAISON,
    Role.ENTERPRISE_OFFICER,
}
