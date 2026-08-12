"""Serializers for Partner (spec §4.11)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.locations.models import Location

from .models import Partner


class PartnerSerializer(serializers.ModelSerializer):
    partner_type_display = serializers.CharField(source="get_partner_type_display", read_only=True)
    mou_status_display = serializers.CharField(source="get_mou_status_display", read_only=True)
    can_receive_referrals = serializers.BooleanField(read_only=True)

    class Meta:
        model = Partner
        fields = [
            "id",
            "partner_name",
            "partner_type",
            "partner_type_display",
            "woreda_coverage",
            "contact_name",
            "phone",
            "email",
            "active_status",
            "can_receive_referrals",
            "mou_status",
            "mou_status_display",
            "mou_date",
            "performance_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_woreda_coverage(self, value):
        """Keep coverage inside the controlled vocabulary.

        Same reasoning as Youth.woreda: a typo here silently removes the partner
        from every woreda-matched referral picker without any visible error.
        """
        known = set(Location.objects.active().woredas().filter(name__in=value).values_list("name", flat=True))
        unknown = [name for name in value if name not in known]
        if unknown:
            raise serializers.ValidationError(
                f"Unknown woreda(s): {', '.join(unknown)}. Choose from /api/v1/locations/?level=WOREDA."
            )
        return value

    def validate(self, attrs):
        candidate = self.instance or Partner()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class PartnerSummarySerializer(serializers.ModelSerializer):
    """Compact form for referral destination pickers and user records."""

    partner_type_display = serializers.CharField(source="get_partner_type_display", read_only=True)

    class Meta:
        model = Partner
        fields = ["id", "partner_name", "partner_type", "partner_type_display", "woreda_coverage", "active_status"]
        read_only_fields = fields
