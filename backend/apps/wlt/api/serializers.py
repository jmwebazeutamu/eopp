"""WLT serializers. Thin — every rule lives in `apps.wlt.services`.

Two fields are read-only everywhere they appear, for the same reason the youth
referral serializer marks `status` read-only: `ServiceLinkage.status` moves only
through `transition_to`, and `Group.current_phase` moves only through the phase
machine. Writing either directly would skip the gate evaluation, the evidence
snapshot and the approval that justify it.
"""

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.locations.models import Location, LocationLevel
from apps.users.models import Role, User
from apps.wlt.models import (
    BeneficiaryProfile,
    BylawVersion,
    Group,
    GroupMembership,
    LedgerEntry,
    LinkageEvent,
    LinkageStatus,
    Loan,
    Meeting,
    MobilisationEvent,
    OfficeHolder,
    PhaseEvent,
    RiskFlag,
    ServiceLinkage,
    ServiceLinkageType,
    SyncConflict,
)


class ConditionSerializer(serializers.Serializer):
    """One gate condition — **always the actual value next to the threshold**.

    The rule the whole readiness card exists for. A screen that renders only
    `met` turns this back into a red dot, and a red dot changes nothing about
    what a facilitator does next week.
    """

    code = serializers.CharField()
    label = serializers.CharField()
    threshold = serializers.JSONField()
    actual = serializers.JSONField()
    met = serializers.BooleanField()
    unmeasurable = serializers.BooleanField()
    unit = serializers.CharField(allow_blank=True)


class GateResultSerializer(serializers.Serializer):
    gate_set = serializers.CharField()
    passed = serializers.BooleanField()
    conditions = ConditionSerializer(many=True)
    policy_version_id = serializers.CharField()
    computed_at = serializers.CharField()


class BeneficiaryProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="person.full_name", read_only=True)
    is_programme_eligible = serializers.BooleanField(read_only=True)
    is_assignable = serializers.BooleanField(read_only=True)
    # The group she is in *now*, or null. Distinct from `is_assignable`, which
    # answers "could she join one" — a woman can be unassignable for four other
    # reasons, so reading a blank group off that flag would name the wrong
    # problem on screen.
    current_group = serializers.SerializerMethodField()

    class Meta:
        model = BeneficiaryProfile
        fields = [
            "id",
            "person",
            "full_name",
            "psnp_client_id",
            "psnp_woreda",
            "psnp_kebele",
            "els_completed_on",
            "els_grant_received_on",
            "primary_iga",
            "literacy_level",
            "digital_literacy",
            "has_device",
            "household_head",
            "enrolment_route",
            "verification_status",
            "verification_note",
            "verified_on",
            "is_programme_eligible",
            "is_assignable",
            "current_group",
        ]
        read_only_fields = ["verification_status", "verified_on", "enrolment_route"]

    def get_current_group(self, profile):
        """Her open membership, as `{id, name, joined_on}`, or null.

        Membership is a dated range, never a flag, so "in a group" means an
        open range and nothing else — a woman who left in April is not in a
        group in May, and her closed row still has to stay on the roster
        because February's attendance denominator is computed against it.

        Reads the prefetch the viewset sets up, and falls back to a query when
        there is none: the serializer is also used for a single profile just
        created by `register`, which has no prefetched attribute on it. Without
        the fallback that path would raise, and with a bare query in the list
        path this would be one SELECT per row.
        """
        prefetched = getattr(profile.person, "open_memberships", None)
        if prefetched is None:
            membership = (
                GroupMembership.objects.filter(person_id=profile.person_id, exited_on__isnull=True)
                .select_related("group")
                .first()
            )
        else:
            membership = prefetched[0] if prefetched else None

        if membership is None:
            return None
        return {
            "id": str(membership.group_id),
            "name": membership.group.name,
            "joined_on": membership.joined_on,
        }


class GroupMembershipSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="person.full_name", read_only=True)
    exit_reason_display = serializers.CharField(source="get_exit_reason_display", read_only=True)

    class Meta:
        model = GroupMembership
        fields = [
            "id",
            "group",
            "person",
            "full_name",
            "joined_on",
            "exited_on",
            "exit_reason",
            "exit_reason_display",
            "exit_note",
        ]
        # An exit moves through the action, which checks her outstanding loan
        # (A11). A writable `exited_on` here would be a way around that check.
        read_only_fields = ["exited_on", "exit_reason"]


class OfficeHolderSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="person.full_name", read_only=True)

    class Meta:
        model = OfficeHolder
        fields = ["id", "group", "person", "full_name", "role", "from_date", "to_date"]
        read_only_fields = ["to_date"]


class BylawVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BylawVersion
        fields = [
            "id",
            "group",
            "version_no",
            "effective_from",
            "effective_to",
            "meeting_cadence",
            "meeting_day",
            "contribution_etb",
            "service_charge_basis",
            "service_charge_rate",
            "service_charge_label",
            "late_penalty_etb",
            "absence_penalty_etb",
            "officer_rotation_months",
            "loan_quorum_pct",
            "max_concurrent_loans",
            "reserve_buffer_pct",
            "clauses_local_language",
        ]
        read_only_fields = ["version_no", "effective_to"]

    def validate_service_charge_basis(self, value):
        # Open question Q4. A flat 5% per loan and 5% per month on a three-month
        # loan differ by a factor of three, so there is no default and the form
        # cannot be submitted without an explicit choice.
        if not value:
            raise serializers.ValidationError("Choose how the service charge is calculated. There is no default.")
        return value


class MobilisationEventSerializer(serializers.ModelSerializer):
    """Handbook 3.4 step 1 — the community meeting a group is drafted from.

    Recorded whether or not the community endorsed. A refusal is not a failed
    submission: it closes the mobilisation, and the row is what explains a
    kebele with no groups in it (assertion A30). So `endorsement_obtained:
    false` is a perfectly good POST and the screen says so.

    `facilitator` is stamped from the request rather than accepted, on the
    §4.1 `registering_worker` precedent — this is an accountability record of
    who convened the meeting, and a client that could name somebody else could
    desynchronise it from who was actually in the room.
    """

    # By `code`, like `/wlt/profiles/register/`: that is what the locations API
    # emits and looks up on, and a Location's integer pk appears nowhere a
    # client can see. A PrimaryKeyRelatedField here would be unusable from the
    # web app for exactly that reason.
    kebele = serializers.SlugRelatedField(slug_field="code", queryset=Location.objects.all())
    kebele_name = serializers.CharField(source="kebele.name", read_only=True)
    facilitator_name = serializers.CharField(source="facilitator.full_name", read_only=True)
    # Whether a group has already been drafted from this meeting. One meeting
    # can endorse more than one group — twenty-five women may split into two —
    # so this is shown, not enforced.
    groups_drafted = serializers.SerializerMethodField()

    class Meta:
        model = MobilisationEvent
        fields = [
            "id",
            "kebele",
            "kebele_name",
            "held_on",
            "facilitator",
            "facilitator_name",
            "attendees_potential",
            "attendees_husbands",
            "attendees_elders",
            "attendees_leaders",
            "endorsement_obtained",
            "endorsement_note",
            "groups_drafted",
            "created_at",
        ]
        read_only_fields = ["facilitator", "created_at"]

    def get_groups_drafted(self, event):
        return event.groups.count()

    def validate_kebele(self, kebele):
        if kebele.level != LocationLevel.KEBELE:
            raise serializers.ValidationError(_("A community meeting is held in a kebele."))
        return kebele

    def validate(self, attrs):
        # A refusal that says nothing is not programme learning, it is a blank.
        # The handbook wants the reason a community declined; A30 is the
        # assertion that reads these rows.
        if attrs.get("endorsement_obtained") is False and not (attrs.get("endorsement_note") or "").strip():
            raise serializers.ValidationError(
                {
                    "endorsement_note": _(
                        "Say why the community did not endorse. A refusal with no reason teaches us nothing."
                    )
                }
            )
        return attrs


