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


class RaisedBy(models.TextChoices):
    """Spec §4.10, verbatim: Youth / Employer / Trainer / Partner."""

    YOUTH = "YOUTH", _("Youth")
    EMPLOYER = "EMPLOYER", _("Employer")
    TRAINER = "TRAINER", _("Trainer")
    PARTNER = "PARTNER", _("Partner organisation")


class ResolutionStatus(models.TextChoices):
    """Spec §4.10, verbatim: Open / In Progress / Resolved / Closed.

    `RESOLVED` and `CLOSED` are not the same and the spec is right to separate
    them: resolved means something was done about it, closed means the file is
    shut — which also happens when a complainant withdraws or cannot be traced.
    Reporting them as one number would inflate the resolution rate with every
    complaint nobody could pursue.
    """

    OPEN = "OPEN", _("Open")
    IN_PROGRESS = "IN_PROGRESS", _("In progress")
    RESOLVED = "RESOLVED", _("Resolved")
    CLOSED = "CLOSED", _("Closed without resolution")

    @classmethod
    def terminal(cls):
        return (cls.RESOLVED, cls.CLOSED)

    @classmethod
    def open_statuses(cls):
        return (cls.OPEN, cls.IN_PROGRESS)


class GrievanceQuerySet(models.QuerySet):
    def open(self):
        return self.filter(resolution_status__in=ResolutionStatus.open_statuses())

    def resolved(self):
        return self.filter(resolution_status=ResolutionStatus.RESOLVED)

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

    resolution_status = models.CharField(
        _("status"),
        max_length=16,
        choices=ResolutionStatus.choices,
        default=ResolutionStatus.OPEN,
        db_index=True,
    )
    resolution_date = models.DateField(_("resolution date"), null=True, blank=True)
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
            models.CheckConstraint(
                condition=~models.Q(resolution_status__in=ResolutionStatus.terminal())
                | models.Q(resolution_date__isnull=False),
                name="grievance_closed_needs_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(resolution_status=ResolutionStatus.RESOLVED) | ~models.Q(resolution_notes=""),
                name="grievance_resolved_needs_notes",
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
            models.Index(fields=["resolution_status", "date_raised"]),
            models.Index(fields=["woreda", "resolution_status"]),
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
        return f"{self.get_complaint_type_display()} ({self.get_resolution_status_display()})"

    @property
    def is_open(self):
        return self.resolution_status in ResolutionStatus.open_statuses()

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

        if self.resolution_status in ResolutionStatus.terminal():
            if not self.resolution_date:
                errors["resolution_date"] = _("Record the date this was concluded.")
            if self.resolution_status == ResolutionStatus.RESOLVED and not self.resolution_notes:
                errors["resolution_notes"] = _("Say what was done about it.")

        if self.resolution_date and self.resolution_date < self.date_raised:
            errors["resolution_date"] = _("A complaint cannot be resolved before it was raised.")

        named = [bool(self.case_id), bool(self.subject_youth_id), bool(self.subject_group_id)]
        if sum(named) > 1:
            errors["subject_group"] = _("A complaint is about one record, or about none.")

        if self.case_id and self.related_referral_id and self.related_referral.case_id != self.case_id:
            errors["related_referral"] = _("That referral belongs to a different case.")

        if errors:
            raise ValidationError(errors)

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
