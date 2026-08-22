"""WLT API — thin viewsets over `apps.wlt.services`.

Every queryset is scoped through `scope_group_queryset` before it is read. That
is not a nicety: these rows carry twenty women's savings and their loan history,
and a group list that failed open would be a financial disclosure, not a bug
report. The scoping fails closed — a viewset that cannot express the key its
user's scope needs returns nothing.

Actions rather than PATCHes wherever a status moves. `POST /groups/{id}/activate/`
runs the gate, checks the allocation ceiling and stamps the phase;
`PATCH {"status": "ACTIVE"}` would do none of that, which is why status is
read-only on every serializer here.
"""

from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db.models import Exists, OuterRef, Prefetch
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django_filters.rest_framework import CharFilter, FilterSet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.common.summaries import counters_for, summary_response
from apps.locations.models import Location
from apps.users.models import Role
from apps.users.permissions import (
    CanAccessGroups,
    CanDraftGroups,
    CanEnrolBeneficiaries,
    IsOperational,
    ScopedGroupQuerySetMixin,
    scope_group_queryset,
)
from apps.wlt import imports as wlt_imports
from apps.wlt import reporting
from apps.wlt import policy as wlt_policy
from apps.wlt.models import (
    BeneficiaryProfile,
    EntryType,
    ExitReason,
    Group,
    GroupMembership,
    GroupStatus,
    LinkageStatus,
    LoanStatus,
    Meeting,
    MobilisationEvent,
    PhaseEvent,
    RiskFlag,
    ServiceLinkage,
    ServiceLinkageType,
    SyncConflict,
    VerificationStatus,
)
from apps.wlt.services import enrolment as enrolment_service
from apps.wlt.services import formation as formation_service
from apps.wlt.services import history as history_service
from apps.wlt.services import indicators as indicator_service
from apps.wlt.services import journey as journey_service
from apps.wlt.services import ledger as ledger_service
from apps.wlt.services import linkage as linkage_service
from apps.wlt.services import phase as phase_service
from apps.youth import imports as youth_imports

from .serializers import (
    BeneficiaryProfileSerializer,
    BylawVersionSerializer,
    GateResultSerializer,
    GroupMembershipSerializer,
    GroupSerializer,
    LedgerEntrySerializer,
    LinkageEventSerializer,
    LoanSerializer,
    MeetingSerializer,
    MobilisationEventSerializer,
    OfficeHolderSerializer,
    PhaseEventSerializer,
    RiskFlagSerializer,
    ServiceLinkageSerializer,
    ServiceLinkageTypeSerializer,
    SyncConflictSerializer,
    WltRegistrationSerializer,
)


class ServiceLinkageFilter(FilterSet):
    """Explicit, because `subject_type` is a generated column.

    django-filter cannot build a filter for a `GeneratedField` and raises at
    request time rather than at startup, so the whole linkage list 500s. Named
    here instead, which also documents what the funnel filters on.
    """

    subject_type = CharFilter(field_name="subject_type", lookup_expr="exact")

    class Meta:
        model = ServiceLinkage
        fields = ["status", "linkage_type", "subject_group", "subject_cla", "subject_federation"]


def _as_drf_error(exc):
    """Turn a service-layer `ValidationError` into a 400 with its message intact.

    The messages are the product here — "Attendance 74% (need 80%)", "counted
    5,000, expected 5,200" — so they are passed through rather than replaced
    with a generic failure.
    """
    if hasattr(exc, "message_dict"):
        return DRFValidationError(exc.message_dict)
    return DRFValidationError({"detail": exc.messages if hasattr(exc, "messages") else [str(exc)]})


def _is_within(kebele, ancestor_id):
    """Is `kebele` at or under `ancestor_id`?

    Walked rather than expressed through `location_subtree_filter`, which builds
    a lookup for a kebele *FK path on another model* and has no form that anchors
    on a Location row itself. The hierarchy is fixed at four levels, so this is
    three parent reads at worst and only ever runs for a single registration.
    """
    node = kebele
    while node is not None:
        if node.pk == ancestor_id:
            return True
        node = node.parent
    return False


