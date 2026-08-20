"""Enterprise — spec §4.8. Sprint 6.

The self-employment pathway's record: a business plan, a grant or loan, some
mentorship, a registration, and a set of milestones. §4.8 marks `milestones` as
a one-to-many child table, which is the right shape for the same reason the
retention checkpoints are: a milestone carries its own dates and status, and a
plan whose milestones live in a text field cannot be listed, counted or chased.

Two things this entity is careful **not** to claim:

* **A grant disbursed is not a business trading.** The two are separate fields
  and separate figures, because a programme that reports disbursement as an
  outcome is reporting its own activity back to itself.
* **A registered business is not a surviving business.** Registration is a
  status with a date; survival is what the follow-up log (§4.9) records over
  time. Nothing here infers one from the other.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


def enterprise_referral_error(referral, case):
    """Why `referral` may not open this record on `case` — or None.

    **The single definition**, shared by the service, the serializer and
    `clean()`. They must not drift: a `ModelSerializer` does not run
    `full_clean`, so any rule stated only on the model is unenforced wherever a
    viewset saves through the serializer.

    Which categories qualify is a flag on the category row, not a tuple here.
    §9 makes the taxonomy the administrator's to extend, and the
    `ENTERPRISE_REFERRAL_CATEGORY_CODES` this replaced meant a category she added could
    not open the record, with no fix short of a deploy.
    """
    if referral is None:
        return _("Create an enterprise from an enterprise or finance-access referral.")
    if referral.case_id is None:
        return _("This referral is not attached to a youth case.")
    if case is not None and referral.case_id != getattr(case, "pk", case):
        return _("That referral belongs to a different case.")
    if not referral.referral_category.creates_enterprise:
        return _("A %(category)s referral does not open an enterprise record.") % {
            "category": referral.referral_category.label.lower()
        }
    return None


class BusinessPlanStatus(models.TextChoices):
    """TODO(spec-gap): §4.8 types this as an Enum and does not enumerate it.

    The sequence follows how the enterprise development agencies work in the
    pilot woredas: a plan is drafted, reviewed, and either approved or sent back.
    `REVISION_REQUESTED` is separate from `REJECTED` on purpose — most first
    plans come back for revision, and filing that as a rejection would report a
    failure rate that is really a coaching workload.
    """

    NOT_STARTED = "NOT_STARTED", _("Not started")
    DRAFTED = "DRAFTED", _("Drafted")
    UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
    REVISION_REQUESTED = "REVISION_REQUESTED", _("Revision requested")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")

    @classmethod
    def approved_statuses(cls):
        return (cls.APPROVED,)


class RegistrationStatus(models.TextChoices):
    """Whether the business exists in law.

    `NOT_REQUIRED` is a real answer in this programme: a great many youth
    enterprises operate below the registration threshold, and forcing them into
    "not registered" would report informality as non-compliance.
    """

    NOT_REQUIRED = "NOT_REQUIRED", _("Not required at this scale")
    NOT_STARTED = "NOT_STARTED", _("Not started")
    IN_PROGRESS = "IN_PROGRESS", _("In progress")
    REGISTERED = "REGISTERED", _("Registered")


class MarketLinkageStatus(models.TextChoices):
    NONE = "NONE", _("No market linkage")
    IDENTIFIED = "IDENTIFIED", _("Buyer identified")
    NEGOTIATING = "NEGOTIATING", _("Negotiating")
    TRADING = "TRADING", _("Trading")
    LAPSED = "LAPSED", _("Lapsed")


class SupportType(models.TextChoices):
    """What the programme actually gave. §4.8 names the amount and not the kind.

    A grant and a loan are different instruments with different consequences for
    the youth, and reporting them as one number would say nothing about either.
    """

    NONE = "NONE", _("None")
    GRANT = "GRANT", _("Grant")
    LOAN = "LOAN", _("Loan")
    IN_KIND = "IN_KIND", _("In-kind (equipment or stock)")


class MilestoneStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    ACHIEVED = "ACHIEVED", _("Achieved")
    MISSED = "MISSED", _("Missed")
    CANCELLED = "CANCELLED", _("Cancelled")


class EnterpriseQuerySet(models.QuerySet):
    def trading(self):
        return self.filter(market_linkage_status=MarketLinkageStatus.TRADING)

    def with_support_disbursed(self):
        """Enterprises that actually received money or goods.

        Deliberately not "approved": approval is a decision, disbursement is a
        transfer, and the gap between them is one of the things this record
        exists to make visible.
        """
        return self.exclude(disbursement_date__isnull=True)

    def registered(self):
        return self.filter(business_registration_status=RegistrationStatus.REGISTERED)

    def awaiting_disbursement(self):
        """Approved plans where nothing has been transferred yet.

        The enterprise officer's queue: a youth with an approved plan and no
        money is waiting on the programme, not on herself.
        """
        return self.filter(
            business_plan_status__in=BusinessPlanStatus.approved_statuses(), disbursement_date__isnull=True
        )


class Enterprise(BaseModel):
    """Spec §4.8. `enterprise_id` is `id`, per the §4 type-translation guide."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="enterprises",
        verbose_name=_("case"),
    )
    source_referral = models.ForeignKey(
        "referrals.Referral",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="enterprises",
        verbose_name=_("source referral"),
    )

    # Not in §4.8's field list. A business with no name cannot be talked about
    # on a phone call, and every screen would have to say "the enterprise of
    # <youth>", which is not what anybody calls it.
    business_name = models.CharField(_("business name"), max_length=255, blank=True)
    sector = models.CharField(_("sector"), max_length=128, blank=True)

    business_plan_status = models.CharField(
        _("business plan status"),
        max_length=24,
        choices=BusinessPlanStatus.choices,
        default=BusinessPlanStatus.NOT_STARTED,
        db_index=True,
    )

    support_type = models.CharField(
        _("support type"), max_length=16, choices=SupportType.choices, default=SupportType.NONE
    )
    grant_or_loan_amount = models.DecimalField(
        _("grant or loan amount (ETB)"), max_digits=12, decimal_places=2, null=True, blank=True
    )
    disbursement_date = models.DateField(_("disbursement date"), null=True, blank=True, db_index=True)

    mentorship_sessions_count = models.PositiveSmallIntegerField(_("mentorship sessions"), default=0)

    business_registration_status = models.CharField(
        _("registration status"),
        max_length=16,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.NOT_STARTED,
    )
    business_registration_number = models.CharField(_("registration number"), max_length=64, blank=True)
    market_linkage_status = models.CharField(
        _("market linkage"), max_length=16, choices=MarketLinkageStatus.choices, default=MarketLinkageStatus.NONE
    )

    started_trading_on = models.DateField(
        _("started trading on"),
        null=True,
        blank=True,
        help_text=_("The date the business first sold something. Not the disbursement date."),
    )
    closed_on = models.DateField(_("closed on"), null=True, blank=True)
    closure_reason = models.TextField(_("closure reason"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_enterprises",
        verbose_name=_("recorded by"),
        help_text=_("The enterprise officer who owns this record. Scopes her own caseload."),
    )
    notes = models.TextField(_("notes"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = EnterpriseQuerySet.as_manager()

    class Meta:
        verbose_name = _("enterprise")
        verbose_name_plural = _("enterprises")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(grant_or_loan_amount__isnull=True) | models.Q(grant_or_loan_amount__gte=0),
                name="enterprise_support_non_negative",
            ),
            # Money moved on a date, or it did not move. A disbursement with no
            # amount cannot be reconciled against anything.
            models.CheckConstraint(
                condition=models.Q(disbursement_date__isnull=True) | models.Q(grant_or_loan_amount__isnull=False),
                name="enterprise_disbursement_needs_amount",
            ),
            models.CheckConstraint(
                condition=models.Q(closed_on__isnull=True) | ~models.Q(closure_reason=""),
                name="enterprise_closure_needs_reason",
            ),
        ]
        indexes = [
            models.Index(fields=["case", "-created_at"]),
            models.Index(fields=["business_plan_status", "disbursement_date"]),
        ]

    def __str__(self):
        return self.business_name or f"Enterprise for {self.case.youth.full_name}"

    # -- derived ----------------------------------------------------------

    @property
    def is_open(self):
        return self.closed_on is None

    @property
    def has_support(self):
        return self.disbursement_date is not None

    @property
    def days_since_disbursement(self):
        if not self.disbursement_date:
            return None
        return ((self.closed_on or date.today()) - self.disbursement_date).days

    @property
    def milestones_achieved(self):
        return self.milestones.filter(status=MilestoneStatus.ACHIEVED).count()

    @property
    def milestones_overdue(self):
        return sum(1 for milestone in self.milestones.all() if milestone.is_overdue)

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        if self.disbursement_date and self.grant_or_loan_amount is None:
            errors["grant_or_loan_amount"] = _("Record how much was disbursed.")

        if self.disbursement_date and self.support_type == SupportType.NONE:
            # Otherwise the figure cannot be split into grant and loan, which is
            # the only split that says anything about the youth's position.
            errors["support_type"] = _("Say whether this was a grant, a loan or in-kind support.")

        if self.grant_or_loan_amount is not None and self.support_type == SupportType.NONE:
            errors["support_type"] = _("An amount needs a support type.")

        if self.business_registration_number and self.business_registration_status != RegistrationStatus.REGISTERED:
            errors["business_registration_number"] = _("A registration number belongs to a registered business.")

        if self.closed_on and not self.closure_reason:
            errors["closure_reason"] = _("Record why the business closed.")

        if self.closed_on and self.started_trading_on and self.closed_on < self.started_trading_on:
            errors["closed_on"] = _("A business cannot close before it starts trading.")

        # Only on add: records written before the referral rule are still valid
        # rows, and re-validating them on save would make them uneditable.
        if self._state.adding or self.source_referral_id:
            problem = enterprise_referral_error(self.source_referral if self.source_referral_id else None, self.case_id)
            if problem:
                errors["source_referral"] = problem

        if errors:
            raise ValidationError(errors)


class MilestoneQuerySet(models.QuerySet):
    def pending(self):
        return self.filter(status=MilestoneStatus.PENDING)

    def overdue(self, as_of=None):
        as_of = as_of or date.today()
        return self.pending().filter(target_date__lt=as_of)


class EnterpriseMilestone(BaseModel):
    """§4.8's one-to-many child: `milestone_name`, `target_date`, `completion_date`, `status`.

    A sub-table rather than a text field, for the reason every plan has: a
    milestone is something somebody is supposed to do by a date, and a date in
    prose cannot be chased. Missing one is recorded rather than deleted — a plan
    whose missed milestones vanish reads as a plan that went well.
    """

    enterprise = models.ForeignKey(
        Enterprise, on_delete=models.CASCADE, related_name="milestones", verbose_name=_("enterprise")
    )
    milestone_name = models.CharField(_("milestone"), max_length=255)
    target_date = models.DateField(_("target date"), db_index=True)
    completion_date = models.DateField(_("completion date"), null=True, blank=True)
    status = models.CharField(
        _("status"), max_length=16, choices=MilestoneStatus.choices, default=MilestoneStatus.PENDING, db_index=True
    )
    note = models.TextField(_("note"), blank=True)

    history = HistoricalRecords()

    objects = MilestoneQuerySet.as_manager()

    class Meta:
        verbose_name = _("enterprise milestone")
        verbose_name_plural = _("enterprise milestones")
        ordering = ["enterprise", "target_date"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status=MilestoneStatus.ACHIEVED) | models.Q(completion_date__isnull=False),
                name="milestone_achieved_needs_date",
            ),
        ]
        indexes = [models.Index(fields=["status", "target_date"])]

    def __str__(self):
        return self.milestone_name

    @property
    def is_overdue(self):
        return self.status == MilestoneStatus.PENDING and self.target_date < date.today()

    def clean(self):
        if self.status == MilestoneStatus.ACHIEVED and not self.completion_date:
            raise ValidationError({"completion_date": _("Record the date this milestone was reached.")})
