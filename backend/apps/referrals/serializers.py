"""Serializers for the referral engine (spec §4.6, §5, §6)."""

from rest_framework import serializers

from apps.partners.serializers import PartnerSummarySerializer

from .models import Referral, ReferralStatus
from .taxonomy import FailureReasonCode, OutcomeType, ReferralCategory


class ReferralCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReferralCategory
        fields = ["code", "label", "description", "exempt_from_parallel_cap", "requires_note", "is_active"]
        read_only_fields = fields


class OutcomeTypeSerializer(serializers.ModelSerializer):
    applies_to = serializers.SlugRelatedField(many=True, slug_field="code", read_only=True)

    class Meta:
        model = OutcomeType
        fields = ["code", "label", "description", "applies_to", "requires_note", "is_active"]
        read_only_fields = fields


class FailureReasonCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FailureReasonCode
        fields = ["code", "label", "description", "requires_note", "is_active"]
        read_only_fields = fields


class ReferralSerializer(serializers.ModelSerializer):
    """Read shape. Status changes go through the transition endpoints, never PATCH."""

    referral_category_label = serializers.CharField(source="referral_category.label", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    trigger_display = serializers.CharField(source="get_referral_trigger_display", read_only=True)
    confirmation_status_display = serializers.CharField(source="get_confirmation_status_display", read_only=True)
    receiving_partner_detail = PartnerSummarySerializer(source="receiving_partner", read_only=True)
    initiated_by_name = serializers.CharField(source="initiated_by.full_name", read_only=True)
    # Null when the partner confirmed through their own login; a staff name when
    # somebody recorded the answer on their behalf. The screen has to be able to
    # tell those apart, and so does the partner-performance card.
    confirmation_recorded_by_name = serializers.CharField(
        source="confirmation_recorded_by.full_name", read_only=True, default=None
    )
    outcome_type_label = serializers.CharField(source="outcome_type.label", read_only=True, default=None)
    failure_reason_label = serializers.CharField(source="failure_reason_code.label", read_only=True, default=None)
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True)
    # Denormalised on Case already (§4.2). Exposed because the cross-case
    # referral queue lists referrals without their case in hand, and the partner
    # picker for an onward or replacement referral needs the woreda to narrow to
    # partners that actually cover it.
    woreda = serializers.CharField(source="case.woreda", read_only=True)
    allowed_transitions = serializers.ListField(child=serializers.CharField(), read_only=True)
    counts_toward_parallel_cap = serializers.BooleanField(read_only=True)

    class Meta:
        model = Referral
        fields = [
            "id",
            "case",
            "youth_name",
            "woreda",
            "referral_category",
            "referral_category_label",
            "referral_trigger",
            "trigger_display",
            "is_parallel",
            "parallel_group_id",
            "counts_toward_parallel_cap",
            "parent_referral",
            "replacement_referral",
            "receiving_partner",
            "receiving_partner_detail",
            "receiving_contact_name",
            "initiated_date",
            "initiated_by",
            "initiated_by_name",
            "confirmation_status",
            "confirmation_status_display",
            "confirmed_date",
            "confirmed_by",
            "confirmation_recorded_by",
            "confirmation_recorded_by_name",
            "status",
            "status_display",
            "allowed_transitions",
            "outcome_type",
            "outcome_type_label",
            "outcome_date",
            "outcome_verified_by",
            "outcome_verification_method",
            # OQ-2. The free-text method above says *how*; this says how strong
            # it is, and §8.3's reportable headline filters on it. Exposed in
            # Sprint 6, when the M&E screen gained a way to change it.
            "verification_source",
            "failure_reason_code",
            "failure_reason_label",
            "failure_date",
            "notes",
            "created_at",
            "updated_at",
        ]
        # Everything the state machine owns is read-only here. §6.2 is the only
        # route between statuses; a PATCH that set `status` directly would skip
        # the required-field checks and the parallel-group bookkeeping.
        read_only_fields = [
            "id",
            "referral_trigger",
            "is_parallel",
            "parallel_group_id",
            "parent_referral",
            "replacement_referral",
            "initiated_by",
            "confirmation_status",
            "confirmed_date",
            "status",
            "outcome_type",
            "outcome_date",
            "outcome_verified_by",
            "outcome_verification_method",
            # Read-only for the same reason the three above are: it moves
            # through `followups.services.verify_referral_outcome`, which stamps
            # the source, the verifier and the method together. Setting it alone
            # is how the three drifted apart before Sprint 6.
            "verification_source",
            "failure_reason_code",
            "failure_date",
            "created_at",
            "updated_at",
        ]


