"""Grievance serializers — spec §4.10."""

from rest_framework import serializers

from .models import Grievance


class GrievanceSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True, default=None)
    complaint_type_display = serializers.CharField(source="get_complaint_type_display", read_only=True)
    raised_by_display = serializers.CharField(source="get_raised_by_display", read_only=True)
    status_display = serializers.CharField(source="get_resolution_status_display", read_only=True)
    assigned_staff_name = serializers.CharField(source="assigned_staff.full_name", read_only=True)
    partner_name = serializers.CharField(source="about_partner.partner_name", read_only=True, default=None)
    days_open = serializers.IntegerField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    is_sensitive = serializers.BooleanField(read_only=True)

    class Meta:
        model = Grievance
        fields = [
            "id",
            "case",
            "youth_name",
            "related_referral",
            "about_partner",
            "partner_name",
            "woreda",
            "complaint_type",
            "complaint_type_display",
            "raised_by",
            "raised_by_display",
            "complainant_name",
            "complainant_contact",
            "summary",
            "date_raised",
            "assigned_staff",
            "assigned_staff_name",
            "resolution_status",
            "status_display",
            "resolution_date",
            "resolution_notes",
            "referral_quality_feedback_flag",
            "days_open",
            "is_open",
            "is_sensitive",
            "created_at",
        ]
        # The lifecycle moves through `services`, which refuses a resolution
        # with no description of what was done. `referral_quality_feedback_flag`
        # is derived from the complaint type, so a "referral delay" nobody
        # ticked still reaches the partner panel.
        read_only_fields = [
            "resolution_status",
            "resolution_date",
            "resolution_notes",
            "referral_quality_feedback_flag",
        ]
        extra_kwargs = {
            # Case-linked grievances inherit their location from the case. This
            # must be optional at the field-validation stage so `validate()` can
            # perform that inheritance when clients omit `woreda` entirely.
            "woreda": {"required": False, "allow_blank": True},
        }

    def validate(self, attrs):
        case = attrs.get("case", getattr(self.instance, "case", None))
        woreda = attrs.get("woreda", getattr(self.instance, "woreda", ""))
        if case is not None:
            attrs["woreda"] = case.woreda
            woreda = case.woreda
        if case is None and not woreda:
            # Without one the complaint is invisible to every supervisor, which
            # is the only way it reaches anybody.
            raise serializers.ValidationError(
                {"woreda": "Say which woreda this concerns, so it reaches the right office."}
            )
        return attrs


class ResolveSerializer(serializers.Serializer):
    notes = serializers.CharField()
    resolution_date = serializers.DateField(required=False)


class CloseSerializer(serializers.Serializer):
    reason = serializers.CharField()
    closed_on = serializers.DateField(required=False)
