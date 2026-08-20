"""Enterprise serializers — spec §4.8.

Disbursement, trading and closure all move through `services`, which is why the
fields that record them are read-only: `record_disbursement` refuses money
against an unapproved plan and moves the case to Placed, and a PATCH would do
neither.
"""

from rest_framework import serializers

from .models import Enterprise, EnterpriseMilestone, enterprise_referral_error


class EnterpriseMilestoneSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = EnterpriseMilestone
        fields = [
            "id",
            "enterprise",
            "milestone_name",
            "target_date",
            "completion_date",
            "status",
            "status_display",
            "note",
            "is_overdue",
        ]
        read_only_fields = ["status", "completion_date"]


class EnterpriseSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True)
    woreda = serializers.CharField(source="case.woreda", read_only=True)
    plan_status_display = serializers.CharField(source="get_business_plan_status_display", read_only=True)
    support_type_display = serializers.CharField(source="get_support_type_display", read_only=True)
    market_linkage_display = serializers.CharField(source="get_market_linkage_status_display", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True)
    milestones = EnterpriseMilestoneSerializer(many=True, read_only=True)
    milestones_achieved = serializers.IntegerField(read_only=True)
    milestones_overdue = serializers.IntegerField(read_only=True)
    has_support = serializers.BooleanField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Enterprise
        fields = [
            "id",
            "case",
            "youth_name",
            "woreda",
            "source_referral",
            "business_name",
            "sector",
            "business_plan_status",
            "plan_status_display",
            "support_type",
            "support_type_display",
            "grant_or_loan_amount",
            "disbursement_date",
            "mentorship_sessions_count",
            "business_registration_status",
            "business_registration_number",
            "market_linkage_status",
            "market_linkage_display",
            "started_trading_on",
            "closed_on",
            "closure_reason",
            "recorded_by",
            "recorded_by_name",
            "milestones",
            "milestones_achieved",
            "milestones_overdue",
            "has_support",
            "is_open",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "business_plan_status",
            "support_type",
            "grant_or_loan_amount",
            "disbursement_date",
            "started_trading_on",
            "closed_on",
            "closure_reason",
            "recorded_by",
        ]
        extra_kwargs = {
            "case": {"required": False},
            "source_referral": {"required": False},
        }

    def validate(self, attrs):
        source_referral = attrs.get("source_referral", getattr(self.instance, "source_referral", None))
        case = attrs.get("case", getattr(self.instance, "case", None))

        if self.instance is None:
            # The category rule has to be here as well as on the model: a
            # `ModelSerializer` does not run `full_clean`, so a rule stated only
            # in `clean()` is unenforced wherever the viewset saves through the
            # serializer. `enterprise_referral_error` is the one definition.
            problem = enterprise_referral_error(source_referral, case)
            if problem:
                mismatch = source_referral is not None and case is not None and source_referral.case_id != case.pk
                raise serializers.ValidationError(
                    {"case": "The case comes from the source referral and cannot differ."}
                    if mismatch
                    else {"source_referral": str(problem)}
                )
            # §4.2: the case is the referral's, never the client's.
            attrs["case"] = source_referral.case
        else:
            if "source_referral" in attrs and source_referral != self.instance.source_referral:
                raise serializers.ValidationError({"source_referral": "The source referral cannot be changed."})
            if "case" in attrs and case != self.instance.case:
                raise serializers.ValidationError(
                    {"case": "The case is derived from the source referral and cannot change."}
                )

        return attrs


class PlanStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Enterprise._meta.get_field("business_plan_status").choices)
    note = serializers.CharField(required=False, allow_blank=True)


class DisbursementSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    support_type = serializers.ChoiceField(choices=Enterprise._meta.get_field("support_type").choices)
    disbursed_on = serializers.DateField(required=False)


class TradingSerializer(serializers.Serializer):
    started_on = serializers.DateField(required=False)
    market_linkage_status = serializers.ChoiceField(
        choices=Enterprise._meta.get_field("market_linkage_status").choices, required=False
    )


class MilestoneOutcomeSerializer(serializers.Serializer):
    completion_date = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class MissMilestoneSerializer(serializers.Serializer):
    reason = serializers.CharField()


class CloseEnterpriseSerializer(serializers.Serializer):
    reason = serializers.CharField()
    closed_on = serializers.DateField(required=False)
