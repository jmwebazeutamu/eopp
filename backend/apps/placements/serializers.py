"""Placement serializers — spec §4.7.

`exit_date` and `exit_reason` are read-only on the placement: recording an exit
closes the outstanding retention checkpoints, and a PATCH that set the two
fields directly would leave three checks pending against a job that has ended.
`POST .../exit/` is the supported route.
"""

from rest_framework import serializers

from .models import Placement, RetentionCheck, RetentionStatus, placement_referral_error


class RetentionCheckSerializer(serializers.ModelSerializer):
    checked_by_name = serializers.CharField(source="checked_by.full_name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = RetentionCheck
        fields = [
            "id",
            "placement",
            "checkpoint",
            "due_date",
            "status",
            "status_display",
            "checked_on",
            "checked_by",
            "checked_by_name",
            "note",
            "is_overdue",
        ]
        # Every one of these moves through `services.record_check`, which
        # requires an actor: §9 wants a name against a status change, and a
        # retention figure whose checks nobody signed is not evidence.
        read_only_fields = ["placement", "checkpoint", "due_date", "status", "checked_on", "checked_by"]


class PlacementSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True)
    woreda = serializers.CharField(source="case.woreda", read_only=True)
    placement_type_display = serializers.CharField(source="get_placement_type_display", read_only=True)
    exit_reason_display = serializers.CharField(source="get_exit_reason_display", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True)
    retention_checks = RetentionCheckSerializer(many=True, read_only=True)
    days_held = serializers.IntegerField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = Placement
        fields = [
            "id",
            "case",
            "youth_name",
            "woreda",
            "source_referral",
            "employer_name",
            "sector",
            "placement_type",
            "placement_type_display",
            "placement_date",
            "wage_amount",
            "contract_type",
            "contract_duration",
            "is_subsidised",
            "exit_date",
            "exit_reason",
            "exit_reason_display",
            "exit_note",
            "recorded_by",
            "recorded_by_name",
            "retention_checks",
            "days_held",
            "is_open",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["exit_date", "exit_reason", "exit_note", "recorded_by"]
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
            # serializer. `placement_referral_error` is the one definition.
            problem = placement_referral_error(source_referral, case)
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


class RecordCheckSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            (RetentionStatus.RETAINED, RetentionStatus.RETAINED.label),
            (RetentionStatus.EXITED, RetentionStatus.EXITED.label),
            # A real answer, not a missing one. At 90 days a meaningful share of
            # youth cannot be reached, and forcing that into "not retained"
            # would overstate loss.
            (RetentionStatus.UNREACHABLE, RetentionStatus.UNREACHABLE.label),
        ]
    )
    checked_on = serializers.DateField(required=False)
    note = serializers.CharField(required=False, allow_blank=True)


class ExitSerializer(serializers.Serializer):
    exit_date = serializers.DateField()
    # OQ-5: an enum, not free text. "Left for a better job" and "dismissed" are
    # opposite results, and a text field could not tell a report which happened.
    exit_reason = serializers.ChoiceField(choices=Placement._meta.get_field("exit_reason").choices)
    exit_note = serializers.CharField(required=False, allow_blank=True)
