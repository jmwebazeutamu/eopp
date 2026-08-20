"""Placement and its retention checkpoints — spec §4.7. Sprint 5.

§4.7 types the checkpoints as "Status + Date + Reference (User), x3" and says
**one record per checkpoint**, so they are a child table rather than nine
columns. Three reasons that is the right reading: a checkpoint carries who did
it and when, which nine columns express badly; the set will grow if the
programme adds a six-month check; and a queue of "checks due this week" is a
query over rows, not a union of three column comparisons.

Two open questions land here, both flagged in CLAUDE.md as schema changes that
had to arrive **before** the first placement was recorded or the first cohort
would be permanently unreportable:

* **`is_subsidised` (OQ-3).** The retention anchor the programme reports on is
  "employed three months after exit, **unsubsidised**". A placement whose wage
  is paid by the programme is not that, and there is no way to tell afterwards.
* **`exit_reason` as an enum (OQ-5).** §4.7 types it as free text. Left as text,
  "left for a better job" and "dismissed" are the same field, and the difference
  is the entire difference between a success and a failure.
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


def placement_referral_error(referral, case):
    """Why `referral` may not open this record on `case` — or None.

    **The single definition**, shared by the service, the serializer and
    `clean()`. They must not drift: a `ModelSerializer` does not run
    `full_clean`, so any rule stated only on the model is unenforced wherever a
    viewset saves through the serializer.

    Which categories qualify is a flag on the category row, not a tuple here.
    §9 makes the taxonomy the administrator's to extend, and the
    `PLACEMENT_REFERRAL_CATEGORY_CODES` this replaced meant a category she added could
    not open the record, with no fix short of a deploy.
    """
    if referral is None:
        return _("Create a placement from an employment or apprenticeship referral.")
    if referral.case_id is None:
        return _("This referral is not attached to a youth case.")
    if case is not None and referral.case_id != getattr(case, "pk", case):
        return _("That referral belongs to a different case.")
    if not referral.referral_category.creates_placement:
        return _("A %(category)s referral does not open a placement.") % {
            "category": referral.referral_category.label.lower()
        }
    return None


# §4.7's three checkpoints, in days from the placement date. Operations only:
# the *reportable* retention anchor is three months from programme exit and
# unsubsidised (OQ-9), which is a different question with a different
# denominator. Both exist because they answer to different people — these drive
# a case manager's week, that one rolls up to the parent operation.
CHECKPOINT_DAYS = (30, 60, 90)


class PlacementType(models.TextChoices):
    """Spec §4.7: 'Job / Apprenticeship'."""

    JOB = "JOB", _("Job")
    APPRENTICESHIP = "APPRENTICESHIP", _("Apprenticeship")


class ContractType(models.TextChoices):
    """TODO(spec-gap): §4.7 types this as an Enum and does not enumerate it.

    These follow Ethiopian labour practice. `NONE` is not an oversight — most
    first placements in the pilot woredas are verbal, and a form that forces a
    contract type onto them would record a document that does not exist.
    """

    NONE = "NONE", _("No written contract")
    PERMANENT = "PERMANENT", _("Permanent")
    FIXED_TERM = "FIXED_TERM", _("Fixed term")
    CASUAL = "CASUAL", _("Casual or daily")
    APPRENTICESHIP = "APPRENTICESHIP", _("Apprenticeship agreement")


class ExitReason(models.TextChoices):
    """OQ-5, settled in principle and implemented here.

    Ordered from the outcome the programme wants to the one it does not, because
    the ordering is the point: "left for a better job" is a **success** and
    "dismissed" is not, and a free-text field could not tell a report which had
    happened. `LOST_TO_FOLLOW_UP` is separate again — it says the programme does
    not know, which is neither.
    """

    BETTER_JOB = "BETTER_JOB", _("Left for a better job")
    RESIGNED = "RESIGNED", _("Resigned")
    CONTRACT_ENDED = "CONTRACT_ENDED", _("Contract ended")
    REDUNDANT = "REDUNDANT", _("Made redundant")
    DISMISSED = "DISMISSED", _("Dismissed")
    HEALTH = "HEALTH", _("Health or family reasons")
    MIGRATED = "MIGRATED", _("Migrated")
    LOST_TO_FOLLOW_UP = "LOST_TO_FOLLOW_UP", _("Lost to follow-up")

    @classmethod
    def voluntary_upward(cls):
        """Exits that are not a loss. Reported apart from the rest."""
        return (cls.BETTER_JOB,)


class RetentionStatus(models.TextChoices):
    """What a checkpoint found.

    `UNREACHABLE` is a first-class answer and not a missing one: at 90 days a
    meaningful share of youth cannot be contacted, and recording that as
    "not retained" would overstate loss while recording it as retained would
    overstate success. It is reported as its own band.
    """

    PENDING = "PENDING", _("Not checked yet")
    RETAINED = "RETAINED", _("Still in the placement")
    EXITED = "EXITED", _("No longer in the placement")
    UNREACHABLE = "UNREACHABLE", _("Could not be contacted")


class PlacementQuerySet(models.QuerySet):
    def open(self):
        """Placements the youth has not left."""
        return self.filter(exit_date__isnull=True)

    def unsubsidised(self):
        return self.filter(is_subsidised=False)

    def placed_youth_ids(self):
        """Distinct youth with at least one placement record.

        The unit that matters for a programme figure: a youth placed twice is
        one young person in work.

        **This does not replace `Referral.objects.placements()`**, and the two
        answer different questions. That one counts referrals that ended in a
        job — it is a statement about the referral engine, and it is what the
        funnel and loop-closure figures read. This one counts placement records,
        which include a youth who found work without a referral and exclude a
        placement outcome nobody has yet written up. `placement_coverage` in
        the dashboard reports the gap between them rather than hiding it.
        """
        return set(self.values_list("case__youth_id", flat=True))


class Placement(BaseModel):
    """Spec §4.7. `placement_id` is `id`, per the §4 type-translation guide."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="placements",
        verbose_name=_("case"),
    )
    source_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="placements",
        verbose_name=_("source referral"),
        help_text=_("Set when the placement resulted from a referral. Empty when the youth found the work herself."),
    )

    employer_name = models.CharField(_("employer"), max_length=255, db_index=True)
    sector = models.CharField(_("sector"), max_length=128)
    placement_type = models.CharField(_("placement type"), max_length=16, choices=PlacementType.choices)

    placement_date = models.DateField(_("placement date"), db_index=True)
    wage_amount = models.DecimalField(
        _("wage (ETB per month)"),
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Leave empty where the youth would not say. A guessed wage is worse than a blank."),
    )
    contract_type = models.CharField(
        _("contract type"), max_length=24, choices=ContractType.choices, default=ContractType.NONE
    )
    contract_duration = models.CharField(_("contract duration"), max_length=128, blank=True)

    # OQ-3. The reportable retention anchor is "unsubsidised", and a placement
    # whose wage the programme pays cannot be told apart afterwards.
    is_subsidised = models.BooleanField(
        _("wage subsidised by the programme"),
        default=False,
        db_index=True,
        help_text=_("A subsidised placement is excluded from the reported retention figure."),
    )

    exit_date = models.DateField(_("exit date"), null=True, blank=True, db_index=True)
    exit_reason = models.CharField(_("exit reason"), max_length=24, choices=ExitReason.choices, blank=True)
    exit_note = models.TextField(_("exit note"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_placements",
        verbose_name=_("recorded by"),
        help_text=_("The employer liaison or case manager who entered this record."),
    )
    notes = models.TextField(_("notes"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = PlacementQuerySet.as_manager()

    class Meta:
        verbose_name = _("placement")
        verbose_name_plural = _("placements")
        ordering = ["-placement_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(exit_date__isnull=True) | models.Q(exit_date__gte=models.F("placement_date")),
                name="placement_exit_after_placement",
            ),
            # OQ-5's whole point: an exit with no reason cannot be reported as
            # either a success or a loss, and by the time somebody asks, nobody
            # remembers.
            models.CheckConstraint(
                condition=models.Q(exit_date__isnull=True) | ~models.Q(exit_reason=""),
                name="placement_exit_needs_reason",
            ),
            models.CheckConstraint(
                condition=models.Q(wage_amount__isnull=True) | models.Q(wage_amount__gte=0),
                name="placement_wage_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-placement_date"]),
            models.Index(fields=["placement_date", "is_subsidised"]),
        ]

    def __str__(self):
        return f"{self.case.youth.full_name} at {self.employer_name}"

    # -- derived ----------------------------------------------------------

    @property
    def is_open(self):
        return self.exit_date is None

    @property
    def days_held(self):
        """Days in the placement, to the exit or to today."""
        return ((self.exit_date or date.today()) - self.placement_date).days

    def due_date_for(self, checkpoint):
        return self.placement_date + timedelta(days=checkpoint)

    def held_at(self, checkpoint):
        """Whether the youth was still in this placement at a checkpoint.

        Derived from the exit date rather than from the check, so a placement
        somebody exited before anyone got round to the 60-day call still
        answers the question correctly.
        """
        if self.exit_date is None:
            return self.days_held >= checkpoint or None
        return self.days_held >= checkpoint

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        if self.exit_date and not self.exit_reason:
            errors["exit_reason"] = _("Record why the youth left the placement.")

        if self.exit_date and self.exit_date < self.placement_date:
            errors["exit_date"] = _("A youth cannot leave a placement before it starts.")

        if self.placement_date and self.placement_date > date.today():
            errors["placement_date"] = _("A placement cannot start in the future.")

        # Only on add: records written before the referral rule are still valid
        # rows, and re-validating them on save would make them uneditable.
        if self._state.adding or self.source_referral_id:
            problem = placement_referral_error(self.source_referral if self.source_referral_id else None, self.case_id)
            if problem:
                errors["source_referral"] = problem

        if errors:
            raise ValidationError(errors)


class RetentionCheckQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=RetentionStatus.PENDING)

    def due(self, as_of=None):
        """Checks whose date has passed and which nobody has answered.

        The queryset the reminder job materialises. Kept here rather than in the
        job for the same reason the referral prompts are: the condition is the
        source of truth, and the alert is a materialisation of it.
        """
        as_of = as_of or date.today()
        return self.pending().filter(due_date__lte=as_of, placement__exit_date__isnull=True)


