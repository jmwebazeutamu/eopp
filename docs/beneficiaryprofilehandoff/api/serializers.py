"""
Beneficiary detail serializer.

Response shape is grouped by card, not flat: identity / household / case /
pathway / savings_group / finance / linkages. One request fills the page.

Money is serialised as a STRING, never a float — the UI formats it and must
never round it.

Select-related everything the page touches; the old page issued one query
per stage check.
"""

from decimal import Decimal
from rest_framework import serializers


class MoneyField(serializers.Field):
    """Decimal -> "1040.00" string, two places, no locale."""

    def to_representation(self, value: Decimal) -> str:
        return f"{(value or Decimal('0')):.2f}"


class IdentitySerializer(serializers.Serializer):
    full_name = serializers.CharField()
    reference_code = serializers.CharField()
    psnp_client_number = serializers.CharField(allow_null=True)
    photo_url = serializers.SerializerMethodField()
    date_of_birth = serializers.DateField(allow_null=True)
    age = serializers.IntegerField(allow_null=True)
    age_is_estimated = serializers.BooleanField()
    phone = serializers.CharField(allow_null=True)
    woreda = serializers.SerializerMethodField()
    kebele = serializers.SerializerMethodField()
    household_size = serializers.IntegerField(allow_null=True)
    registered_on = serializers.DateField()
    status = serializers.CharField()
    exited_on = serializers.DateField(allow_null=True)
    exit_reason = serializers.CharField(allow_null=True)
    missing_field_count = serializers.IntegerField()

    def get_photo_url(self, obj):
        return obj.photo.url if obj.photo else None

    def get_woreda(self, obj):
        return {"id": str(obj.woreda_id), "name": obj.woreda.name} if obj.woreda_id else None

    def get_kebele(self, obj):
        return {"id": str(obj.kebele_id), "name": obj.kebele.name} if obj.kebele_id else None


class FinanceSerializer(serializers.Serializer):
    currency = serializers.CharField(default="ETB")
    savings_total = MoneyField()
    loans_received_total = MoneyField()
    loan_count = serializers.IntegerField()
    repayments_total = MoneyField()
    repayments_principal = MoneyField()
    repayments_service_charge = MoneyField()
    principal_outstanding = MoneyField()


class BeneficiaryDetailSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    identity = IdentitySerializer(source="*")
    household = serializers.SerializerMethodField()
    case = serializers.SerializerMethodField()
    pathway = serializers.SerializerMethodField()
    savings_group = serializers.SerializerMethodField()
    finance = FinanceSerializer(source="*")
    linkages = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    def get_household(self, obj):
        return {
            "is_head_of_household": obj.is_head_of_household,
            "marital_status": obj.marital_status,
            "dependants_count": obj.dependants_count,
            "dependants_under_5": obj.dependants_under_5,
            "disability_type": obj.disability_type,
            "disability_notes": obj.disability_notes,
            "education_level": obj.education_level,
            "education_grade": obj.education_grade,
        }

    def get_case(self, obj):
        agent = obj.development_agent
        return {
            "development_agent": {"id": str(agent.id), "name": agent.name} if agent else None,
            # annotate in the queryset: Max("contacts__occurred_on")
            "last_contact_on": obj.last_contact_on,
            "enterprise": (
                {"id": str(e.id), "name": e.name, "status": e.status}
                if (e := obj.active_enterprise) else None
            ),
            # annotate: Count("grievances", filter=Q(grievances__status="open"))
            "open_grievance_count": obj.open_grievance_count,
        }

    def get_permissions(self, obj):
        user = self.context["request"].user
        return {
            "can_edit": user.has_perm("wlt.change_beneficiary"),
            "can_log_contact": user.has_perm("wlt.add_contactlog"),
        }
