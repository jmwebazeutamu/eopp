"""Serializers for Case (spec §4.2)."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.users.models import Role, User
from apps.youth.serializers import YouthSummarySerializer

from .models import Case, CaseAction, CaseActionStatus, CaseActionType, Pathway, PathwayAssignment, ProfilingRecord


class CaseListSerializer(serializers.ModelSerializer):
    """Row shape for the case manager's case list (spec §10 Sprint 1)."""

    youth = YouthSummarySerializer(read_only=True)
    case_status_display = serializers.CharField(source="get_case_status_display", read_only=True)
    case_manager_name = serializers.CharField(source="case_manager.full_name", read_only=True)
    days_since_activity = serializers.IntegerField(read_only=True)
    is_stalled_by_threshold = serializers.BooleanField(read_only=True)

    class Meta:
        model = Case
        fields = [
            "id",
            "youth",
            "case_status",
            "case_status_display",
            "case_manager",
            "case_manager_name",
            "woreda",
            "opened_date",
            "last_activity_date",
            "days_since_activity",
            "is_stalled_by_threshold",
            "next_action",
        ]
        read_only_fields = fields


class CaseSerializer(serializers.ModelSerializer):
    """Full case record for the detail screen."""

    youth_detail = YouthSummarySerializer(source="youth", read_only=True)
    case_status_display = serializers.CharField(source="get_case_status_display", read_only=True)
    case_manager_name = serializers.CharField(source="case_manager.full_name", read_only=True)
    next_action_owner_name = serializers.CharField(source="next_action_owner.full_name", read_only=True, default=None)
    days_since_activity = serializers.IntegerField(read_only=True)
    is_stalled_by_threshold = serializers.BooleanField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    # SerializerMethodFields rather than nested serializers: those classes are
    # defined further down this module, so referencing them here would be a
    # forward reference at class-creation time.
    current_pathway = serializers.SerializerMethodField()
    current_profiling = serializers.SerializerMethodField()
    recent_actions = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            "id",
            "youth",
            "youth_detail",
            "current_pathway",
            "current_profiling",
            "case_status",
            "case_status_display",
            "case_manager",
            "case_manager_name",
            "woreda",
            "opened_date",
            "closed_date",
            "exit_reason",
            "last_activity_date",
            "days_since_activity",
            "is_stalled_by_threshold",
            "is_open",
            "next_action",
            "next_action_owner",
            "next_action_owner_name",
            "recent_actions",
            "created_at",
            "updated_at",
        ]
        # `woreda` is denormalised from Youth by Case.save — accepting it from a
        # client would let the two disagree.
        read_only_fields = ["id", "woreda", "last_activity_date", "created_at", "updated_at"]

    def get_current_pathway(self, obj):
        assignment = obj.pathway_assignments.current().first()
        return PathwayAssignmentSerializer(assignment).data if assignment else None

    def get_current_profiling(self, obj):
        record = obj.current_profiling
        return ProfilingRecordSerializer(record).data if record else None

    def get_recent_actions(self, obj):
        actions = obj.actions.select_related("created_by", "assigned_to").all()[:10]
        return CaseActionSerializer(actions, many=True).data

    def validate_case_manager(self, value):
        if value.role != Role.CASE_MANAGER:
            raise serializers.ValidationError(
                f"{value.full_name} holds the {value.get_role_display()} role and cannot own a caseload."
            )
        if not value.is_operational:
            raise serializers.ValidationError(f"{value.full_name}'s account is not active.")
        return value

    def validate_youth(self, value):
        # OneToOne already guarantees this at the database level; catching it
        # here turns a 500 into a usable field error.
        existing = Case.objects.filter(youth=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError(f"{value.full_name} already has a case.")
        return value

    def validate(self, attrs):
        candidate = self.instance or Case()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        # Mirror the denormalisation so clean() sees what save() will write.
        if candidate.youth_id:
            candidate.woreda = candidate.youth.woreda
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class CaseAssignmentSerializer(serializers.Serializer):
    """Reassign a case to a different case manager."""

    case_manager = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Recorded in the audit history (spec §9 requires a rationale on status changes).",
    )

    def validate_case_manager(self, value):
        if value.role != Role.CASE_MANAGER:
            raise serializers.ValidationError(f"{value.full_name} cannot own a caseload.")
        if not value.is_operational:
            raise serializers.ValidationError(f"{value.full_name}'s account is not active.")
        return value


