"""Training Enrolment — spec §4.5. Sprint 5.

One table for both training types the programme runs — Life Skills and
Employability, and Technical and Vocational — distinguished by `training_type`,
exactly as §4.5 specifies. They share every field that matters (a provider, a
window, an attendance rate, a completion status) and differ only in whether a
trade is named, so two tables would have been the same table twice.

Two things this entity owes the rest of the platform:

* **`triggers_onward_referral`.** §4.5 marks it System-set: true on completion,
  and it drives the onward-referral prompt. Completing a course is the moment a
  youth is ready for the next step, and the §6.2 prompt machinery is what makes
  somebody act on it.
* **The training-completion rate**, which the §8.3 donor tier has been reporting
  as unavailable since the dashboards were built. It becomes measurable the
  moment there are rows here.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


def training_referral_error(referral, case):
    """Why `referral` may not open a training enrolment on `case` — or None.

    **The single definition of the rule**, because there are three write paths
    into a training enrolment and they must not disagree: the service, the
    serializer, and `TrainingEnrolment.clean` (which the admin and any data fix
    reach). The serializer is the one that matters most — `perform_create` calls
    `serializer.save()`, and a `ModelSerializer` does not run `full_clean`, so a
    rule stated only on the model is not enforced over the API at all.

    Which categories qualify is a **flag on the category row**, not a list of
    codes here. §9 makes the taxonomy the administrator's to extend, and the
    `("TRAINING",)` tuple this replaced meant a category she added could not
    open an enrolment, with no way to change it short of a deploy.
    """
    if referral is None:
        return _("Create a training enrolment from a training referral.")
    if referral.case_id is None:
        return _("This referral is not attached to a youth case.")
    if case is not None and referral.case_id != getattr(case, "pk", case):
        return _("That referral belongs to a different case.")
    if not referral.referral_category.creates_training_enrolment:
        return _("A %(category)s referral does not open a training enrolment.") % {
            "category": referral.referral_category.label.lower()
        }
    return None


class TrainingType(models.TextChoices):
    """Spec §4.5: 'Life Skills/Employability / TVET'."""

    LIFE_SKILLS = "LIFE_SKILLS", _("Life skills and employability")
    TVET = "TVET", _("Technical and vocational (TVET)")


class CompletionStatus(models.TextChoices):
    """Spec §4.5, verbatim: Enrolled / Completed / Dropped Out / Failed Assessment.

    `FAILED_ASSESSMENT` is deliberately separate from `DROPPED_OUT`: a youth who
    sat the assessment and did not pass attended the course, and counting her as
    a dropout would both understate attendance and hide an assessment problem
    that belongs to the provider rather than to her.
    """

    ENROLLED = "ENROLLED", _("Enrolled")
    COMPLETED = "COMPLETED", _("Completed")
    DROPPED_OUT = "DROPPED_OUT", _("Dropped out")
    FAILED_ASSESSMENT = "FAILED_ASSESSMENT", _("Failed assessment")

    @classmethod
    def terminal(cls):
        return (cls.COMPLETED, cls.DROPPED_OUT, cls.FAILED_ASSESSMENT)

    @classmethod
    def finished_the_course(cls):
        """Attended to the end, whatever the assessment said.

        The denominator for an attendance conversation, and **not** the
        numerator for the completion rate — that is `COMPLETED` alone.
        """
        return (cls.COMPLETED, cls.FAILED_ASSESSMENT)


class CertificateStatus(models.TextChoices):
    """TODO(spec-gap): §4.5 types this as an Enum and does not enumerate it.

    These follow the TVET certification sequence. Confirm with the training
    providers in Phase 1 — a certificate that exists but has not been collected
    is a real and common state, and it is the one a youth needs for a job
    application.
    """

    NOT_APPLICABLE = "NOT_APPLICABLE", _("Not applicable")
    PENDING = "PENDING", _("Pending")
    AWARDED = "AWARDED", _("Awarded")
    COLLECTED = "COLLECTED", _("Collected by the youth")
    WITHHELD = "WITHHELD", _("Withheld")


class TrainingEnrolmentQuerySet(models.QuerySet):
    def open(self):
        return self.filter(completion_status=CompletionStatus.ENROLLED)

    def completed(self):
        """**The** definition of a completed training. Nothing else may restate it.

        Deliberately not "finished the course": a failed assessment is not a
        completion, and the §8.3 training-completion rate is the share who came
        out with the qualification the course exists to give.
        """
        return self.filter(completion_status=CompletionStatus.COMPLETED)

    def dropped_out(self):
        return self.filter(completion_status=CompletionStatus.DROPPED_OUT)

    def concluded(self):
        """Enrolments that have reached an end, of any kind.

        The denominator for the completion rate. An enrolment still running is
        neither a completion nor a failure, and counting it as either would make
        the rate move every time a new cohort starts.
        """
        return self.filter(completion_status__in=CompletionStatus.terminal())

    def awaiting_onward_prompt(self):
        """Completed trainings that have not yet produced an onward referral.

        The training-side counterpart of `Referral.objects.awaiting_onward_prompt`,
        for enrolments that reference no source referral. Where one *does* exist
        the referral's own prompt covers it, so this excludes them rather than
        raising the same prompt twice.

        **Now a legacy sweep, and deliberately kept as one.** Since §4.5
        enrolments are created from a referral, no new row can land here — the
        set drains to zero as the enrolments recorded before that rule finish.
        It is not deleted, because those rows are still valid (the referral
        check runs on add) and a youth who completed a directly-recorded course
        must still be offered a next step. Expect it to raise nothing on a
        database seeded after 2026-08-20.
        """
        return self.completed().filter(source_referral__isnull=True, onward_referral__isnull=True)


class TrainingEnrolment(BaseModel):
    """Spec §4.5. `training_id` is `id`, per the §4 type-translation guide."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="training_enrolments",
        verbose_name=_("case"),
    )

    training_type = models.CharField(_("training type"), max_length=16, choices=TrainingType.choices, db_index=True)
    trade_or_skill_area = models.CharField(
        _("trade or skill area"),
        max_length=128,
        blank=True,
        help_text=_("TVET only — the trade the course teaches."),
    )
    training_provider = models.ForeignKey(
        "partners.Partner",
        on_delete=models.PROTECT,
        related_name="training_enrolments",
        verbose_name=_("training provider"),
    )

    enrolment_date = models.DateField(_("enrolment date"), default=date.today, db_index=True)
    start_date = models.DateField(_("start date"))
    end_date = models.DateField(_("end date"), help_text=_("Scheduled end. The actual end is the completion date."))

    attendance_rate = models.DecimalField(
        _("attendance rate (%)"),
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text=_("Share of sessions attended, where the provider records it."),
    )

    completion_status = models.CharField(
        _("completion status"),
        max_length=24,
        choices=CompletionStatus.choices,
        default=CompletionStatus.ENROLLED,
        db_index=True,
    )
    completion_date = models.DateField(_("completion date"), null=True, blank=True, db_index=True)
    assessment_result = models.CharField(_("assessment result"), max_length=255, blank=True)
    certificate_status = models.CharField(
        _("certificate status"),
        max_length=24,
        choices=CertificateStatus.choices,
        default=CertificateStatus.NOT_APPLICABLE,
        blank=True,
    )

    # §4.5 carries the dropout flag beside the status. It is derived, not
    # entered: a flag a person can set independently of the status is a flag
    # that will disagree with it. `save` keeps the two together.
    dropout_flag = models.BooleanField(_("dropped out"), default=False, editable=False)
    dropout_date = models.DateField(_("dropout date"), null=True, blank=True)
    dropout_reason = models.TextField(_("dropout reason"), blank=True)

    source_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="training_enrolments",
        verbose_name=_("source referral"),
        help_text=_("The referral that placed the youth into this training, where one did."),
    )
    # Set true on completion (§4.5, System-set). Read by the alert job that
    # materialises the onward prompt; kept as a stored field rather than a pure
    # queryset because §4.5 names it, and because it records that the condition
    # *was* true even after an onward referral clears the prompt.
    triggers_onward_referral = models.BooleanField(_("triggers an onward referral"), default=False, editable=False)
    onward_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="preceding_training",
        verbose_name=_("onward referral"),
        help_text=_("The referral raised after this training completed, once a case manager confirms the prompt."),
    )

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_training_enrolments",
        verbose_name=_("recorded by"),
        help_text=_("The trainer or case manager who entered this record. Scopes a trainer's own caseload."),
    )
    notes = models.TextField(_("notes"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = TrainingEnrolmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("training enrolment")
        verbose_name_plural = _("training enrolments")
        ordering = ["-enrolment_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="training_end_after_start",
            ),
            # A completion with no date cannot be placed in a quarter, and the
            # §8.3 completion rate is quarterly.
            models.CheckConstraint(
                condition=~models.Q(completion_status=CompletionStatus.COMPLETED)
                | models.Q(completion_date__isnull=False),
                name="training_completed_needs_date",
            ),
            models.CheckConstraint(
                condition=~models.Q(completion_status=CompletionStatus.DROPPED_OUT)
                | models.Q(dropout_date__isnull=False),
                name="training_dropout_needs_date",
            ),
            models.CheckConstraint(
                condition=models.Q(attendance_rate__isnull=True)
                | models.Q(attendance_rate__gte=0, attendance_rate__lte=100),
                name="training_attendance_rate_range",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-enrolment_date"]),
            models.Index(fields=["completion_status", "training_type"]),
            models.Index(fields=["training_provider", "completion_status"]),
        ]

    def __str__(self):
        return f"{self.get_training_type_display()} for {self.case.youth.full_name}"

    # -- derived ----------------------------------------------------------

    @property
    def is_open(self):
        return self.completion_status == CompletionStatus.ENROLLED

    @property
    def days_in_training(self):
        """Elapsed days, to the completion date where there is one."""
        end = self.completion_date or self.dropout_date or date.today()
        return (end - self.start_date).days

    @property
    def is_overdue(self):
        """Still open past its scheduled end date.

        Not an alert in its own right — the stall detection already covers a
        case that has gone quiet — but it is what a trainer's queue sorts on.
        """
        return self.is_open and self.end_date < date.today()

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        if self.training_type == TrainingType.TVET and not self.trade_or_skill_area:
            # §4.5 marks the field TVET-only, which reads both ways: a technical
            # course without a trade cannot be reported against a skills gap.
            errors["trade_or_skill_area"] = _("Name the trade for a TVET course.")

        if self.completion_status == CompletionStatus.COMPLETED and not self.completion_date:
            errors["completion_date"] = _("Record the date the training completed.")

        if self.completion_status == CompletionStatus.DROPPED_OUT:
            if not self.dropout_date:
                errors["dropout_date"] = _("Record the date the youth left.")
            if not self.dropout_reason:
                # The reason is the whole value of recording a dropout: a count
                # of dropouts tells a programme nothing it can act on.
                errors["dropout_reason"] = _("Record why the youth left the training.")

        if self.completion_date and self.completion_date < self.start_date:
            errors["completion_date"] = _("A training cannot complete before it starts.")

        # Only on add: enrolments recorded before the referral rule landed are
        # still valid rows, and re-validating them on every save would make them
        # uneditable rather than merely historical.
        if self._state.adding or self.source_referral_id:
            problem = training_referral_error(self.source_referral if self.source_referral_id else None, self.case_id)
            if problem:
                errors["source_referral"] = problem

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """Keep the derived fields with the status they describe.

        `dropout_flag` and `triggers_onward_referral` are both System-set in
        §4.5. Deriving them here rather than at the call site means the admin, a
        data fix and the service layer cannot disagree about them.
        """
        self.dropout_flag = self.completion_status == CompletionStatus.DROPPED_OUT
        self.triggers_onward_referral = self.completion_status == CompletionStatus.COMPLETED

        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if "completion_status" in update_fields:
                update_fields |= {"dropout_flag", "triggers_onward_referral"}
                kwargs["update_fields"] = update_fields

        return super().save(*args, **kwargs)
