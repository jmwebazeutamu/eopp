"""Training enrolment serializers — spec §4.5.

`completion_status` is read-only, for the same reason `Referral.status` is: it
moves through `services`, which stamps the completion date, derives the dropout
flag and the onward-referral trigger, and touches the case. A PATCH that set it
directly would skip all four.
"""

from rest_framework import serializers

from .models import CompletionStatus, TrainingEnrolment, TrainingType, training_referral_error


class TrainingEnrolmentSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True)
    woreda = serializers.CharField(source="case.woreda", read_only=True)
    provider_name = serializers.CharField(source="training_provider.partner_name", read_only=True)
    training_type_display = serializers.CharField(source="get_training_type_display", read_only=True)
    completion_status_display = serializers.CharField(source="get_completion_status_display", read_only=True)
    recorded_by_name = serializers.CharField(source="recorded_by.full_name", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_in_training = serializers.IntegerField(read_only=True)

    class Meta:
        model = TrainingEnrolment
        fields = [
            "id",
            "case",
            "youth_name",
            "woreda",
            "training_type",
            "training_type_display",
            "trade_or_skill_area",
            "training_provider",
            "provider_name",
            "enrolment_date",
            "start_date",
            "end_date",
            "attendance_rate",
            "completion_status",
            "completion_status_display",
            "completion_date",
            "assessment_result",
            "certificate_status",
            "dropout_flag",
            "dropout_date",
            "dropout_reason",
            "source_referral",
            "triggers_onward_referral",
            "onward_referral",
            "recorded_by",
            "recorded_by_name",
            "is_overdue",
            "days_in_training",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "completion_status",
            "completion_date",
            "dropout_flag",
            "dropout_date",
            "dropout_reason",
            "triggers_onward_referral",
            "onward_referral",
            "recorded_by",
        ]
        extra_kwargs = {
            "case": {"required": False},
            "source_referral": {"required": False},
        }

    def validate(self, attrs):
        """The one cross-field rule §4.5 states: a TVET course names its trade.

        Repeated here rather than left to `Model.clean` alone so the API returns
        it against the field, which is what puts the message beside the input on
        the form.
        """
        training_type = attrs.get("training_type", getattr(self.instance, "training_type", None))
        trade = attrs.get("trade_or_skill_area", getattr(self.instance, "trade_or_skill_area", ""))
        if training_type == TrainingType.TVET and not trade:
            raise serializers.ValidationError({"trade_or_skill_area": "Name the trade for a TVET course."})

        source_referral = attrs.get("source_referral", getattr(self.instance, "source_referral", None))
        case = attrs.get("case", getattr(self.instance, "case", None))

        if self.instance is None:
            # The category rule has to be *here*, not only on the model:
            # `perform_create` calls `serializer.save()`, and a ModelSerializer
            # does not run `full_clean`, so a rule stated only in `Model.clean`
            # is unenforced over the API. `training_referral_error` is the one
            # definition all three write paths call.
            problem = training_referral_error(source_referral, case)
            if problem:
                field = (
                    "case"
                    if source_referral is not None and case is not None and source_referral.case_id != case.pk
                    else "source_referral"
                )
                raise serializers.ValidationError({field: str(problem)})
            # §4.2: the case is the referral's, never the client's. Making it
            # writable lets the two desynchronise.
            attrs["case"] = source_referral.case
        else:
            if "source_referral" in attrs and source_referral != self.instance.source_referral:
                raise serializers.ValidationError({"source_referral": "The source referral cannot be changed."})
            if "case" in attrs and case != self.instance.case:
                raise serializers.ValidationError(
                    {"case": "The case is derived from the source referral and cannot change."}
                )
        return attrs


class CompleteSerializer(serializers.Serializer):
    completion_date = serializers.DateField(required=False)
    assessment_result = serializers.CharField(required=False, allow_blank=True)
    certificate_status = serializers.CharField(required=False, allow_blank=True)


class DropOutSerializer(serializers.Serializer):
    # Mandatory, and the whole value of the record: a count of dropouts tells a
    # programme nothing it can act on.
    dropout_reason = serializers.CharField()
    dropout_date = serializers.DateField(required=False)


class FailAssessmentSerializer(serializers.Serializer):
    assessment_result = serializers.CharField()
    completion_date = serializers.DateField(required=False)


TRAINING_STATUS_CHOICES = CompletionStatus