class GroupSerializer(serializers.ModelSerializer):
    kebele_name = serializers.CharField(source="kebele.name", read_only=True)
    members_current = serializers.SerializerMethodField()
    facilitator_name = serializers.CharField(source="facilitator.full_name", read_only=True)
    # Display strings come from the model's own choices, so a screen cannot
    # invent its own wording for a status and drift from the counter row that
    # filters to it.
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    phase_display = serializers.CharField(source="get_current_phase_display", read_only=True)
    # Optional on the wire so a facilitator drafting her own group need not name
    # herself; `validate` refuses to let anybody else leave it blank.
    facilitator = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False)
    # Optional because `open_draft` defaults it to today. Still accepted, and
    # deliberately: these groups are formed in a meeting and entered afterwards,
    # sometimes days later from a paper register, and a drafting date forced to
    # the day of data entry would misdate every cohort computed from it.
    drafted_on = serializers.DateField(required=False)

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "kebele",
            "kebele_name",
            "mobilisation_event",
            "facilitator",
            "facilitator_name",
            "status",
            "status_display",
            "current_phase",
            "phase_display",
            "drafted_on",
            "constituted_on",
            "activated_on",
            "phase_entered_on",
            "closed_on",
            "closure_reason",
            "members_current",
            "created_at",
            "updated_at",
        ]
        # Status and phase move through `services.formation` and
        # `services.phase`. A PATCH that set either would skip the gate, the
        # snapshot and the approval.
        #
        # `kebele` is read-only because it is derived from the mobilisation
        # event: a group drafted from a meeting held in one kebele belongs to
        # that kebele, and a hand-typed one that disagreed would scope to one
        # place and report in another. Same rule as `Case.woreda`, and as the
        # region/zone/woreda derived at `POST /wlt/profiles/register/`.
        read_only_fields = [
            "kebele",
            "status",
            "current_phase",
            "constituted_on",
            "activated_on",
            "phase_entered_on",
        ]

    def get_members_current(self, group):
        return group.current_members.count()

    def validate_mobilisation_event(self, event):
        """The endorsement gate, stated where a client can be told about it.

        `formation.open_draft` refuses an unendorsed event too, and that is the
        real enforcement — this exists so the refusal arrives as a field error
        on the form rather than as a 400 with a sentence in it.
        """
        if event is not None and not event.endorsement_obtained:
            raise serializers.ValidationError(
                _("This community meeting did not endorse a group, so no group can be drafted from it.")
            )
        return event

    def validate(self, attrs):
        # A facilitator drafting her own group need not name herself; anybody
        # else must name one. An administrator has `group_write` and is not a
        # facilitator, so defaulting to the request user would leave the group
        # with an administrator in the field slot — and `OWN_GROUPS` scoping
        # keys on exactly that column, so the real facilitator would then be
        # unable to see the group she runs.
        if self.instance is None and attrs.get("facilitator") is None:
            actor = self.context["request"].user
            if actor.role != Role.WLT_FACILITATOR:
                raise serializers.ValidationError(
                    {"facilitator": _("Name the facilitator who will run this group.")}
                )
        facilitator = attrs.get("facilitator")
        event = attrs.get("mobilisation_event")
        if self.instance is None and facilitator is not None:
            if facilitator.role != Role.WLT_FACILITATOR:
                raise serializers.ValidationError({"facilitator": _("Choose a WLT group facilitator.")})
            if event is not None and facilitator.wlt_scope_location_id:
                node = event.kebele
                covered = False
                while node is not None:
                    if node.pk == facilitator.wlt_scope_location_id:
                        covered = True
                        break
                    node = node.parent
                if not covered:
                    raise serializers.ValidationError(
                        {"facilitator": _("This facilitator's geography does not cover the meeting's kebele.")}
                    )

        # Required on create, immutable afterwards. Required because the
        # endorsement check is only a control if it cannot be skipped, and
        # omitting the event skips it exactly as effectively as an unendorsed
        # one would. Immutable because the kebele is derived from it.
        if self.instance is None and attrs.get("mobilisation_event") is None:
            raise serializers.ValidationError(
                {
                    "mobilisation_event": _(
                        "Record the community meeting first. A group starts with the community endorsing it."
                    )
                }
            )
        if self.instance is not None and "mobilisation_event" in attrs:
            if attrs["mobilisation_event"] != self.instance.mobilisation_event:
                raise serializers.ValidationError(
                    {"mobilisation_event": _("A group cannot be moved to a different community meeting.")}
                )
        return attrs


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = [
            "id",
            "group",
            "meeting_no",
            "scheduled_for",
            "held_on",
            "opening_cash_etb",
            "closing_cash_etb",
            "counted_cash_etb",
            "social_time_minutes",
            "social_topic",
            "status",
            "closed_at",
            "device_id",
            "synced_at",
        ]
        read_only_fields = ["meeting_no", "status", "closed_at", "closing_cash_etb", "opening_cash_etb"]


class LedgerEntrySerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="person.full_name", read_only=True, default=None)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "group",
            "meeting",
            "person",
            "member_name",
            "loan",
            "entry_type",
            "account",
            "amount_etb",
            "reverses",
            "reversal_reason",
            "created_at",
        ]
        read_only_fields = ["reverses", "reversal_reason"]


class LoanSerializer(serializers.ModelSerializer):
    borrower_name = serializers.CharField(source="person.full_name", read_only=True)
    outstanding_principal_etb = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Loan
        fields = [
            "id",
            "group",
            "person",
            "borrower_name",
            "cycle_batch",
            "principal_etb",
            "charge_basis",
            "charge_rate",
            "purpose",
            "purpose_note",
            "disbursed_on",
            "due_on",
            "status",
            "outstanding_principal_etb",
            "written_off_on",
        ]
        # Frozen at disbursement, never read live from the bylaw afterwards.
        read_only_fields = ["charge_basis", "charge_rate", "status", "disbursed_on", "written_off_on"]


class ServiceLinkageTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceLinkageType
        fields = [
            "code",
            "label",
            "description",
            "allowed_subject_types",
            "min_phase",
            "approval_chain",
            "restricted",
            "lapse_days",
            "is_active",
        ]


class LinkageEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.full_name", read_only=True, default=None)

    class Meta:
        model = LinkageEvent
        fields = ["id", "from_status", "to_status", "occurred_at", "actor", "actor_name", "reason", "gate_snapshot"]


class ServiceLinkageSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="linkage_type.label", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    provider_name = serializers.CharField(source="provider.partner_name", read_only=True, default=None)
    subject_name = serializers.SerializerMethodField()
    next_approval_role = serializers.SerializerMethodField()
    next_action_role_display = serializers.SerializerMethodField()
    can_current_user_approve = serializers.SerializerMethodField()

    class Meta:
        model = ServiceLinkage
        fields = [
            "id",
            "linkage_type",
            "type_label",
            "provider",
            "provider_name",
            "subject_group",
            "subject_cla",
            "subject_federation",
            "subject_type",
            "subject_name",
            "status",
            "status_display",
            "opened_on",
            "approved_on",
            "activated_on",
            "closed_on",
            "value_etb",
            "terms",
            "guarantors",
            # The list a blocked facilitator reads. Carried on the row so the
            # blocked screen renders in one request.
            "block_reasons",
            "next_approval_role",
            "next_action_role_display",
            "can_current_user_approve",
        ]
        read_only_fields = ["status", "subject_type", "block_reasons", "approved_on", "activated_on", "closed_on"]

    def get_subject_name(self, linkage):
        subject = linkage.subject
        return str(subject) if subject is not None else None

    def _next_approval(self, linkage):
        if linkage.status != LinkageStatus.PENDING_APPROVAL:
            return None
        return linkage.approvals.filter(decision="").order_by("level").first()

    def get_next_approval_role(self, linkage):
        approval = self._next_approval(linkage)
        return approval.required_role if approval else None

    def get_next_action_role_display(self, linkage):
        if linkage.status in {LinkageStatus.REJECTED, LinkageStatus.CLOSED, LinkageStatus.LAPSED, LinkageStatus.DEFAULTED}:
            return None
        role = self.get_next_approval_role(linkage)
        if not role:
            role = Role.WLT_FACILITATOR
        try:
            return str(Role(role).label)
        except ValueError:
            return str(role).replace("_", " ").title()

    def get_can_current_user_approve(self, linkage):
        approval = self._next_approval(linkage)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if approval is None or not user or not user.is_authenticated:
            return False
        if approval.required_role and user.role not in (approval.required_role, Role.SYSTEM_ADMIN):
            return False
        if linkage.initiated_by_id == user.pk or linkage.approvals.filter(decided_by=user).exists():
            return False
        return True


class PhaseEventSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    submitted_by_name = serializers.CharField(source="submitted_by.full_name", read_only=True, default=None)

    class Meta:
        model = PhaseEvent
        fields = [
            "id",
            "group",
            "group_name",
            "from_phase",
            "to_phase",
            "direction",
            "submitted_by",
            "submitted_by_name",
            "submitted_at",
            "decided_by",
            "decided_at",
            "override_reason",
            "gate_snapshot",
        ]
        read_only_fields = fields


class RiskFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskFlag
        fields = ["id", "subject_type", "subject_id", "reason_code", "raised_on", "cleared_on", "detail"]
        read_only_fields = fields


class SyncConflictSerializer(serializers.ModelSerializer):
    class Meta:
        model = SyncConflict
        fields = [
            "id",
            "group",
            "entity",
            "natural_key",
            "payload",
            "device_id",
            "detail",
            "resolved_at",
            "resolution_note",
            "created_at",
        ]
        read_only_fields = ["payload", "entity", "natural_key", "device_id", "detail", "resolved_at"]


class WltRegistrationSerializer(serializers.Serializer):
    """The facilitator's exception-route registration form.

    A plain `Serializer`, not a `ModelSerializer`, because one submission writes
    two rows in two apps — a `youth.Youth` and her `BeneficiaryProfile` — and the
    service is what knows how to do that. A ModelSerializer over either one would
    have to reach into the other in `create`, which is the shape that lets a
    half-registered woman exist.

    The place is a kebele and nothing else. Region, zone and woreda are derived
    from it in the service, for the reason the youth importer gives: a hand-typed
    woreda that disagrees with its kebele scopes to one place and reports in
    another.
    """

    # Person
    full_name = serializers.CharField(max_length=255)
    date_of_birth = serializers.DateField()
    # By `code`, not by primary key. `code` is what the locations API emits and
    # what its own viewset looks up on; the integer pk appears nowhere a client
    # can see, so a PrimaryKeyRelatedField here asks for a value no screen has.
    kebele = serializers.SlugRelatedField(slug_field="code", queryset=Location.objects.all())
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True)
    national_or_kebele_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    household_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    # §9 of the youth spec makes consent the basis for holding the record at all,
    # and `Youth.clean` refuses a registration without it. Required here rather
    # than defaulted, so nobody can register a woman by leaving a box alone.
    consent_given = serializers.BooleanField()
    consent_date = serializers.DateField()

    # Profile
    psnp_client_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    els_completed_on = serializers.DateField(required=False, allow_null=True)
    els_grant_received_on = serializers.DateField(required=False, allow_null=True)
    primary_iga = serializers.CharField(max_length=128, required=False, allow_blank=True)
    literacy_level = serializers.CharField(max_length=16, required=False, allow_blank=True)
    digital_literacy = serializers.CharField(max_length=16, required=False, allow_blank=True)
    has_device = serializers.BooleanField(required=False, default=False)
    household_head = serializers.BooleanField(required=False, default=False)
    note = serializers.CharField(required=False, allow_blank=True)

    PROFILE_FIELDS = (
        "psnp_client_id",
        "els_completed_on",
        "els_grant_received_on",
        "primary_iga",
        "literacy_level",
        "digital_literacy",
        "has_device",
        "household_head",
    )

    def validate_consent_given(self, value):
        if not value:
            raise serializers.ValidationError(_("A woman cannot be registered without recorded consent."))
        return value

    def validate_kebele(self, value):
        if value.level != LocationLevel.KEBELE:
            raise serializers.ValidationError(_("Choose a kebele, not a woreda or a zone."))
        return value

    def split(self):
        """`(person_fields, profile_fields, note)` for `enrolment.register_by_facilitator`."""
        data = dict(self.validated_data)
        note = data.pop("note", "")
        profile_fields = {key: data.pop(key) for key in self.PROFILE_FIELDS if key in data}
        data.pop("kebele")
        return data, profile_fields, note


class JourneyConditionSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    threshold = serializers.CharField(allow_null=True)
    actual = serializers.CharField(allow_null=True)
    met = serializers.BooleanField()
    unit = serializers.CharField(allow_blank=True)
    unmeasurable = serializers.BooleanField()


class JourneyStageSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    state = serializers.CharField()
    conditions = JourneyConditionSerializer(many=True)
    detail = serializers.DictField()


class JourneySerializer(serializers.Serializer):
    """Documented for the schema; the service already returns plain dicts."""

    person = serializers.UUIDField()
    profile = serializers.UUIDField()
    full_name = serializers.CharField()
    stages = JourneyStageSerializer(many=True)
    stages_done = serializers.IntegerField()
    stages_total = serializers.IntegerField()
    next_action = JourneyStageSerializer(allow_null=True)
