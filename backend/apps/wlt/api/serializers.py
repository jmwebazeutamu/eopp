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
from apps.wlt.models import (
    BeneficiaryProfile,
    BylawVersion,
    Group,
    GroupMembership,
    LedgerEntry,
    LinkageEvent,
    Loan,
    Meeting,
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
        ]
        read_only_fields = ["verification_status", "verified_on", "enrolment_route"]


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


class GroupSerializer(serializers.ModelSerializer):
    kebele_name = serializers.CharField(source="kebele.name", read_only=True)
    members_current = serializers.SerializerMethodField()
    facilitator_name = serializers.CharField(source="facilitator.full_name", read_only=True)
    # Display strings come from the model's own choices, so a screen cannot
    # invent its own wording for a status and drift from the counter row that
    # filters to it.
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    phase_display = serializers.CharField(source="get_current_phase_display", read_only=True)

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "kebele",
            "kebele_name",
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
        read_only_fields = ["status", "current_phase", "constituted_on", "activated_on", "phase_entered_on"]

    def get_members_current(self, group):
        return group.current_members.count()


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
        ]
        read_only_fields = ["status", "subject_type", "block_reasons", "approved_on", "activated_on", "closed_on"]

    def get_subject_name(self, linkage):
        subject = linkage.subject
        return str(subject) if subject is not None else None


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
