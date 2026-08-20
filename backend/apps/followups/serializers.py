"""Follow-up serializers — spec §4.9."""

from rest_framework import serializers

from .models import ContactOutcome, FollowUp


class FollowUpSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True)
    woreda = serializers.CharField(source="case.woreda", read_only=True)
    contact_method_display = serializers.CharField(source="get_contact_method_display", read_only=True)
    contact_outcome_display = serializers.CharField(source="get_contact_outcome_display", read_only=True)
    conducted_by_name = serializers.CharField(source="conducted_by.full_name", read_only=True)
    reached_the_youth = serializers.BooleanField(read_only=True)

    class Meta:
        model = FollowUp
        fields = [
            "id",
            "case",
            "youth_name",
            "woreda",
            "related_referral",
            "attempt_date",
            "contact_method",
            "contact_method_display",
            "contact_outcome",
            "contact_outcome_display",
            "re_engagement_status",
            "pathway_revision_flag",
            "conducted_by",
            "conducted_by_name",
            "reached_the_youth",
            "notes",
            "created_at",
        ]
        read_only_fields = ["conducted_by"]

    def validate(self, attrs):
        """A conversation that never happened cannot have found anything.

        Checked here as well as in `Model.clean` so the message lands against
        the field on the form rather than at the top of it.
        """
        outcome = attrs.get("contact_outcome", getattr(self.instance, "contact_outcome", None))
        reached = outcome in ContactOutcome.reached()
        status = attrs.get("re_engagement_status", getattr(self.instance, "re_engagement_status", ""))

        if not reached and status not in ("", "NOT_APPLICABLE"):
            raise serializers.ValidationError(
                {"re_engagement_status": "Nobody was reached, so there is no answer to record."}
            )
        if not reached and attrs.get("pathway_revision_flag"):
            raise serializers.ValidationError(
                {"pathway_revision_flag": "A pathway revision has to come from a conversation with the youth."}
            )
        return attrs


class VerifyOutcomeSerializer(serializers.Serializer):
    """Turning a recorded outcome into a verified one — §6.2, §8.3."""

    verification_source = serializers.CharField()
    method = serializers.CharField(required=False, allow_blank=True)