class CaseActionSerializer(serializers.ModelSerializer):
    """Append-only notes and tasks hanging off a case."""

    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, default=None)
    action_type_display = serializers.CharField(source="get_action_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = CaseAction
        fields = [
            "id",
            "case",
            "action_type",
            "action_type_display",
            "body",
            "created_by",
            "created_by_name",
            "assigned_to",
            "assigned_to_name",
            "status",
            "status_display",
            "due_date",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_by_name", "resolved_at", "created_at", "updated_at"]

    def validate_assigned_to(self, value):
        if value and not value.is_operational:
            raise serializers.ValidationError(f"{value.full_name}'s account is not active.")
        return value

    def validate(self, attrs):
        candidate = self.instance or CaseAction()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        if not candidate.body.strip():
            raise serializers.ValidationError({"body": "This field may not be blank."})
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["created_by"] = request.user
        if (
            validated_data["action_type"] == CaseActionType.NEXT_ACTION
            and validated_data.get("status", CaseActionStatus.OPEN) == CaseActionStatus.OPEN
        ):
            CaseAction.objects.filter(
                case=validated_data["case"],
                action_type=CaseActionType.NEXT_ACTION,
                status=CaseActionStatus.OPEN,
            ).update(status=CaseActionStatus.SUPERSEDED)
        action = super().create(validated_data)
        CaseAction.sync_case_summary(action.case)
        action.case.touch()
        return action


class ProfilingRecordSerializer(serializers.ModelSerializer):
    """Profiling and Eligibility Record — spec §4.3."""

    assessor_name = serializers.CharField(source="assessor.full_name", read_only=True)
    eligibility_flags_display = serializers.SerializerMethodField()

    class Meta:
        model = ProfilingRecord
        fields = [
            "id",
            "case",
            "work_history_summary",
            "skills_list",
            "vulnerability_index_score",
            "eligibility_flags",
            "eligibility_flags_display",
            "priority_flag",
            "assessed_date",
            "assessor",
            "assessor_name",
            "created_at",
            "updated_at",
        ]
        # The assessor is whoever is logged in — an accountability record, as
        # with Youth.registering_worker (§4.1).
        read_only_fields = ["id", "assessor", "created_at", "updated_at"]

    def get_eligibility_flags_display(self, obj):
        labels = dict(Pathway.choices)
        return [labels.get(flag, flag) for flag in obj.eligibility_flags]

    def validate(self, attrs):
        candidate = self.instance or ProfilingRecord()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["assessor"] = request.user
        record = super().create(validated_data)
        record.case.touch()
        return record


class PathwayAssignmentSerializer(serializers.ModelSerializer):
    """Pathway Assignment — spec §4.4."""

    assessor_name = serializers.CharField(source="assessor.full_name", read_only=True)
    selected_pathway_display = serializers.CharField(source="get_selected_pathway_display", read_only=True)

    class Meta:
        model = PathwayAssignment
        fields = [
            "id",
            "case",
            "assessed_interests",
            "capacities",
            "barriers",
            "selected_pathway",
            "selected_pathway_display",
            "assessment_date",
            "assessor",
            "assessor_name",
            "is_current",
            "superseded_by",
            "revision_reason",
            "created_at",
            "updated_at",
        ]
        # is_current and superseded_by are maintained by revise(); a client
        # setting them directly could produce two current pathways for one case.
        read_only_fields = [
            "id",
            "assessor",
            "is_current",
            "superseded_by",
            "revision_reason",
            "created_at",
            "updated_at",
        ]

    def validate_case(self, value):
        if value.pathway_assignments.current().exists():
            raise serializers.ValidationError(
                "This case already has a current pathway. Use the revise endpoint to change it."
            )
        return value

    def validate(self, attrs):
        candidate = self.instance or PathwayAssignment()
        for key, value in attrs.items():
            setattr(candidate, key, value)
        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data["assessor"] = request.user
        assignment = super().create(validated_data)
        # §4.2 keeps a pointer to the current pathway on the Case.
        assignment.case.current_pathway_assignment = assignment
        assignment.case.save(update_fields=["current_pathway_assignment", "updated_at"])
        assignment.case.touch()
        return assignment


class PathwayRevisionSerializer(serializers.Serializer):
    """Payload for revising a pathway (spec §4.4 `revision_reason`)."""

    selected_pathway = serializers.ChoiceField(choices=Pathway.choices)
    revision_reason = serializers.CharField(
        help_text="Why the pathway changed. Required — §9 wants a rationale on every such change."
    )
    assessed_interests = serializers.CharField(required=False, allow_blank=True)
    capacities = serializers.CharField(required=False, allow_blank=True)
    barriers = serializers.CharField(required=False, allow_blank=True)
