"""Grievance — spec §4.10. Sprint 6.

The only entity in §4 whose `case_id` is **nullable**, and that is the whole
design. A grievance can be raised by an employer about the programme, by a
trainer about a partner, or by a young person who never registered — and a
complaints channel that only accepts complaints from people already on file is
not a complaints channel.

Because it can arrive with no case, it carries its own `woreda`. Scoping is by
place, not by caseload: a supervisor has to see a complaint about a partner in
her woreda whether or not it names a youth she manages.

`referral_quality_feedback_flag` (§4.10) is the one field with a second life.
It marks complaints about referral quality or timeliness, which is qualitative
evidence about a partner — the §4.11 `performance_notes` counterpart to the
quantitative failure rates the §8 dashboards compute. A partner with a good
confirmation time and six quality complaints is not a good partner, and only
this flag can say so.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class ComplaintType(models.TextChoices):
    """TODO(spec-gap): §4.10 types this as an Enum and does not enumerate it.

    These follow the categories a PSNP grievance desk already uses, plus the two
    the referral engine needs to hear about. Validate with the grievance focal
    point in Phase 1 — a category nobody uses is as much of a problem as one
    that is missing, because complaints get filed under whatever is closest.
    """

    REFERRAL_QUALITY = "REFERRAL_QUALITY", _("Referral quality or suitability")
    REFERRAL_DELAY = "REFERRAL_DELAY", _("Referral delay or no response")
    SERVICE_QUALITY = "SERVICE_QUALITY", _("Quality of the service received")
    STAFF_CONDUCT = "STAFF_CONDUCT", _("Staff conduct")
    SELECTION = "SELECTION", _("Selection or exclusion from the programme")
    PAYMENT = "PAYMENT", _("Payment, stipend or grant")
    WORKPLACE = "WORKPLACE", _("Workplace conditions or treatment")
    SAFEGUARDING = "SAFEGUARDING", _("Safeguarding or harassment")
    OTHER = "OTHER", _("Other")

    @classmethod
    def about_referrals(cls):
        """Types that are feedback about a partner's referral handling.

        Used to default `referral_quality_feedback_flag`, which the partner
        performance panel reads.
        """
        return (cls.REFERRAL_QUALITY, cls.REFERRAL_DELAY)

    @classmethod
    def sensitive(cls):
        """Types withheld from everyone who can merely see the woreda.

        Staff conduct names a person, and the person complained about may be the
        supervisor who would otherwise read it. Narrowed to the assigned staff
        member and the administrator; see `GrievanceQuerySet.visible_to`.

        **Safeguarding is no longer on this list, and that is a widening of what
        is seen and a narrowing of what is read.** Excluding the row entirely
        meant a disclosure vanished from every queue but one, so nobody could
        show that the mechanism had received it and nothing counted it. It is
        now `is_restricted` instead: the row stays, redacted to a reference, a
        date and a woreda, and its content is readable only by a named focal
        point — not by a supervisor, and not by the administrator. See
        `safeguarding.py`.
        """
        return (cls.STAFF_CONDUCT,)


class GrievanceSubjectType(models.TextChoices):
    """What, or who, the complaint is about.

    The grievance channel is shared by both programmes, and the two ask
    different questions of it: the referral engine asks "what happened to this
    young person", the WLT module asks "what happened to this savings group".
    Same shape as `referrals.SubjectType` (handoff decision D4) and for the same
    reason — one channel, several kinds of subject, typed columns rather than a
    generic foreign key.

    One difference from the referral side, and it is the important one:
    **`NONE` is a real value here.** A referral is always about somebody; a
    complaint need not be. §4.10 makes the case optional precisely so a person
    who never registered, an employer, or an anonymous caller can complain, and
    a channel that first demands to know who you are is not a channel.
    """

    NONE = "NONE", _("Not about a specific record")
    CASE = "CASE", _("Youth case")
    YOUTH = "YOUTH", _("Youth or beneficiary")
    GROUP = "GROUP", _("Savings group")


class Severity(models.TextChoices):
    """How fast this has to be answered, separate from what it is about.

    Deliberately not derived from `complaint_type`. A payment complaint from a
    woman whose family has eaten nothing for three days and a payment complaint
    about a late transport stipend are the same category and are not the same
    urgency, and only the person who took the complaint can tell them apart.
    """

    ROUTINE = "ROUTINE", _("Routine")
    SERIOUS = "SERIOUS", _("Serious")
    CRITICAL = "CRITICAL", _("Critical")


class RaisedBy(models.TextChoices):
    """Spec §4.10, verbatim: Youth / Employer / Trainer / Partner."""

    YOUTH = "YOUTH", _("Youth")
    EMPLOYER = "EMPLOYER", _("Employer")
    TRAINER = "TRAINER", _("Trainer")
    PARTNER = "PARTNER", _("Partner organisation")


class GrievanceStatus(models.TextChoices):
    """Where the work is. **Not** what was decided — that is `Outcome`.

    The four statuses this replaces conflated the two: `RESOLVED` said both
    "the file is finished" and "the complaint was upheld", so a complaint that
    was investigated and found to be unfounded had nowhere to go but `CLOSED`,
    which also meant "the complainant withdrew". The resolution rate could not
    be computed without deciding which of those two things it meant.

    Eight states, following the PSNP 5 redress chain. Two of them are the ones
    that were missing and that the mechanism is judged on: `ACKNOWLEDGED`,
    because telling somebody their complaint arrived is a separate act from
    answering it, and `DECIDED`, because a decision that has not yet been
    communicated is not a closed file.
    """

    RECEIVED = "RECEIVED", _("Received")
    ACKNOWLEDGED = "ACKNOWLEDGED", _("Acknowledged")
    UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
    AWAITING_COMPLAINANT = "AWAITING_COMPLAINANT", _("Awaiting the complainant")
    DECIDED = "DECIDED", _("Decided")
    CLOSED = "CLOSED", _("Closed")
    APPEALED = "APPEALED", _("Appealed")
    REFERRED_OUT = "REFERRED_OUT", _("Referred out")

    @classmethod
    def terminal(cls):
        """The file is shut. `APPEALED` is terminal *for this record* — the work
        continues on the child at the next tier, which has its own clock."""
        return (cls.CLOSED, cls.APPEALED, cls.REFERRED_OUT)

    @classmethod
    def open_statuses(cls):
        return (cls.RECEIVED, cls.ACKNOWLEDGED, cls.UNDER_REVIEW, cls.AWAITING_COMPLAINANT, cls.DECIDED)

    @classmethod
    def paused(cls):
        """The only pause. Any other would be a hiding place — a case parked in
        a state whose clock does not run is a case nobody is accountable for."""
        return (cls.AWAITING_COMPLAINANT,)


class Outcome(models.TextChoices):
    """What was decided, which is not the same as where the file got to.

    This is the enum §8 reporting turns on. An overturn rate at tier 1 needs to
    know that a first-tier decision said `NOT_UPHELD` and a second-tier one said
    `UPHELD` about the same complaint, and neither of those facts is expressible
    as a status.
    """

    UPHELD = "UPHELD", _("Upheld")
    PARTLY_UPHELD = "PARTLY_UPHELD", _("Partly upheld")
    NOT_UPHELD = "NOT_UPHELD", _("Not upheld")
    REFERRED = "REFERRED", _("Referred to another body")
    WITHDRAWN = "WITHDRAWN", _("Withdrawn by the complainant")

    @classmethod
    def in_the_complainant_favour(cls):
        """What an appeal overturning a decision looks like from below."""
        return (cls.UPHELD, cls.PARTLY_UPHELD)


class Tier(models.TextChoices):
    """Where in the appeals chain this case sits.

    Tiers 1 and 2 are the platform's working range: the Kebele Appeals
    Committee answers first and the Woreda Appeals Committee hears the appeal.
    Region and federal exist so a case escalated beyond the woreda can be
    *recorded* with its reference — they are not worked inside this module, and
    pretending otherwise would put a queue in front of somebody who does not use
    this system.
    """

    KEBELE = "KEBELE", _("Kebele Appeals Committee")
    WOREDA = "WOREDA", _("Woreda Appeals Committee")
    REGION = "REGION", _("Regional FSCO")
    FEDERAL = "FEDERAL", _("Federal FSCO or Ombudsman")

    @classmethod
    def above(cls, tier):
        """The tier an appeal goes to, or None at the top of the chain."""
        ladder = [cls.KEBELE, cls.WOREDA, cls.REGION, cls.FEDERAL]
        index = ladder.index(tier)
        return ladder[index + 1] if index + 1 < len(ladder) else None


class TransitionError(ValidationError):
    """An attempt to move a complaint along an edge the workflow does not have."""


class Transition:
    """One edge, with what it demands before it may be taken."""

    def __init__(self, to_status, description, requires=()):
        self.to_status = to_status
        self.description = description
        self.requires = tuple(requires)


# The workflow, transcribed. Keys are the `from` status; `transition_to`
# refuses anything absent, so an unlisted move fails loudly rather than
# silently putting a case in a state nothing knows how to handle.
#
# Read the `requires` column as the answer to "what must be true before this is
# allowed": it is where the gates live that the old screen had only as disabled
# buttons, and a disabled button is a suggestion.
TRANSITIONS = {
    GrievanceStatus.RECEIVED: [
        Transition(
            GrievanceStatus.ACKNOWLEDGED,
            _("The complainant was told it arrived and given the reference."),
            requires=("acknowledgement",),
        ),
        Transition(GrievanceStatus.REFERRED_OUT, _("Another body owns this."), requires=("referral",)),
    ],
    GrievanceStatus.ACKNOWLEDGED: [
        Transition(GrievanceStatus.UNDER_REVIEW, _("A committee or officer is working it.")),
        Transition(GrievanceStatus.REFERRED_OUT, _("Another body owns this."), requires=("referral",)),
    ],
    GrievanceStatus.UNDER_REVIEW: [
        Transition(
            GrievanceStatus.AWAITING_COMPLAINANT,
            _("The programme needs something back before it can go on."),
            requires=("pause_reason",),
        ),
        Transition(GrievanceStatus.DECIDED, _("An outcome was reached."), requires=("outcome",)),
        Transition(GrievanceStatus.REFERRED_OUT, _("Another body owns this."), requires=("referral",)),
    ],
    GrievanceStatus.AWAITING_COMPLAINANT: [
        Transition(GrievanceStatus.UNDER_REVIEW, _("The complainant answered, or the chase date passed.")),
        Transition(GrievanceStatus.REFERRED_OUT, _("Another body owns this."), requires=("referral",)),
    ],
    GrievanceStatus.DECIDED: [
        Transition(
            GrievanceStatus.CLOSED,
            _("The complainant was told the outcome."),
            requires=("feedback",),
        ),
    ],
    GrievanceStatus.CLOSED: [
        Transition(
            GrievanceStatus.APPEALED,
            _("The complainant rejected the outcome inside the appeal window."),
            requires=("appeal_window", "tier_above"),
        ),
    ],
    # Nothing leaves these. An appealed case continues as its child, and a
    # referred one is somebody else's file now.
    GrievanceStatus.APPEALED: [],
    GrievanceStatus.REFERRED_OUT: [],
}


class GrievanceQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=GrievanceStatus.open_statuses())

    def upheld(self):
        """Decided in the complainant's favour, wholly or partly.

        Replaces `resolved()`, which meant two things at once — the file is
        finished, *and* something was done about it — so a complaint properly
        investigated and found unfounded had nowhere to be counted.
        """
        return self.filter(outcome__in=Outcome.in_the_complainant_favour())

    def decided(self):
        return self.filter(outcome__isnull=False)

    def about_referral_quality(self):
        return self.filter(referral_quality_feedback_flag=True)

    def overdue(self, threshold_days, as_of=None):
        """Open past the service standard.

        A grievance process nobody answers is worse than none: it collects the
        complaint, creates the expectation, and then does nothing with it.
        """
        as_of = as_of or date.today()
        from datetime import timedelta

        return self.open().filter(date_raised__lt=as_of - timedelta(days=threshold_days))

    def late(self, as_of=None):
        """Open and past its own deadline.

        Against `due_on`, the value stamped when the complaint was raised — not
        against today's setting. A complaint raised under a 21-day rule must not
        be silently re-judged at 10, which is the same reasoning the alert
        engine's `threshold_days` records.
        """
        return self.open().filter(due_on__lt=as_of or date.today())

    def due_within(self, days, as_of=None):
        from datetime import timedelta

        as_of = as_of or date.today()
        return self.open().filter(due_on__gte=as_of, due_on__lte=as_of + timedelta(days=days))

    def awaiting_acknowledgement(self):
        """Nobody has told the complainant it arrived."""
        return self.open().filter(acknowledged_at__isnull=True)

    def visible_to(self, user):
        """Narrow to what this user may read.

        Staff-conduct complaints are visible only to the assigned staff member
        and the administrator, because the person complained about may be the
        supervisor who would otherwise read it.

        Safeguarding is **not** filtered here. Its row stays in every list its
        scope reaches and the serializer redacts it, so a queue can show that a
        disclosure was received without showing what it said. Removing the row
        instead — which this method used to do — hid the mechanism working.
        """
        from apps.users.models import Role

        if user.role == Role.SYSTEM_ADMIN:
            return self
        return self.exclude(models.Q(complaint_type__in=ComplaintType.sensitive()) & ~models.Q(assigned_staff=user))


class Grievance(BaseModel):
    """Spec §4.10. `grievance_id` is `id`, per the §4 type-translation guide."""

    # Nullable, per §4.10. The one entity in §4 that can exist without a case.
    case = models.ForeignKey(
        "cases.Case",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grievances",
        verbose_name=_("case"),
        help_text=_("Optional. A complaint may come from somebody who is not on the register."),
    )
    related_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grievances",
        verbose_name=_("related referral"),
    )
    # Set when the complaint is about a partner organisation rather than about
    # the programme. It is what lets the partner panel show complaints beside
    # the failure rates instead of only the numbers.
    about_partner = models.ForeignKey(
        "partners.Partner",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="grievances",
        verbose_name=_("about partner"),
    )

    # The two subjects the group module needs, beside the case the youth module
    # already had. Typed columns rather than a generic relation: a generic FK
    # cannot be constrained, cannot be indexed usefully, and cannot be read by
    # the admin or by a scoping filter without a join it does not know how to
    # make.
    subject_youth = models.ForeignKey(
        "youth.Youth",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grievances",
        verbose_name=_("about this person"),
        help_text=_("A beneficiary with no youth-employment case — a WLT member, for instance."),
    )
    subject_group = models.ForeignKey(
        "wlt.Group",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grievances",
        verbose_name=_("about this savings group"),
    )

    subject_type = models.GeneratedField(
        expression=models.Case(
            models.When(case__isnull=False, then=models.Value(GrievanceSubjectType.CASE)),
            models.When(subject_youth__isnull=False, then=models.Value(GrievanceSubjectType.YOUTH)),
            models.When(subject_group__isnull=False, then=models.Value(GrievanceSubjectType.GROUP)),
            default=models.Value(GrievanceSubjectType.NONE),
            output_field=models.CharField(max_length=8),
        ),
        output_field=models.CharField(max_length=8),
        db_persist=True,
        verbose_name=_("subject type"),
    )

    # Not in §4.10's field list, and required here. A grievance with no case has
    # no woreda to inherit, and without one a supervisor cannot be shown the
    # complaints from her own woreda — which is the only way this reaches anyone.
    woreda = models.CharField(_("woreda"), max_length=128, db_index=True)

    complaint_type = models.CharField(_("complaint type"), max_length=24, choices=ComplaintType.choices)
    raised_by = models.CharField(_("raised by"), max_length=16, choices=RaisedBy.choices)
    complainant_name = models.CharField(
        _("complainant"),
        max_length=255,
        blank=True,
        help_text=_("Optional. A complaint may be made anonymously and is still recorded."),
    )
    complainant_contact = models.CharField(_("contact"), max_length=64, blank=True)
    summary = models.TextField(_("what happened"))

    date_raised = models.DateField(_("date raised"), default=date.today, db_index=True)
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_grievances",
        verbose_name=_("assigned to"),
    )

    severity = models.CharField(
        _("severity"),
        max_length=8,
        choices=Severity.choices,
        default=Severity.ROUTINE,
        db_index=True,
        help_text=_("Drives the deadline. Not derived from the category — only the person who took it can judge it."),
    )

    # Derived in `save` from `date_raised` and `severity`, in working days.
    # Stored rather than computed on read so the queue can sort and filter on it
    # in the database: "show me what is late" over a scan of every row, in
    # Python, is the query that stops being run.
    due_on = models.DateField(_("due"), null=True, blank=True, db_index=True)

    # When the complainant was told it had arrived. Null is the finding: it is
    # the step most often skipped, and nothing in the record used to ask for it.
    acknowledged_at = models.DateTimeField(_("acknowledged"), null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acknowledged_grievances",
        verbose_name=_("acknowledged by"),
    )
    acknowledgement_method = models.CharField(
        _("how"),
        max_length=32,
        blank=True,
        help_text=_("In person, by phone, at a kebele meeting, through a third party."),
    )

    status = models.CharField(
        _("status"),
        max_length=24,
        choices=GrievanceStatus.choices,
        default=GrievanceStatus.RECEIVED,
        db_index=True,
    )

    # Where in the appeals chain. A complaint enters at the kebele committee
    # unless it was raised about something the kebele cannot answer.
    tier = models.CharField(_("tier"), max_length=8, choices=Tier.choices, default=Tier.KEBELE, db_index=True)
    parent_grievance = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="appeals",
        verbose_name=_("appeal against"),
        help_text=_("Set when this case is an appeal against a decision at the tier below."),
    )
    appeal_ground = models.TextField(
        _("ground of appeal"),
        blank=True,
        help_text=_("Why the complainant rejected the decision. Their words, not a summary of them."),
    )

    outcome = models.CharField(
        _("outcome"),
        max_length=16,
        choices=Outcome.choices,
        blank=True,
        db_index=True,
        help_text=_("What was decided. Distinct from the status of the record."),
    )
    outcome_reason = models.TextField(
        _("reason"),
        blank=True,
        help_text=_("In plain language, written as if the complainant will hear it read back — because they will."),
    )

    # The pause, and the only one. Any other would be a hiding place.
    pause_reason = models.CharField(_("waiting for"), max_length=255, blank=True)
    chase_date = models.DateField(_("chase on"), null=True, blank=True)
    paused_on = models.DateField(_("paused on"), null=True, blank=True)

    # Proof the complainant was told the answer, and what they said about it.
    feedback_given_at = models.DateTimeField(_("outcome communicated"), null=True, blank=True)
    feedback_method = models.CharField(_("how"), max_length=32, blank=True)
    complainant_satisfied = models.BooleanField(
        _("complainant accepted the outcome"),
        null=True,
        blank=True,
        help_text=_("Null means they were told and did not say. That is not the same as satisfied."),
    )

    referred_to = models.CharField(
        _("referred to"),
        max_length=255,
        blank=True,
        help_text=_("Which body now owns this, and their reference."),
    )
    resolution_date = models.DateField(_("resolution date"), null=True, blank=True)
    # Kept, and no longer where a decision is recorded — that is
    # `outcome_reason`. Complaints raised before the workflow existed carry
    # their only account of what happened here, so clearing it deletes history.
    resolution_notes = models.TextField(_("resolution notes"), blank=True)

    # Derived from the complaint type in `save`, never typed. A safeguarding
    # disclosure that reaches the shared queue because somebody forgot to tick a
    # box is the failure this flag exists to make impossible.
    is_restricted = models.BooleanField(
        _("restricted"),
        default=False,
        db_index=True,
        help_text=_("Safeguarding. Content is readable only by a named focal point for this woreda."),
    )

    referral_quality_feedback_flag = models.BooleanField(
        _("referral quality feedback"),
        default=False,
        db_index=True,
        help_text=_("Marks a complaint about referral quality or timeliness. Read by the partner performance panel."),
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recorded_grievances",
        verbose_name=_("recorded by"),
    )

    history = HistoricalRecords()  # §9 audit trail

    objects = GrievanceQuerySet.as_manager()

    class Meta:
        verbose_name = _("grievance")
        verbose_name_plural = _("grievances")
        ordering = ["-date_raised", "-created_at"]
        constraints = [
            # A resolution with no date cannot be timed, and time-to-resolution
            # is the only figure that says whether the channel works.
            # A conclusion with no date cannot be timed, and time-to-conclusion
            # is the figure that says whether the channel works.
            models.CheckConstraint(
                condition=~models.Q(status__in=GrievanceStatus.terminal()) | models.Q(resolution_date__isnull=False),
                name="grievance_closed_needs_date",
            ),
            # An outcome nobody explained is a status change wearing a decision's
            # clothes, and the reason is what a complainant hears read back.
            models.CheckConstraint(
                condition=models.Q(outcome="") | ~models.Q(outcome_reason=""),
                name="grievance_outcome_needs_reason",
            ),
            # **The gate the whole rebuild turns on.** A file cannot be shut
            # until there is a record that the complainant was told the answer.
            # It was possible to close a case having told nobody anything, which
            # is the step auditors check and the one most often skipped.
            models.CheckConstraint(
                condition=~models.Q(status=GrievanceStatus.CLOSED) | models.Q(feedback_given_at__isnull=False),
                name="grievance_closed_needs_feedback",
            ),
            # A child record is an appeal, and an appeal is against something.
            # Expressed as a constraint rather than left to the service, because
            # the overturn rate — the number that shows the second tier is
            # independent — is uncomputable the moment one of these is orphaned.
            models.CheckConstraint(
                condition=models.Q(appeal_ground="") | models.Q(parent_grievance__isnull=False),
                name="grievance_appeal_needs_a_parent",
            ),
            # **At most** one, not exactly one — the referral side's constraint
            # with the zero case allowed. A complaint about the programme as a
            # whole, or one whose complainant will not say who they are, names
            # no subject and must still be recordable.
            models.CheckConstraint(
                condition=(
                    models.Q(case__isnull=True, subject_youth__isnull=True, subject_group__isnull=True)
                    | models.Q(case__isnull=False, subject_youth__isnull=True, subject_group__isnull=True)
                    | models.Q(case__isnull=True, subject_youth__isnull=False, subject_group__isnull=True)
                    | models.Q(case__isnull=True, subject_youth__isnull=True, subject_group__isnull=False)
                ),
                name="grievance_at_most_one_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "date_raised"]),
            models.Index(fields=["woreda", "status"]),
            models.Index(fields=["tier", "status"]),
            # A partial index per non-case subject, so a group's complaint
            # history is a lookup rather than a scan of a table that is
            # overwhelmingly youth-side. Same reasoning as the referral indexes.
            models.Index(
                fields=["subject_group"],
                condition=models.Q(subject_group__isnull=False),
                name="grievance_subject_group_idx",
            ),
            models.Index(
                fields=["subject_youth"],
                condition=models.Q(subject_youth__isnull=False),
                name="grievance_subject_youth_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_complaint_type_display()} ({self.get_status_display()})"

    @property
    def is_open(self):
        return self.status in GrievanceStatus.open_statuses()

    @property
    def days_open(self):
        return ((self.resolution_date or date.today()) - self.date_raised).days

    @property
    def is_sensitive(self):
        return self.complaint_type in ComplaintType.sensitive()

    def clean(self):
        errors = {}

        if self.date_raised and self.date_raised > date.today():
            errors["date_raised"] = _("A complaint cannot be raised in the future.")

        if self.status in GrievanceStatus.terminal() and not self.resolution_date:
            errors["resolution_date"] = _("Record the date this was concluded.")
        if self.outcome and not self.outcome_reason:
            errors["outcome_reason"] = _("Say why, in words the complainant will hear read back.")

        if self.parent_grievance_id and self.parent_grievance_id == self.pk:
            errors["parent_grievance"] = _("A complaint cannot be an appeal against itself.")

        if self.resolution_date and self.resolution_date < self.date_raised:
            errors["resolution_date"] = _("A complaint cannot be resolved before it was raised.")

        named = [bool(self.case_id), bool(self.subject_youth_id), bool(self.subject_group_id)]
        if sum(named) > 1:
            errors["subject_group"] = _("A complaint is about one record, or about none.")

        if self.case_id and self.related_referral_id and self.related_referral.case_id != self.case_id:
            errors["related_referral"] = _("That referral belongs to a different case.")

        if errors:
            raise ValidationError(errors)

    def allowed_transitions(self):
        return TRANSITIONS.get(self.status, [])

    def transition_to(self, status, *, actor=None, **facts):
        """Move this complaint, or refuse and say which edge is missing.

        **The only supported way to change `status`** — the serializer marks the
        field read-only for that reason, exactly as the referral engine does with
        §6.2. Every gate the old screen expressed as a disabled button lives
        here instead, because a disabled button is a suggestion and this is a
        record somebody is accountable for.

        The row is re-read under `select_for_update` before the check: two
        officers deciding the same case at the same moment would otherwise both
        pass a check made against a stale copy, and the second would overwrite
        the first's outcome with no trace but the history table.
        """
        from django.db import transaction

        with transaction.atomic():
            current = Grievance.objects.select_for_update().get(pk=self.pk)
            edge = next((t for t in TRANSITIONS.get(current.status, []) if t.to_status == status), None)
            if edge is None:
                raise TransitionError(
                    _("A complaint that is %(from)s cannot become %(to)s.")
                    % {"from": current.get_status_display(), "to": GrievanceStatus(status).label}
                )
            for requirement in edge.requires:
                problem = _REQUIREMENTS[requirement](current, facts)
                if problem:
                    raise TransitionError(problem)

            self.status = status
            return current

    def days_since_closed(self, as_of=None):
        """How long the appeal window has been running, in calendar days.

        Calendar rather than working days: the window is time the complainant
        has to think, not time the programme is working, and counting it in
        working days would quietly lengthen it over every holiday.
        """
        if not self.resolution_date:
            return None
        return ((as_of or date.today()) - self.resolution_date).days

    def save(self, *args, **kwargs):
        """Derive the referral-quality flag and the woreda where they follow.

        The flag defaults from the complaint type rather than being remembered
        separately, because a "referral delay" complaint that nobody ticked would
        never reach the partner panel — and the panel is the only place the
        complaint changes anything.
        """
        if self.complaint_type in ComplaintType.about_referrals():
            self.referral_quality_feedback_flag = True
        # Derived, never typed: a safeguarding disclosure that reached the shared
        # queue because somebody left a box unticked is the whole failure mode.
        self.is_restricted = self.complaint_type == ComplaintType.SAFEGUARDING
        # Derived from the date and the severity — but **not on every save**.
        #
        # It used to be, which silently undid `services.resume`: that pushes the
        # deadline forward by however long the programme waited on the
        # complainant, and the next save recomputed it back to the original.
        # A deliberate adjustment has to survive a save that was not about the
        # deadline.
        #
        # So: computed when the record is new or has none, and recomputed only
        # when the two things it derives from are themselves being written.
        # Raising the severity of a complaint that turns out worse than it
        # looked still moves its deadline with it — that is a full save.
        update_fields = kwargs.get("update_fields")
        touches_basis = update_fields is None or {"severity", "date_raised"} & set(update_fields)
        if self.date_raised and (self.due_on is None or touches_basis):
            from . import clock

            self.due_on = clock.due_on(raised_on=self.date_raised, severity=self.severity)
        if not self.woreda:
            if self.case_id:
                self.woreda = self.case.woreda
            elif self.subject_youth_id:
                self.woreda = self.subject_youth.woreda
        return super().save(*args, **kwargs)

    @property
    def short_reference(self):
        """What a complainant is told to quote, for now.

        The printed reference the design asks for — `OR-EShewa-Lume-2018-0043`,
        drawn from a per-kebele block allocated in advance so a receipt written
        where there is no signal still matches — is its own piece of work and is
        not built. This is the stable part of the row's own id, which is enough
        for a restricted row to be referred to on screen without naming anybody.
        """
        return str(self.pk).replace("-", "")[:8].upper()

    def subject_label(self):
        """Who or what this is about, in one line, for a screen or the admin."""
        if self.case_id:
            return self.case.youth.full_name
        if self.subject_youth_id:
            return self.subject_youth.full_name
        if self.subject_group_id:
            return self.subject_group.name
        return ""


class SafeguardingFocalPoint(BaseModel):
    """Who may read a safeguarding disclosure in a given woreda.

    **A named list, deliberately not a role.** A role is inherited: create a new
    administrator, or add somebody to a group that happens to carry the right
    permission, and they silently acquire the ability to read a survivor's
    account of what happened to her. Naming the people means the list can be
    read out loud in a meeting, and adding to it is a decision somebody makes
    rather than a side effect of an account being provisioned.

    Dated rather than flagged, like every other appointment in this platform: a
    focal point who leaves in April must not be able to read March's disclosure
    in May, and an `is_active` boolean drifts from the dates within a month.
    """

    woreda = models.CharField(_("woreda"), max_length=128, db_index=True)
    person = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="safeguarding_woredas",
        verbose_name=_("focal point"),
    )
    from_date = models.DateField(_("from"), default=date.today)
    to_date = models.DateField(_("until"), null=True, blank=True)
    # The safeguarding lead reads the access log; she is not thereby a reader of
    # the disclosures themselves, which is why this is a separate flag.
    is_lead = models.BooleanField(
        _("safeguarding lead"),
        default=False,
        help_text=_("Reads the access log for this woreda. Does not by itself grant access to content."),
    )
    note = models.CharField(_("note"), max_length=255, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("safeguarding focal point")
        verbose_name_plural = _("safeguarding focal points")
        ordering = ["woreda", "-from_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_date__isnull=True) | models.Q(to_date__gte=models.F("from_date")),
                name="focal_point_period_valid",
            ),
        ]
        indexes = [models.Index(fields=["woreda", "from_date"])]

    def __str__(self):
        return f"{self.person} — {self.woreda}"

    def covers(self, on_date=None):
        on_date = on_date or date.today()
        return self.from_date <= on_date and (self.to_date is None or on_date <= self.to_date)


class GrievanceAccess(BaseModel):
    """Every time somebody opened a restricted record.

    Access to a safeguarding disclosure is an **event**, not a state. The
    question the safeguarding lead has to be able to answer is not "who is
    allowed to read this" — that is the focal point list — but "who did", and
    that has no answer unless each opening is written down as it happens.

    Append-only. There is no route that edits or deletes one, and there should
    not be: a log a reader can tidy is not a log.

    The screen says this is happening. A control that watches people silently
    is a different thing from one that tells them it is watching, and only the
    second changes behaviour.
    """

    grievance = models.ForeignKey(
        Grievance,
        on_delete=models.CASCADE,
        related_name="accesses",
        verbose_name=_("grievance"),
    )
    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grievance_accesses",
        verbose_name=_("read by"),
    )
    # Recorded rather than derived at read time: the role is what the log is
    # read for, and a person's role can change after the fact.
    role = models.CharField(_("role at the time"), max_length=32)
    granted = models.BooleanField(
        _("granted"),
        default=True,
        help_text=_("False records a refused attempt, which is the more interesting row."),
    )

    class Meta:
        verbose_name = _("restricted record access")
        verbose_name_plural = _("restricted record accesses")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["grievance", "-created_at"])]

    def __str__(self):
        return f"{self.reader} → {self.grievance_id}"


class GrievanceNote(BaseModel):
    """Something somebody did or found out, appended to the case file.

    **Append-only through the API — no PATCH, no DELETE.** Same rule as the
    contact log, and for the same reason: a note that can be edited afterwards
    is not evidence of anything. A correction is another note that says what was
    corrected, which also records that somebody thought the first one was wrong.

    The original complaint is *not* a note. It is `Grievance.summary`, and it is
    read-only after creation — the statement a complainant gave is the one thing
    on the record that nobody may improve.
    """

    grievance = models.ForeignKey(
        Grievance,
        on_delete=models.CASCADE,
        related_name="notes",
        verbose_name=_("grievance"),
    )
    body = models.TextField(_("note"))
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="grievance_notes",
        verbose_name=_("written by"),
    )
    # Recorded rather than derived at read time: the role is what the file is
    # read for, and a person's role can change after the fact.
    author_role = models.CharField(_("role at the time"), max_length=32, blank=True)

    class Meta:
        verbose_name = _("case note")
        verbose_name_plural = _("case notes")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["grievance", "created_at"])]

    def __str__(self):
        return f"{self.author} — {self.grievance_id}"


def _needs_acknowledgement(grievance, facts):
    if not grievance.acknowledged_at:
        return _("Record how the complainant was told it arrived before moving this on.")
    return None


def _needs_outcome(grievance, facts):
    if not facts.get("outcome"):
        return _("Choose what was decided — upheld, partly upheld, not upheld, referred or withdrawn.")
    if not (facts.get("outcome_reason") or "").strip():
        return _("Say why, in words the complainant will hear read back.")
    return None


def _needs_feedback(grievance, facts):
    """The gate the rebuild turns on.

    A decision the complainant has not heard is not a closed file. This was
    possible before — a case could be closed having told nobody anything — and
    it is the step auditors check.
    """
    if not (facts.get("feedback_method") or "").strip():
        return _("Say how the complainant was told the outcome before shutting the file.")
    return None


def _needs_pause_reason(grievance, facts):
    if not (facts.get("pause_reason") or "").strip():
        return _("Say what the programme is waiting for. A pause with no reason is a hiding place.")
    if not facts.get("chase_date"):
        return _("Set a date to chase. A pause with no end is a case nobody comes back to.")
    return None


def _needs_referral(grievance, facts):
    if not (facts.get("referred_to") or "").strip():
        return _("Name the body that now owns this, and their reference.")
    return None


def _inside_appeal_window(grievance, facts):
    from django.conf import settings

    elapsed = grievance.days_since_closed()
    window = settings.GRIEVANCE_APPEAL_WINDOW_DAYS
    if elapsed is not None and elapsed > window:
        return _("The %(days)s-day appeal window closed on this decision.") % {"days": window}
    if not (facts.get("appeal_ground") or "").strip():
        return _("Record the ground of appeal — the complainant's words, not a summary of them.")
    return None


def _has_a_tier_above(grievance, facts):
    if Tier.above(grievance.tier) is None:
        return _("This is already at the top of the chain the platform records. Refer it out instead.")
    return None


#: Named rather than inlined, so the workflow table above reads as a table.
_REQUIREMENTS = {
    "acknowledgement": _needs_acknowledgement,
    "outcome": _needs_outcome,
    "feedback": _needs_feedback,
    "pause_reason": _needs_pause_reason,
    "referral": _needs_referral,
    "appeal_window": _inside_appeal_window,
    "tier_above": _has_a_tier_above,
}
