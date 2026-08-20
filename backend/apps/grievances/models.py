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
        """Types that must not be readable by everyone who can see a woreda.

        Safeguarding and staff conduct complaints name people, and the person
        complained about may be the supervisor who would otherwise read it.
        Narrowed to the assigned staff member and the administrator; see
        `GrievanceQuerySet.visible_to`.
        """
        return (cls.SAFEGUARDING, cls.STAFF_CONDUCT)


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

        Sensitive types — safeguarding and staff conduct — are visible only to
        the assigned staff member and the administrator, because the person
        complained about may be the supervisor who would otherwise read it. Every
        other type follows the normal woreda scope, which the viewset applies.
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
        ]
        indexes = [
            models.Index(fields=["resolution_status", "date_raised"]),
            models.Index(fields=["woreda", "resolution_status"]),
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
        if not self.woreda and self.case_id:
            self.woreda = self.case.woreda
        return super().save(*args, **kwargs)