class RetentionCheck(BaseModel):
    """One of §4.7's three checkpoints, as its own record.

    Created up front — three rows the moment a placement is recorded — rather
    than when each falls due. A checkpoint that exists as a `PENDING` row can be
    listed, counted and sorted; one that exists only as an arithmetic
    relationship between today and a placement date cannot, and every screen
    would have to recompute it.
    """

    placement = models.ForeignKey(
        Placement, on_delete=models.CASCADE, related_name="retention_checks", verbose_name=_("placement")
    )
    checkpoint = models.PositiveSmallIntegerField(
        _("checkpoint (days)"), choices=[(days, _("%(days)s days") % {"days": days}) for days in CHECKPOINT_DAYS]
    )
    due_date = models.DateField(_("due"), db_index=True)

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=RetentionStatus.choices,
        default=RetentionStatus.PENDING,
        db_index=True,
    )
    checked_on = models.DateField(_("checked on"), null=True, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="retention_checks",
        verbose_name=_("checked by"),
    )
    note = models.TextField(_("note"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = RetentionCheckQuerySet.as_manager()

    class Meta:
        verbose_name = _("retention check")
        verbose_name_plural = _("retention checks")
        ordering = ["placement", "checkpoint"]
        constraints = [
            models.UniqueConstraint(fields=["placement", "checkpoint"], name="retention_one_per_checkpoint"),
            # A recorded answer needs a date and a person: §9 wants an actor on
            # every status change, and a retention figure whose checks nobody
            # signed is not evidence.
            models.CheckConstraint(
                condition=models.Q(status=RetentionStatus.PENDING)
                | models.Q(checked_on__isnull=False, checked_by__isnull=False),
                name="retention_answer_needs_actor",
            ),
        ]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return f"{self.checkpoint}-day check on {self.placement_id}"

    @property
    def is_overdue(self):
        return self.status == RetentionStatus.PENDING and self.due_date < date.today()

    def clean(self):
        errors = {}
        if self.status != RetentionStatus.PENDING:
            if not self.checked_on:
                errors["checked_on"] = _("Record the date this check was made.")
            if not self.checked_by_id:
                errors["checked_by"] = _("Record who made this check.")
        if errors:
            raise ValidationError(errors)