class InitiateReferralSerializer(serializers.Serializer):
    """Spec §6.2, first row: case manager initiates a referral."""

    case = serializers.UUIDField()
    referral_category = serializers.SlugRelatedField(slug_field="code", queryset=ReferralCategory.objects.active())
    receiving_partner = serializers.UUIDField()
    receiving_contact_name = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class OnwardReferralSerializer(serializers.Serializer):
    """Confirming the Onward prompt on a Completed referral (spec §6.2)."""

    referral_category = serializers.SlugRelatedField(slug_field="code", queryset=ReferralCategory.objects.active())
    receiving_partner = serializers.UUIDField()
    receiving_contact_name = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class ReplacementReferralSerializer(OnwardReferralSerializer):
    """Confirming the Replacement prompt on a Failed referral (spec §6.2)."""


class ConfirmReferralSerializer(serializers.Serializer):
    """The partner's confirmation, entered by the partner or by staff.

    §4.6 types `confirmed_by` as free text because the person confirming is
    often partner-side staff with no platform account. When a case manager
    records the answer on the partner's behalf, `confirmed_by` still names who
    at the partner gave it, and the state machine stamps
    `confirmation_recorded_by` with the account that typed it.
    """

    confirmed_by = serializers.CharField(max_length=255)
    confirmed_date = serializers.DateField(required=False)


class DeclineReferralSerializer(serializers.Serializer):
    """Partner declines — §6.2 requires a failure reason and prompts a replacement."""

    failure_reason_code = serializers.SlugRelatedField(slug_field="code", queryset=FailureReasonCode.objects.active())
    notes = serializers.CharField(required=False, allow_blank=True)


class CompleteReferralSerializer(serializers.Serializer):
    """Recording a verified outcome (spec §6.2, Active -> Completed)."""

    outcome_type = serializers.SlugRelatedField(slug_field="code", queryset=OutcomeType.objects.active())
    outcome_date = serializers.DateField(required=False)
    outcome_verification_method = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class FailReferralSerializer(serializers.Serializer):
    """Non-attendance, dropout, or other failure (spec §6.2, Active -> Failed)."""

    failure_reason_code = serializers.SlugRelatedField(slug_field="code", queryset=FailureReasonCode.objects.active())
    failure_date = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class CancelReferralSerializer(serializers.Serializer):
    """Case manager withdraws before confirmation (spec §6.2).

    Distinct from a partner-side decline: §6.1 keeps Cancelled separate so the
    §8 partner performance dashboards do not count a withdrawal against the
    partner, and no replacement is prompted.
    """

    notes = serializers.CharField(required=False, allow_blank=True)


class ReferralStackNodeSerializer(serializers.Serializer):
    """A node in the §6.4 stack: one referral plus the referrals that follow it."""

    referral = ReferralSerializer()
    children = serializers.SerializerMethodField()

    def get_children(self, obj):
        return ReferralStackNodeSerializer(obj["children"], many=True).data


class TransitionOptionSerializer(serializers.Serializer):
    """Exposes the §6.2 table so clients can render only the legal actions."""

    to_status = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField()
    requires = serializers.ListField(child=serializers.CharField())


def describe_transitions(referral):
    from .models import TRANSITIONS

    return [
        {
            "to_status": to_status,
            "label": ReferralStatus(to_status).label,
            "description": transition.description,
            "requires": list(transition.requires),
        }
        for to_status, transition in TRANSITIONS.get(referral.status, {}).items()
    ]
