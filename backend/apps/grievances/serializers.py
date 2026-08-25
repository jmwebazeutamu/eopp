"""Grievance serializers — spec §4.10, shared by both modules.

The one thing worth reading here is `to_representation`: a restricted record is
**redacted, not omitted**. The row stays in every list so the queue can show
that the mechanism received it, and everything that could identify a survivor
or describe what happened is removed from the payload rather than merely hidden
by the screen. A client that renders whatever the API sends cannot leak what the
API never sent.
"""

from rest_framework import serializers

from . import clock, safeguarding
from .models import Grievance, GrievanceNote, Outcome


class GrievanceSerializer(serializers.ModelSerializer):
    youth_name = serializers.CharField(source="case.youth.full_name", read_only=True, default=None)
    complaint_type_display = serializers.CharField(source="get_complaint_type_display", read_only=True)
    raised_by_display = serializers.CharField(source="get_raised_by_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    tier_display = serializers.CharField(source="get_tier_display", read_only=True)
    outcome_display = serializers.CharField(source="get_outcome_display", read_only=True)
    assigned_staff_name = serializers.CharField(source="assigned_staff.full_name", read_only=True)
    partner_name = serializers.CharField(source="about_partner.partner_name", read_only=True, default=None)
    days_open = serializers.IntegerField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    is_sensitive = serializers.BooleanField(read_only=True)
    short_reference = serializers.CharField(read_only=True)
    subject_label = serializers.CharField(read_only=True)
    group_name = serializers.CharField(source="subject_group.name", read_only=True, default=None)
    person_name = serializers.CharField(source="subject_youth.full_name", read_only=True, default=None)
    # True when *this reader* is getting the redacted shape rather than the
    # record. Named for what the reader is experiencing, not for the row's flag:
    # a focal point opening her own woreda's disclosure sees `is_restricted`
    # true and `restricted` false, and the screen needs to tell them apart.
    restricted = serializers.SerializerMethodField()
    # Time remaining, not age. "3 days late" is a fact somebody has to act on;
    # "30 day(s) open" on a resolved row is a number that keeps counting after
    # anybody could have done anything about it.
    standing = serializers.SerializerMethodField()
    severity_display = serializers.CharField(source="get_severity_display", read_only=True)
    # Server-side, in the payload. The client used to infer it from
    # `case_write || group_write`, which is false for a supervisor — the role
    # that actually works a woreda's complaints — so every action was hidden on
    # a screen whose API would have accepted them.
    can_act = serializers.SerializerMethodField()

    def get_can_act(self, grievance):
        from apps.users.permissions import CanAccessGrievances

        request = self.context.get("request")
        if request is None:
            return False
        return CanAccessGrievances().has_permission(_Writing(request), None)

    def get_standing(self, grievance):
        return clock.standing(grievance)

    def get_restricted(self, grievance):
        return grievance.is_restricted and not safeguarding.may_read_content(self._reader(), grievance)

    def _reader(self):
        request = self.context.get("request")
        return getattr(request, "user", None)

    def to_representation(self, instance):
        """Redact a restricted record for anyone not named for its woreda.

        Whitelist, not blacklist. A field added to this serializer later is
        withheld by default rather than published by default, which is the only
        way round that survives somebody else editing the field list.
        """
        data = super().to_representation(instance)
        if not data.get("restricted"):
            return data
        return {key: value for key, value in data.items() if key in safeguarding.VISIBLE_WHEN_RESTRICTED}

    class Meta:
        model = Grievance
        fields = [
            "id",
            "short_reference",
            "case",
            "youth_name",
            "subject_youth",
            "person_name",
            "subject_group",
            "group_name",
            "subject_type",
            "subject_label",
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
            "status",
            "status_display",
            "tier",
            "tier_display",
            "outcome",
            "outcome_display",
            "outcome_reason",
            "parent_grievance",
            "appeal_ground",
            "pause_reason",
            "chase_date",
            "feedback_given_at",
            "feedback_method",
            "complainant_satisfied",
            "referred_to",
            "resolution_date",
            "resolution_notes",
            "referral_quality_feedback_flag",
            "severity",
            "severity_display",
            "can_act",
            "due_on",
            "standing",
            "acknowledged_at",
            "acknowledgement_method",
            "days_open",
            "is_open",
            "is_sensitive",
            "is_restricted",
            "restricted",
            "created_at",
        ]
        # The lifecycle moves through `services`, which refuses a resolution
        # with no description of what was done. `referral_quality_feedback_flag`
        # is derived from the complaint type, so a "referral delay" nobody
        # ticked still reaches the partner panel.
        # **Every one of these moves through `Grievance.transition_to`**, which
        # owns the workflow's edges and their gates. A client that could PATCH
        # `status` could close a case having told nobody anything, which is the
        # one thing the rebuild exists to make impossible.
        read_only_fields = [
            "status",
            "outcome",
            "outcome_reason",
            "parent_grievance",
            "appeal_ground",
            "pause_reason",
            "chase_date",
            "feedback_given_at",
            "feedback_method",
            "complainant_satisfied",
            "referred_to",
            "resolution_date",
            "resolution_notes",
            "referral_quality_feedback_flag",
            # Derived from the complaint type in `Model.save`. A client that
            # could set it could also clear it, and the one it would clear is
            # the one that matters.
            "is_restricted",
            "subject_type",
            # Derived in `Model.save` from the date and the severity. A client
            # that could set its own deadline could also move it.
            "due_on",
            # Moved by `services.acknowledge`, which requires saying how.
            "acknowledged_at",
            "acknowledgement_method",
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
        subject_youth = attrs.get("subject_youth", getattr(self.instance, "subject_youth", None))
        subject_group = attrs.get("subject_group", getattr(self.instance, "subject_group", None))
        named = [subject for subject in (case, subject_youth, subject_group) if subject is not None]
        if len(named) > 1:
            raise serializers.ValidationError(
                {"subject_group": "A complaint is about one record, or about none — not several."}
            )

        # A group complaint takes the group's woreda the same way a case
        # complaint takes the case's: a hand-typed one that disagrees scopes to
        # one office and reports in another.
        if subject_group is not None:
            derived = _woreda_of(subject_group)
            if derived:
                attrs["woreda"] = derived
                woreda = derived
        elif subject_youth is not None and not woreda:
            attrs["woreda"] = subject_youth.woreda
            woreda = subject_youth.woreda

        if not named and not woreda:
            # Without one the complaint is invisible to every supervisor, which
            # is the only way it reaches anybody.
            raise serializers.ValidationError(
                {"woreda": "Say which woreda this concerns, so it reaches the right office."}
            )
        return attrs


class EmptySerializer(serializers.Serializer):
    """A move that needs no facts beyond who asked for it."""


class PauseSerializer(serializers.Serializer):
    reason = serializers.CharField()
    chase_date = serializers.DateField()


class DecideSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=Outcome.choices)
    reason = serializers.CharField()
    decided_on = serializers.DateField(required=False)


class CloseSerializer(serializers.Serializer):
    method = serializers.CharField()
    # Nullable on purpose. "Told, and did not say" is a real and common answer,
    # and recording it as dissatisfaction would be as wrong as recording it as
    # agreement.
    satisfied = serializers.BooleanField(required=False, allow_null=True, default=None)


class AppealSerializer(serializers.Serializer):
    ground = serializers.CharField()


class ReferOutSerializer(serializers.Serializer):
    to = serializers.CharField()


def _woreda_of(group):
    """The woreda name a group sits in, walked up from its kebele.

    Groups carry a `Location` FK; grievances carry a woreda *name*, because most
    complaints have no group and no case to inherit a location row from. This is
    the one place the two vocabularies meet.
    """
    node = getattr(group, "kebele", None)
    while node is not None:
        if getattr(node, "level", None) == "WOREDA":
            return node.name
        node = node.parent
    return ""


class _Writing:
    """A request seen as a write, so one permission answers both questions.

    Asking `CanAccessGrievances` directly would answer about the request in
    hand — a GET — and every payload would say the reader may not act. Wrapping
    it means the rule lives in exactly one place instead of being restated here
    and drifting from it.
    """

    def __init__(self, request):
        self.user = request.user
        self.method = "POST"


class GrievanceNoteSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.full_name", read_only=True)

    class Meta:
        model = GrievanceNote
        fields = ["id", "body", "author", "author_name", "author_role", "created_at"]
        read_only_fields = ["author", "author_role"]


class AcknowledgeSerializer(serializers.Serializer):
    method = serializers.CharField()


class NoteSerializer(serializers.Serializer):
    body = serializers.CharField()