class GroupViewSet(ScopedGroupQuerySetMixin, viewsets.ModelViewSet):
    """SHGs, scoped by facilitator or by geography (handoff §9)."""

    queryset = Group.objects.select_related("kebele", "facilitator").all()
    serializer_class = GroupSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    kebele_field = "kebele"
    facilitator_field = "facilitator_id"
    # Declared, not assumed. The filter backends are configured globally, but a
    # viewset that names no fields silently ignores every query parameter — the
    # status chips would have filtered nothing while looking as though they had.
    filterset_fields = {"status": ["exact"], "current_phase": ["exact"], "kebele": ["exact"]}
    search_fields = ["name", "kebele__name"]
    ordering_fields = ["name", "activated_on", "status"]

    def get_permissions(self):
        """Drafting is a wider permission than running a group.

        `CanDraftGroups` rather than dropping `CanAccessGroups` for create: that
        also removed the `group_scope != NONE` check, so the module boundary
        stopped being enforced on this action at all.
        """
        if self.action == "create":
            return [IsOperational(), CanDraftGroups()]
        return super().get_permissions()

    def perform_create(self, serializer):
        """Draft through `formation.open_draft`, never around it.

        This used to call `serializer.save(status=DRAFT)` directly, which meant
        the endorsement check in `open_draft` — a refused community meeting
        opens no group (A30) — did not run over HTTP at all. The service was
        reachable only from a shell, so the one rule the community itself sets
        was enforced everywhere except the API.

        The kebele is taken from the meeting rather than from the payload. A
        group drafted from a meeting held in one kebele belongs to that kebele;
        accepting a typed one lets the two disagree, and then the group scopes
        to one place and reports in another.
        """
        if self.request.user.role not in {Role.WLT_FACILITATOR, Role.WLT_WOREDA_OFFICER, Role.SYSTEM_ADMIN}:
            raise PermissionDenied(_("Your role cannot draft a savings group."))
        event = serializer.validated_data["mobilisation_event"]
        try:
            group = formation_service.open_draft(
                name=serializer.validated_data["name"],
                kebele=event.kebele,
                facilitator=serializer.validated_data.get("facilitator") or self.request.user,
                mobilisation_event=event,
                created_by=self.request.user,
                on_date=serializer.validated_data.get("drafted_on"),
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        # The viewset's response is built from `serializer.instance`, so the row
        # the service created has to be handed back rather than left behind.
        serializer.instance = group

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """The counter row that is also the filter, per the platform convention."""
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="status", field="status", choices=GroupStatus),
            )
        )

    @action(detail=True, methods=["get"])
    def readiness(self, request, pk=None):
        """The readiness card: every condition, actual next to threshold.

        Computed on request rather than read from a nightly table, so it changes
        the moment a meeting closes. That immediate feedback is most of what
        makes the card worth having.
        """
        group = self.get_object()

        # `?gate_set=` shows an earlier phase gate against today's data. A group
        # in Phase 2 asked for `p1_to_p2` gets the conditions it was promoted
        # on, measured now — savings compliance and attendance are continuous,
        # so a group can fall back below a gate it has already passed, and
        # nothing on any screen used to show that. Anything not on the offered
        # list is ignored rather than trusted: the parameter arrives from a URL.
        offered = phase_service.available_gate_sets(group)
        asked = request.query_params.get("gate_set")
        gate_set = asked if any(row["name"] == asked for row in offered) else None

        result = phase_service.readiness(group, gate_set=gate_set)
        figures = indicator_service.compute(group)
        return Response(
            {
                "group": GroupSerializer(group).data,
                "gate": GateResultSerializer(result).data if result else None,
                "gate_sets": offered,
                "gate_set": gate_set or next((row["name"] for row in offered if row["is_next"]), None),
                "indicators": figures.as_snapshot(),
                "risk_flags": RiskFlagSerializer(RiskFlag.objects.open().for_group(group), many=True).data,
                # Stamped so a client that cached this offline can say how old
                # it is. A stale card that is honest about its age beats a fresh
                # one that is wrong.
                "computed_at": figures.as_of,
            }
        )

    @action(detail=True, methods=["get"])
    def validation(self, request, pk=None):
        """Blocks and warnings on the current roster, before constituting."""
        group = self.get_object()
        findings = formation_service.validate_roster(group)
        return Response({"findings": [finding.as_dict() for finding in findings]})

    @action(detail=True, methods=["post"])
    def constitute(self, request, pk=None):
        group = self.get_object()
        try:
            formation_service.constitute(group, overrides=request.data.get("overrides") or {}, actor=request.user)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GroupSerializer(group).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        group = self.get_object()
        try:
            formation_service.activate(
                group,
                allocation_override_reason=request.data.get("allocation_override_reason", ""),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GroupSerializer(group).data)

    @action(detail=True, methods=["get", "post"], url_path="members")
    def members(self, request, pk=None):
        group = self.get_object()
        if request.method == "GET":
            # Current members first, then the women who have left, each in the
            # order she joined. The roster is a dated range, so the exited rows
            # are part of it — an indicator computed against March needs the
            # woman who left in April.
            # `person__wlt_profile` too: the roster links to each woman's
            # record, and without it the serializer would fetch her profile one
            # row at a time.
            roster = (
                group.memberships.select_related("person", "person__wlt_profile")
                .order_by("exited_on", "joined_on", "person__full_name")
            )
            return Response(GroupMembershipSerializer(roster, many=True).data)
        from apps.youth.models import Youth

        person_ids = request.data.get("people") or [request.data.get("person")]
        people = list(Youth.objects.filter(pk__in=person_ids))
        if len(people) != len(set(person_ids)):
            raise DRFValidationError({"people": [_("One or more people are unknown.")]})
        memberships = []
        try:
            for person in people:
                memberships.append(formation_service.add_member(group, person, actor=request.user))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        payload = GroupMembershipSerializer(memberships, many=True).data
        return Response(payload if "people" in request.data else payload[0], status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"members/(?P<membership_id>[^/.]+)/exit")
    def member_exit(self, request, pk=None, membership_id=None):
        """Close one membership, with a reason.

        A reason is mandatory here as well as in the check constraint, because
        the constraint can only say "not blank" — it cannot tell a facilitator
        that "moved away" and "expelled" are different programme outcomes. The
        outstanding-loan block (A11) lives in the service and in a trigger; this
        route only surfaces the sentence it raises.
        """
        group = self.get_object()
        membership = group.memberships.select_related("person").filter(pk=membership_id).first()
        if membership is None:
            raise DRFValidationError({"detail": [_("This membership is not on this group's roster.")]})
        if membership.exited_on is not None:
            raise DRFValidationError(
                {"detail": [_("%(name)s has already left this group.") % {"name": membership.person.full_name}]}
            )

        reason = request.data.get("reason") or ""
        if reason not in ExitReason.values:
            raise DRFValidationError({"reason": [_("Choose why she is leaving the group.")]})

        try:
            formation_service.exit_member(membership, reason=reason, note=request.data.get("note", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(GroupMembershipSerializer(membership).data)

    @action(detail=True, methods=["get", "post"], url_path="officers")
    def officers(self, request, pk=None):
        """Who holds office, and electing somebody to it.

        A term is a dated range, like a membership: `elect_officer` closes the
        sitting officer's term rather than editing the row, because "who was
        treasurer on the date of that disbursement" is a question that gets
        asked (A8). So the GET returns closed terms too — the current ones are
        the rows with no `to_date`, and the screen filters for them.

        The GET is new. Officers could be elected and never read back, so no
        screen could show who the chair was; the roster listed twenty
        indistinguishable names.
        """
        group = self.get_object()
        from apps.youth.models import Youth

        if request.method == "GET":
            holders = group.office_holders.select_related("person").order_by("role", "-from_date")
            return Response(OfficeHolderSerializer(holders, many=True).data)

        person = Youth.objects.filter(pk=request.data.get("person")).first()
        try:
            holder = formation_service.elect_officer(group, person=person, role=request.data.get("role"))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(OfficeHolderSerializer(holder).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"], url_path="bylaws")
    def bylaws(self, request, pk=None):
        group = self.get_object()
        if request.method == "GET":
            return Response(BylawVersionSerializer(group.bylaw_versions.all(), many=True).data)

        serializer = BylawVersionSerializer(data={**request.data, "group": str(group.pk)})
        serializer.is_valid(raise_exception=True)
        fields = {
            key: value
            for key, value in serializer.validated_data.items()
            if key not in {"group", "version_no", "effective_to"}
        }
        try:
            bylaw = formation_service.record_bylaws(group, recorded_by=request.user, **fields)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(BylawVersionSerializer(bylaw).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="ledger")
    def ledger(self, request, pk=None):
        group = self.get_object()
        entries = group.ledger_entries.select_related("person").order_by("-created_at")[:200]
        return Response(
            {
                "entries": LedgerEntrySerializer(entries, many=True).data,
                "cash_balance_etb": ledger_service.cash_balance(group),
                "charge_label": ledger_service.charge_label(group),
            }
        )

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """The group's audit trail — "why did three members leave on 20 August".

        Assembled from the records that already exist rather than from an event
        table: phase decisions, linkage status changes, dated memberships and
        office terms, and closed meetings. Writing those a second time into a
        log would create a second version of the truth that could disagree with
        the first, and the audit trail is the one place that must not happen.
        """
        group = self.get_object()
        types = [value for value in request.query_params.getlist("type") if value]
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", 40))))
            offset = max(0, int(request.query_params.get("offset", 0)))
        except ValueError:
            # Paging values arrive from a URL. A bad one is the first page, not
            # a 500 on a screen somebody opened from a link.
            limit, offset = 40, 0
        return Response(history_service.build(group, types=types or None, limit=limit, offset=offset))

    @action(detail=True, methods=["get"], url_path="loans")
    def loans(self, request, pk=None):
        group = self.get_object()
        return Response(LoanSerializer(group.loans.select_related("person"), many=True).data)


class MeetingViewSet(ScopedGroupQuerySetMixin, viewsets.ModelViewSet):
    """Meeting capture. Everything here has to work with no signal."""

    queryset = Meeting.objects.select_related("group").all()
    serializer_class = MeetingSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    kebele_field = "group__kebele"
    facilitator_field = "group__facilitator_id"
    filterset_fields = {"group": ["exact"], "status": ["exact"]}
    ordering_fields = ["meeting_no", "held_on"]
    # Two meetings can be held on one date — a catch-up sits beside the regular
    # one — and a date-only sort then puts 31 above 32 inside a descending list.
    # `meeting_no` is the tiebreak everywhere meetings are listed or exported,
    # so it is the viewset default rather than something each caller remembers.
    ordering = ["-held_on", "-meeting_no"]

    def create(self, request, *args, **kwargs):
        group = Group.objects.filter(pk=request.data.get("group")).first()
        if group is None or not scope_group_queryset(Group.objects.filter(pk=group.pk), request.user).exists():
            raise DRFValidationError({"group": [_("Unknown group.")]})
        meeting = ledger_service.open_meeting(
            group,
            held_on=request.data.get("held_on") or None,
            recorded_by=request.user,
            device_id=request.data.get("device_id", ""),
            meeting_id=request.data.get("id"),
        )
        return Response(MeetingSerializer(meeting).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def attendance(self, request, pk=None):
        from apps.youth.models import Youth

        meeting = self.get_object()
        rows = []
        for row in request.data.get("rows", []):
            person = Youth.objects.filter(pk=row.get("person")).first()
            if person is not None:
                rows.append((person, row.get("status")))
        try:
            ledger_service.record_attendance(meeting, rows)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response({"recorded": len(rows)})

    @action(detail=True, methods=["post"], url_path="savings")
    def savings(self, request, pk=None):
        from apps.youth.models import Youth

        meeting = self.get_object()
        person = Youth.objects.filter(pk=request.data.get("person")).first()
        try:
            entry = ledger_service.record_savings(
                meeting, person=person, amount_etb=request.data.get("amount_etb"), actor=request.user
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(LedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="expected-cash")
    def expected_cash(self, request, pk=None):
        """What should be in the box, so a facilitator can count against it."""
        meeting = self.get_object()
        return Response({"expected_cash_etb": ledger_service.expected_cash(meeting)})

    @action(detail=True, methods=["post"], url_path="loans")
    def disburse(self, request, pk=None):
        """Issue a loan from the group's own fund, at this meeting.

        On the meeting rather than on the group because that is where the money
        is: the cash leaves the box in the room, and `expected_cash` counts the
        disbursement, so a loan given out and a till that still balances are the
        same act. Disbursing outside a meeting would put the box out by the
        principal with nothing to explain it.

        Every refusal comes from the service — before the tenth savings meeting,
        past the concurrent-loan cap, into the reserve buffer, or more cash than
        the box holds — and its message is passed through, because "this group
        has held 6 savings meetings, lending starts after 10" is the answer.
        """
        from apps.youth.models import Youth

        meeting = self.get_object()
        person = Youth.objects.filter(pk=request.data.get("person")).first()
        if person is None:
            raise DRFValidationError({"person": [_("Choose the borrower.")]})

        try:
            loan = ledger_service.disburse_loan(
                meeting.group,
                person=person,
                principal_etb=request.data.get("principal_etb"),
                purpose=request.data.get("purpose"),
                purpose_note=request.data.get("purpose_note", ""),
                due_on=request.data.get("due_on"),
                meeting=meeting,
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(LoanSerializer(loan).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"loans/(?P<loan_id>[^/.]+)/repay")
    def repay(self, request, pk=None, loan_id=None):
        """Money back, split into principal and charge.

        Split because PAR30 is a statement about principal alone, and a
        repayment recorded as one number cannot be split afterwards.

        The loan is looked up *through* the meeting's group, so it inherits the
        group's scoping rather than trusting an id from the URL.
        """
        from ..models import Loan

        meeting = self.get_object()
        loan = Loan.objects.filter(pk=loan_id, group=meeting.group).first()
        if loan is None:
            raise Http404

        try:
            ledger_service.record_repayment(
                loan,
                principal_etb=request.data.get("principal_etb") or 0,
                charge_etb=request.data.get("charge_etb") or 0,
                meeting=meeting,
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        loan.refresh_from_db()
        return Response(LoanSerializer(loan).data)

    @action(detail=True, methods=["get"], url_path="register")
    def register(self, request, pk=None):
        """The paper register, as one read: who is on the roster, who turned up,
        and who has already paid.

        One call rather than four because this is the screen a facilitator opens
        in a village on a bad connection, and because the alternative was worse
        than slow: `record_savings` appends, and there is no update path, so a
        screen that could not see what was already posted would double a
        woman's contribution on a retry. Correcting that needs a reversal with a
        reason. Showing what is recorded is what stops it.

        The roster is the one in force **on the meeting date**, not today's:
        membership is a dated range, and a woman who left last week was in the
        group when this meeting was held.
        """
        meeting = self.get_object()
        group = meeting.group

        roster = (
            group.memberships.filter(joined_on__lte=meeting.held_on)
            .exclude(exited_on__lt=meeting.held_on)
            .select_related("person")
            .order_by("person__full_name")
        )
        attendance = {row.person_id: row.status for row in meeting.attendance.all()}
        saved = {}
        for entry in meeting.ledger_entries.filter(entry_type=EntryType.SAVINGS, person__isnull=False):
            saved[entry.person_id] = saved.get(entry.person_id, Decimal("0")) + entry.amount_etb

        bylaw = group.bylaw_on(meeting.held_on) or group.current_bylaw

        return Response(
            {
                "meeting": MeetingSerializer(meeting).data,
                "group_name": group.name,
                "contribution_etb": str(bylaw.contribution_etb) if bylaw else None,
                "expected_cash_etb": ledger_service.expected_cash(meeting),
                # What the box holds right now, which is the ceiling on what can
                # be lent out at this meeting. Shown so the refusal is not the
                # first time a facilitator learns the money is not there.
                "cash_balance_etb": ledger_service.cash_balance(group),
                # Loans still owing, so a repayment can be recorded against one
                # without a second call. Settled loans are not offered: there is
                # nothing left to pay.
                "loans": LoanSerializer(
                    group.loans.filter(status=LoanStatus.DISBURSED).select_related("person").order_by("due_on"),
                    many=True,
                ).data,
                "members": [
                    {
                        "person": str(membership.person_id),
                        "full_name": membership.person.full_name,
                        "attendance": attendance.get(membership.person_id),
                        # None means nothing posted yet, which is different from
                        # a recorded zero — a woman who saved nothing this week
                        # is a compliance finding, not a blank row.
                        "saved_etb": str(saved[membership.person_id]) if membership.person_id in saved else None,
                    }
                    for membership in roster
                ],
            }
        )

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        meeting = self.get_object()
        try:
            ledger_service.close_meeting(
                meeting,
                counted_cash_etb=request.data.get("counted_cash_etb"),
                actor=request.user,
                social_time_minutes=request.data.get("social_time_minutes"),
                social_topic=request.data.get("social_topic", ""),
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(
            {
                "meeting": MeetingSerializer(meeting).data,
                "warning": ledger_service.social_time_warning(meeting),
            }
        )


class ServiceLinkageViewSet(ScopedGroupQuerySetMixin, viewsets.ModelViewSet):
    """The gated linkage lifecycle (README §6.5).

    Scoped on the group subject. A CLA- or federation-level linkage has no
    single kebele, so it resolves through the subject's own geography; a user
    whose scope cannot reach it sees nothing, which is the fail-closed default.
    """

    queryset = ServiceLinkage.objects.select_related(
        "linkage_type", "provider", "subject_group", "predecessor", "predecessor__linkage_type"
    ).all()
    serializer_class = ServiceLinkageSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    kebele_field = "subject_group__kebele"
    facilitator_field = "subject_group__facilitator_id"
    # `subject_group` matters most: the readiness card asks for one group's
    # linkages, and without the declaration it was handed every linkage the
    # user could see — another group's bank account on this group's card.
    filterset_class = ServiceLinkageFilter
    search_fields = ["subject_group__name", "provider__partner_name", "linkage_type__label"]
    ordering_fields = ["opened_on", "status"]

    def get_permissions(self):
        # Officers are intentionally read-only for group/ledger records, but
        # approval decisions are their named administrative responsibility.
        # Domain services still validate the configured approval role and
        # prohibit self/repeat approval.
        if self.action in {"approve", "return_for_revision", "reject", "write_off_obligation"}:
            return [IsOperational()]
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(queryset, param="status", field="status", choices=LinkageStatus),
            )
        )

    @action(detail=False, methods=["get"], url_path="types")
    def types(self, request):
        return Response(ServiceLinkageTypeSerializer(ServiceLinkageType.objects.active(), many=True).data)

    @action(detail=False, methods=["get"], url_path="eligible-providers")
    def eligible_providers(self, request):
        linkage_type = ServiceLinkageType.objects.filter(pk=request.query_params.get("linkage_type")).first()
        group = scope_group_queryset(
            Group.objects.filter(pk=request.query_params.get("subject_group")), request.user
        ).first()
        if linkage_type is None or group is None:
            return Response([])
        providers = linkage_service.proposable_providers(linkage_type, group)
        return Response(
            [
                {"id": str(provider.pk), "name": provider.partner_name, "type": provider.partner_type}
                for provider in providers
            ]
        )

    def create(self, request, *args, **kwargs):
        subject, linkage_type, provider = self._resolve_proposal(request)
        try:
            linkage = linkage_service.propose(
                linkage_type=linkage_type,
                subject=subject,
                provider=provider,
                actor=request.user,
                value_etb=request.data.get("value_etb"),
                terms=request.data.get("terms"),
                predecessor=self._resolve_predecessor(request, subject),
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data, status=status.HTTP_201_CREATED)

    def _resolve_predecessor(self, request, subject):
        predecessor_id = request.data.get("predecessor")
        if not predecessor_id:
            return None
        predecessor = self.get_queryset().filter(pk=predecessor_id).first()
        if predecessor is None:
            raise DRFValidationError({"predecessor": [_('Unknown or inaccessible earlier linkage.')]})
        return predecessor

    def _resolve_proposal(self, request):
        from apps.partners.models import Partner
        from apps.wlt.models import CLA, Federation

        linkage_type = ServiceLinkageType.objects.filter(pk=request.data.get("linkage_type")).first()
        if linkage_type is None:
            raise DRFValidationError({"linkage_type": [_("Unknown linkage type.")]})

        subject = None
        if request.data.get("subject_group"):
            subject = scope_group_queryset(Group.objects.filter(pk=request.data["subject_group"]), request.user).first()
        elif request.data.get("subject_cla"):
            subject = CLA.objects.filter(pk=request.data["subject_cla"]).first()
        elif request.data.get("subject_federation"):
            subject = Federation.objects.filter(pk=request.data["subject_federation"]).first()
        if subject is None:
            raise DRFValidationError({"subject": [_("Name one subject you can see.")]})

        provider = Partner.objects.filter(pk=request.data.get("provider")).first()
        return subject, linkage_type, provider

    @action(detail=True, methods=["get"], url_path="providers")
    def providers(self, request, pk=None):
        """Providers that actually operate where this subject is.

        A bank present in Amhara is often absent in Afar, and a linkage proposed
        to one with no branch in the woreda wastes a facilitator's month.
        """
        linkage = self.get_object()
        providers = linkage_service.proposable_providers(linkage.linkage_type, linkage.subject)
        return Response([{"id": str(p.pk), "name": p.partner_name, "type": p.partner_type} for p in providers])

    @action(detail=True, methods=["post"], url_path="screen")
    def rescreen(self, request, pk=None):
        linkage = self.get_object()
        linkage_service.screen(linkage, actor=request.user)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.submit_for_approval(
                linkage, actor=request.user, override_reason=request.data.get("override_reason", "")
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"], url_path="resolution")
    def resolution(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.record_resolution(
                linkage,
                reference=request.data.get("reference", ""),
                meeting_id=request.data.get("meeting_id"),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.approve(linkage, actor=request.user, note=request.data.get("note", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"], url_path="return")
    def return_for_revision(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.return_for_revision(linkage, actor=request.user, reason=request.data.get("reason", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.reject(linkage, actor=request.user, reason=request.data.get("reason", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.activate(linkage, actor=request.user, terms=request.data.get("terms"))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["get", "post"], url_path="obligations")
    def obligation(self, request, pk=None):
        linkage = self.get_object()
        if request.method == "GET":
            rows = linkage_service.obligation_register(linkage)
            for row in rows:
                row["occurred_at"] = row["occurred_at"].isoformat()
            return Response(rows)
        try:
            linkage_service.record_obligation(
                linkage,
                kind=request.data.get("kind", ""),
                reference=request.data.get("reference", ""),
                missed=request.data.get("missed", False),
                outstanding=request.data.get("outstanding", True),
                note=request.data.get("note", ""),
                actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"], url_path="obligations/settle")
    def settle_obligation(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.resolve_obligation(
                linkage, reference=request.data.get("reference", ""), resolution="SETTLED",
                note=request.data.get("note", ""), actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"], url_path="obligations/write-off")
    def write_off_obligation(self, request, pk=None):
        if request.user.role not in {
            Role.WLT_WOREDA_OFFICER, Role.WLT_REGION_OFFICER, Role.WLT_FEDERAL_OFFICER, Role.SYSTEM_ADMIN
        }:
            raise DRFValidationError({"detail": _("An approver must authorize a write-off.")})
        linkage = self.get_object()
        try:
            linkage_service.resolve_obligation(
                linkage, reference=request.data.get("reference", ""), resolution="WRITE_OFF",
                note=request.data.get("note", ""), actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"], url_path="obligations/transfer")
    def transfer_obligation(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.resolve_obligation(
                linkage, reference=request.data.get("reference", ""), resolution="TRANSFER",
                transfer_reference=request.data.get("transfer_reference", ""),
                note=request.data.get("note", ""), actor=request.user,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def cure(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.cure(linkage, actor=request.user, note=request.data.get("note", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        linkage = self.get_object()
        try:
            linkage_service.close(linkage, actor=request.user, reason=request.data.get("reason", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ServiceLinkageSerializer(linkage).data)

    @action(detail=True, methods=["get"], url_path="events")
    def events(self, request, pk=None):
        linkage = self.get_object()
        return Response(LinkageEventSerializer(linkage.events.select_related("actor"), many=True).data)


class PhaseEventViewSet(
    ScopedGroupQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Phase submissions and decisions. Immutable once decided."""

    queryset = PhaseEvent.objects.select_related("group", "submitted_by", "decided_by").all()
    serializer_class = PhaseEventSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    kebele_field = "group__kebele"
    facilitator_field = "group__facilitator_id"
    filterset_fields = {"group": ["exact"], "to_phase": ["exact"], "direction": ["exact"]}

    def get_permissions(self):
        # Phase decisions belong to WLT officers (and System Admin), whose
        # group records are intentionally read-only. The phase service still
        # enforces approval level and no-self-decision.
        if self.action in {"approve", "reject"}:
            return [IsOperational()]
        return super().get_permissions()

    @action(detail=False, methods=["get"])
    def pending(self, request):
        """What is waiting on this user, excluding anything they submitted."""
        return Response(PhaseEventSerializer(phase_service.pending_for(request.user), many=True).data)

    @action(detail=False, methods=["post"])
    def submit(self, request):
        group = scope_group_queryset(Group.objects.filter(pk=request.data.get("group")), request.user).first()
        if group is None:
            raise DRFValidationError({"group": [_("Unknown group.")]})
        try:
            event = phase_service.submit(
                group, actor=request.user, override_reason=request.data.get("override_reason", "")
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PhaseEventSerializer(event).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        event = self.get_object()
        try:
            phase_service.approve(event, actor=request.user)
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PhaseEventSerializer(event).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        event = self.get_object()
        try:
            phase_service.reject(event, actor=request.user, reason=request.data.get("reason", ""))
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(PhaseEventSerializer(event).data)


class BeneficiaryProfileViewSet(viewsets.ModelViewSet):
    """The WLT registry extension, and the exception-route verification queue."""

    queryset = BeneficiaryProfile.objects.select_related("person", "psnp_kebele").all()
    serializer_class = BeneficiaryProfileSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    # Enrolment is not group_write — see `CanEnrolBeneficiaries` for why the
    # woreda officer has to be able to do these two and nothing else here.
    ENROLMENT_ACTIONS = {"register", "import_extract", "verify"}
    filterset_fields = {
        "verification_status": ["exact"],
        "enrolment_route": ["exact"],
        "psnp_kebele": ["exact"],
    }
    search_fields = ["person__full_name", "psnp_client_id"]

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        eligible = self.request.query_params.get("is_programme_eligible")
        if eligible == "true":
            queryset = queryset.programme_eligible()
        elif eligible == "false":
            eligible_ids = queryset.programme_eligible().values("pk")
            queryset = queryset.exclude(pk__in=eligible_ids)

        # `?in_group=false` is the women waiting to be seated, which is the
        # question the register is actually asked. Reuses `unassigned()` rather
        # than restating it: that queryset had an inverted-join bug that
        # excluded every woman in the database, and a second copy here would be
        # a second place for it to come back.
        in_group = self.request.query_params.get("in_group")
        if in_group == "false":
            queryset = queryset.unassigned()
        elif in_group == "true":
            queryset = queryset.exclude(pk__in=queryset.unassigned().values("pk"))

        # `?group=<id>` — the women in one named group. `Exists` rather than a
        # join for the reason `unassigned()` documents: a membership join
        # multiplies the row, and a woman who left and rejoined would appear
        # twice on the register.
        #
        # Her *open* membership only. A former member is not in the group now,
        # and her closed row stays on the roster for the meeting denominators
        # rather than for this list.
        group_id = self.request.query_params.get("group")
        if group_id:
            # Validated here rather than caught later: a malformed UUID raises
            # when the queryset is *evaluated*, which is inside pagination, so a
            # try/except around `.filter()` would not see it and the register —
            # reachable from a pasted URL — would 500.
            try:
                group_uuid = UUID(str(group_id))
            except ValueError:
                return queryset.none()

            queryset = queryset.filter(
                Exists(
                    GroupMembership.objects.filter(
                        person=OuterRef("person_id"), group_id=group_uuid, exited_on__isnull=True
                    )
                )
            )

        return queryset

    def get_permissions(self):
        if self.action in self.ENROLMENT_ACTIONS:
            return [IsOperational(), CanEnrolBeneficiaries()]
        return super().get_permissions()

    def get_queryset(self):
        """Scoped by the woman's PSNP kebele, through the same subtree walk groups use."""
        from apps.users.models import GroupScope
        from apps.users.permissions import location_subtree_filter

        # Each woman's *open* membership, prefetched: the register's group
        # column and `is_assignable` both ask the same question, and answering
        # it per row cost one query per woman. `to_attr` because only the open
        # range is wanted — pulling every closed row to answer a yes/no would
        # trade one problem for another.
        queryset = super().get_queryset().prefetch_related(
            Prefetch(
                "person__wlt_memberships",
                queryset=GroupMembership.objects.filter(exited_on__isnull=True).select_related("group"),
                to_attr="open_memberships",
            )
        )
        user = self.request.user
        scope = user.group_scope()
        if scope == GroupScope.ALL:
            return queryset
        if scope == GroupScope.NONE:
            return queryset.none()
        if scope == GroupScope.OWN_GROUPS:
            # A facilitator sees the pool she can actually form groups from: the
            # kebeles of the groups she runs.
            kebele_ids = Group.objects.filter(facilitator=user).values_list("kebele_id", flat=True)
            return queryset.filter(psnp_kebele_id__in=list(kebele_ids))
        if not user.wlt_scope_location_id:
            return queryset.none()
        lookup = location_subtree_filter("psnp_kebele", user.wlt_scope_location)
        return queryset.none() if lookup is None else queryset.filter(**lookup)

    @action(detail=False, methods=["get"], url_path="candidates")
    def candidates(self, request):
        """Eligible, verified, unassigned women in a kebele.

        The three filters are the queryset methods `formation.candidate_pool`
        uses, not a restatement of them. An earlier hand-written version tested
        `wlt_memberships__isnull=True` — never in *any* group — which quietly
        made a woman who had left one permanently unaddable, and omitted the
        eligibility filter, so the pool offered women `add_member` then refused.
        """
        kebele_id = request.query_params.get("kebele")
        pool = self.get_queryset().programme_eligible().verified().unassigned()

        here = pool.filter(psnp_kebele_id=kebele_id) if kebele_id else pool
        rows = BeneficiaryProfileSerializer(here.order_by("person__full_name"), many=True).data

        # An empty pool has to say *why*. A group's candidates are the women in
        # its own kebele — an SHG meets weekly in person and saves into one box
        # — so the usual reason for an empty list is that every waiting woman
        # lives somewhere else. Returning the bare list left the screen showing
        # nothing at all, which reads as a fault rather than as geography, and
        # it was reported as one.
        #
        # Counted rather than listed: naming women in kebeles this group cannot
        # recruit from would invite exactly the cross-kebele add the pool exists
        # to prevent.
        elsewhere = pool.exclude(psnp_kebele_id=kebele_id).count() if kebele_id else 0
        kebele = Location.objects.filter(pk=kebele_id).first() if kebele_id else None

        return Response(
            {
                "results": rows,
                "kebele": {"code": kebele.code, "name": kebele.name} if kebele else None,
                "waiting_elsewhere": elsewhere,
                "registered_here": self.get_queryset().filter(psnp_kebele_id=kebele_id).count() if kebele_id else 0,
                "already_grouped_here": self.get_queryset().filter(
                    psnp_kebele_id=kebele_id,
                    person__wlt_memberships__exited_on__isnull=True,
                ).distinct().count() if kebele_id else 0,
            }
        )

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """The counter row that is also the filter, per the platform convention."""
        queryset = self.filter_queryset(self.get_queryset())
        return Response(
            summary_response(
                queryset,
                counters_for(
                    queryset,
                    param="verification_status",
                    field="verification_status",
                    choices=VerificationStatus,
                ),
            )
        )

    @action(detail=False, methods=["post"])
    def register(self, request):
        """The exception route, end to end — handoff decision D5, rule 3.

        Before this, `add_by_facilitator` needed a `Youth` row and no WLT role
        could create one: `YouthViewSet` is gated on `CanAccessCases` and every
        WLT role has `case_scope: NONE`. So the route the handoff calls the
        legitimate path for a woman the extract missed stopped at its first step,
        and the import was the only real way in.

        Creating the person here does not breach the module boundary — she still
        gets 403 on every case route, which `test_boundary` pins. Registering
        somebody is not reading their case file.
        """
        serializer = WltRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        kebele = serializer.validated_data["kebele"]
        self._check_registration_scope(request.user, kebele)

        person_fields, profile_fields, note = serializer.split()
        try:
            profile = enrolment_service.register_by_facilitator(
                kebele=kebele,
                actor=request.user,
                note=note,
                profile_fields=profile_fields,
                **person_fields,
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(BeneficiaryProfileSerializer(profile).data, status=status.HTTP_201_CREATED)

    def _check_registration_scope(self, user, kebele):
        """A facilitator registers in the kebeles she works, not the region's.

        Read from the same places `get_queryset` scopes by, so a woman cannot be
        registered into a kebele whose register the same account could not then
        open. Fails closed: a scope this viewset cannot express registers nowhere.
        """
        from apps.users.models import GroupScope

        scope = user.group_scope()
        if scope == GroupScope.ALL:
            return
        if scope == GroupScope.OWN_GROUPS:
            kebele_ids = set(Group.objects.filter(facilitator=user).values_list("kebele_id", flat=True))
            # A facilitator opening her first group has no kebele yet, so her
            # own assignment stands in — otherwise the module cannot be started.
            if user.wlt_scope_location_id:
                kebele_ids.add(user.wlt_scope_location_id)
            if kebele.pk in kebele_ids:
                return
        elif user.wlt_scope_location_id and _is_within(kebele, user.wlt_scope_location_id):
            return
        raise DRFValidationError({"kebele": [_("You cannot register a woman in this kebele.")]})

    @action(detail=False, methods=["get"], url_path="import-template")
    def import_template(self, request):
        response = HttpResponse(wlt_imports.build_extract_template(), content_type=youth_imports.XLSX_CONTENT_TYPE)
        response["Content-Disposition"] = 'attachment; filename="psnp-els-extract-template.xlsx"'
        return response

    @extend_schema(
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "format": "binary"},
                    "kebele": {"type": "string", "format": "uuid"},
                    "batch": {"type": "string"},
                },
            }
        },
        responses={200: OpenApiTypes.OBJECT},
        description=(
            "Import a PSNP ELS extract for one kebele. Unlike the youth-side register this is not all-or-nothing: "
            "a row that needs a woreda officer is queued and named, and the rest of the file still lands."
        ),
    )
    @action(detail=False, methods=["post"], url_path="import", parser_classes=[MultiPartParser, FormParser])
    def import_extract(self, request):
        upload = request.FILES.get("file")
        if upload is None:
            raise DRFValidationError({"file": [_("Attach the extract as 'file'.")]})
        if upload.size > youth_imports.MAX_FILE_BYTES:
            raise DRFValidationError(
                {
                    "file": [
                        _("The file is larger than %(limit)s MB.")
                        % {"limit": youth_imports.MAX_FILE_BYTES // (1024 * 1024)}
                    ]
                }
            )

        kebele = Location.objects.filter(code=request.data.get("kebele")).first()
        if kebele is None:
            raise DRFValidationError({"kebele": [_("Name the kebele this extract covers.")]})
        # An extract is a bulk write into one place, so it goes through the same
        # check a single registration does rather than a looser one.
        self._check_registration_scope(request.user, kebele)

        try:
            parsed = wlt_imports.read_extract(upload)
        except youth_imports.WorkbookError as exc:
            raise DRFValidationError({"file": [str(exc)]})

        if not parsed:
            raise DRFValidationError({"file": [_("The sheet has a header row but no women.")]})

        rows, unreadable = wlt_imports.to_rows(parsed)
        batch = (request.data.get("batch") or "").strip() or f"upload-{timezone.now():%Y%m%d-%H%M%S}"
        report = enrolment_service.import_batch(rows, batch=batch, kebele=kebele, actor=request.user)
        # Rows whose cells could not be read never reached the service, so they
        # are absent from its counts. Reported beside them rather than folded in:
        # "we could not read this" and "this needs a woreda officer" are
        # different problems with different owners.
        report["unreadable"] = unreadable
        return Response(report)

    @action(detail=True, methods=["get"])
    def journey(self, request, pk=None):
        """Registered → verified → in a group → linked, with every gate named.

        Computed on request, like the group readiness card and for the same
        reason: it has to change the moment a woreda officer verifies her or a
        facilitator seats her, or the screen teaches people not to trust it.
        """
        profile = self.get_object()
        return Response(journey_service.build(profile))

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        """A woreda officer confirms or refuses an exception-route registration."""
        profile = self.get_object()
        if request.user.wlt_approval_level is None:
            raise DRFValidationError({"detail": [_("Your role does not verify registrations.")]})
        try:
            enrolment_service.verify(
                profile,
                actor=request.user,
                approved=bool(request.data.get("approved")),
                reason=request.data.get("reason", ""),
            )
        except ValidationError as exc:
            raise _as_drf_error(exc)
        return Response(BeneficiaryProfileSerializer(profile).data)


class MobilisationEventViewSet(ScopedGroupQuerySetMixin, viewsets.ModelViewSet):
    """The community meeting — handbook 3.4 step 1, and step 0 of drafting a group.

    It had no route at all, which is why creating a group had no route either:
    `open_draft` wants an endorsed event, and nothing outside the admin could
    produce one. A facilitator convening her first meeting could not record it.

    Scoped like every other group record. Note the bootstrap this deliberately
    permits: a facilitator's group scope is the kebeles of groups she already
    runs, so she can *read* no events in a kebele where she has no group yet —
    but she may still record one there, because mobilising a new kebele is
    precisely the act that has no prior group behind it. The same shape as
    `CanEnrolBeneficiaries`: the write is the bootstrap, so gating it on what
    she can already see would leave it doable by nobody.
    """

    queryset = MobilisationEvent.objects.select_related("kebele", "facilitator").all()
    serializer_class = MobilisationEventSerializer
    # `CanDraftGroups`, not `CanAccessGroups`: convening the community meeting
    # and drafting the group from it are one act. Letting a woreda officer draft
    # while refusing her the meeting it must be drafted from would leave her
    # able to start a group only where a facilitator had already been — which
    # is the bootstrap problem the widening exists to solve.
    permission_classes = [IsOperational, CanDraftGroups]
    kebele_field = "kebele"
    facilitator_field = "facilitator_id"
    filterset_fields = {"endorsement_obtained": ["exact"], "kebele": ["exact"]}
    search_fields = ["kebele__name", "endorsement_note"]
    ordering_fields = ["held_on", "created_at"]
    ordering = ["-held_on"]

    def get_queryset(self):
        """`?endorsed_only=true` — the meetings a group can be drafted from.

        The group form asks for exactly this set. Expressed as its own
        parameter rather than left to the caller to remember, because a form
        that offered a refused meeting would collect a submission the service
        is bound to reject.
        """
        queryset = super().get_queryset()
        if self.request.query_params.get("endorsed_only") in ("true", "1"):
            queryset = queryset.filter(endorsement_obtained=True)
        return queryset

    def perform_create(self, serializer):
        # §4.1's `registering_worker` rule: the accountability record names the
        # account that convened the meeting, taken from the request.
        serializer.save(facilitator=self.request.user)

    def perform_destroy(self, instance):
        """Nothing deletes a mobilisation event.

        A refused endorsement only explains a kebele with no groups in it for
        as long as the row survives (A30), and a deleted meeting would take the
        group drafted from it with it — the FK is PROTECT.
        """
        raise MethodNotAllowed("DELETE")


class SyncConflictViewSet(
    ScopedGroupQuerySetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Records two devices disagree about. Resolved by a person, never merged."""

    queryset = SyncConflict.objects.select_related("group").all()
    serializer_class = SyncConflictSerializer
    permission_classes = [IsOperational, CanAccessGroups]
    kebele_field = "group__kebele"
    facilitator_field = "group__facilitator_id"

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        from django.utils import timezone

        conflict = self.get_object()
        conflict.resolved_at = timezone.now()
        conflict.resolved_by = request.user
        conflict.resolution_note = request.data.get("note", "")
        conflict.save(update_fields=["resolved_at", "resolved_by", "resolution_note", "updated_at"])
        return Response(SyncConflictSerializer(conflict).data)


class ReportViewSet(viewsets.ViewSet):
    """The aggregate screens, read from the materialized views."""

    permission_classes = [IsOperational, CanAccessGroups]

    def _visible_woreda_ids(self, request):
        """The woredas this account may read, by the same walk as the kebeles.

        Separate from `_visible_kebele_ids` rather than derived from it: a
        federation forms in a woreda, and an officer scoped to a woreda can see
        it whether or not any of its kebeles holds a group yet.
        """
        woredas = Location.objects.active().filter(level="WOREDA")
        scope = request.user.wlt_scope_location
        if request.user.group_scope() == "ALL" or scope is None:
            return list(woredas.values_list("pk", flat=True))
        visible = []
        for woreda in woredas.select_related("parent__parent"):
            node = woreda
            while node is not None:
                if node.pk == scope.pk:
                    visible.append(woreda.pk)
                    break
                node = node.parent
        # A scope *below* woreda level — a facilitator on one kebele — still
        # reads the woreda that contains it, because that is where a federation
        # would form. Without this her screen is empty rather than informative.
        if not visible and scope is not None:
            node = scope
            while node is not None:
                if node.level == "WOREDA":
                    visible.append(node.pk)
                    break
                node = node.parent
        return visible

    def _visible_kebele_ids(self, request):
        kebeles = Location.objects.active().filter(level="KEBELE")
        scope = request.user.wlt_scope_location
        if request.user.group_scope() == "ALL" or scope is None:
            return list(kebeles.values_list("pk", flat=True))
        visible = []
        for kebele in kebeles.select_related("parent__parent__parent"):
            node = kebele
            while node is not None:
                if node.pk == scope.pk:
                    visible.append(kebele.pk)
                    break
                node = node.parent
        return visible

    @action(detail=False, methods=["get"], url_path="federation-readiness")
    def federation_readiness(self, request):
        """Per woreda: active CLAs against the federation threshold.

        Scoped like every other aggregate here — "eleven CLAs in Dessie Zuria"
        told to somebody entitled to see one woreda is still a disclosure.
        """
        woreda_ids = self._visible_woreda_ids(request)
        return Response({"rows": reporting.federation_readiness(woreda_ids)})

    @action(detail=False, methods=["get"], url_path="cla-readiness")
    def cla_readiness(self, request):
        """Per kebele: eligible groups, the threshold, how many more are needed.

        Scoped to the kebeles the user can see. An aggregate is a disclosure
        too: "eleven groups in Chifra" told to somebody entitled to see two is
        still a leak.
        """
        kebele_ids = self._visible_kebele_ids(request)
        rows = reporting.cla_readiness(kebele_ids)
        present = {row["kebele_id"] for row in rows}
        for kebele in Location.objects.filter(pk__in=set(kebele_ids) - present):
            threshold = wlt_policy.resolve_int("gate.cla.min_groups", location=kebele, default=8)
            rows.append(
                {
                    "kebele_id": kebele.pk,
                    "kebele": kebele.name,
                    "eligible_groups": 0,
                    "threshold": threshold,
                    "groups_short": threshold,
                }
            )
        rows.sort(key=lambda row: (row["groups_short"], row["kebele"]))
        return Response({"rows": rows})

    @action(detail=False, methods=["get"], url_path="linkage-funnel")
    def linkage_funnel(self, request):
        return Response({"funnel": reporting.linkage_funnel(), "block_reasons": reporting.block_reasons()})

    @action(detail=False, methods=["get"], url_path="enrolment")
    def enrolment(self, request):
        return Response({"rows": reporting.enrolment_vs_allocation()})

    @action(detail=False, methods=["get"], url_path="formation-attrition")
    def formation_attrition(self, request):
        return Response({"rows": reporting.formation_attrition()})

    @action(detail=False, methods=["get"], url_path="cohort-survival")
    def cohort_survival(self, request):
        return Response({"rows": reporting.cohort_survival()})
