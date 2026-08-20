"""Meetings and the savings-and-credit ledger — handoff README §5, `sql/001` D.

Handbook annexes 1 to 4 are a ledger: minute book, cashbook, individual passbook,
loan ledger. Digitising them raises the bar above case tracking — this is a
financial system of record, and three rules follow from that:

1. **A meeting cannot close on an unbalanced till.** The error names the
   discrepancy in birr rather than failing generically.
2. **The ledger is append-only.** Corrections are reversals referencing the
   original with a mandatory reason, never edits. Members sign the paper
   register and the digital record has to be defensible against it.
3. **Paper stays primary in the pilot.** The digital record runs in parallel and
   reconciles. Nothing here assumes paper is gone.

Rules 1 and 2 are enforced by database triggers as well as in `services.ledger`.
That is a deliberate departure from the platform's "no business rules in the
database" convention, and the reason is that the service layer is not the only
writer: the admin, a data fix and the offline sync reconciler all reach these
tables, and an append-only ledger that only one path respects is not append-only.
The triggers live in migration `0002_ledger_invariants`.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class MeetingStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    CLOSED = "CLOSED", _("Closed")
    CANCELLED = "CANCELLED", _("Cancelled")


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", _("Present")
    LATE = "LATE", _("Late")
    ABSENT = "ABSENT", _("Absent")
    ABSENT_EXCUSED = "ABSENT_EXCUSED", _("Absent, excused")

    @classmethod
    def counts_as_attending(cls):
        """Present or late, per the attendance formula in DEFINITIONS.md.

        Whether `ABSENT_EXCUSED` should count against a member is an open item
        for FSCO. It currently does. The status exists as its own value so the
        rule can change without a migration.
        """
        return (cls.PRESENT, cls.LATE)


class LedgerAccount(models.TextChoices):
    CASH = "CASH", _("Cash box")
    BANK = "BANK", _("Bank account")


class EntryType(models.TextChoices):
    SAVINGS = "SAVINGS", _("Savings contribution")
    FINE = "FINE", _("Fine")
    SOCIAL_FUND = "SOCIAL_FUND", _("Social fund")
    LOAN_DISBURSEMENT = "LOAN_DISBURSEMENT", _("Loan disbursement")
    LOAN_PRINCIPAL_REPAYMENT = "LOAN_PRINCIPAL_REPAYMENT", _("Loan principal repayment")
    LOAN_CHARGE_REPAYMENT = "LOAN_CHARGE_REPAYMENT", _("Loan service charge repayment")
    BANK_DEPOSIT = "BANK_DEPOSIT", _("Deposit to the bank")
    BANK_WITHDRAWAL = "BANK_WITHDRAWAL", _("Withdrawal from the bank")
    WRITE_OFF = "WRITE_OFF", _("Loan write-off")
    ADJUSTMENT = "ADJUSTMENT", _("Adjustment")

    @classmethod
    def into_the_fund(cls):
        """Entry types that increase the group's own fund."""
        return (cls.SAVINGS, cls.FINE, cls.LOAN_PRINCIPAL_REPAYMENT, cls.LOAN_CHARGE_REPAYMENT)


class LoanStatus(models.TextChoices):
    REQUESTED = "REQUESTED", _("Requested")
    APPROVED = "APPROVED", _("Approved")
    DISBURSED = "DISBURSED", _("Disbursed")
    REPAID = "REPAID", _("Repaid")
    WRITTEN_OFF = "WRITTEN_OFF", _("Written off")
    CANCELLED = "CANCELLED", _("Cancelled")

    @classmethod
    def owing(cls):
        """Statuses under which a member still owes the group money."""
        return (cls.APPROVED, cls.DISBURSED)


class LoanPurpose(models.TextChoices):
    IGA = "IGA", _("Income generating activity")
    EMERGENCY = "EMERGENCY", _("Emergency")
    HOUSEHOLD = "HOUSEHOLD", _("Household")
    EDUCATION = "EDUCATION", _("Education")
    OTHER = "OTHER", _("Other")


class MeetingQuerySet(models.QuerySet):
    def closed(self):
        return self.filter(status=MeetingStatus.CLOSED)


class Meeting(BaseModel):
    """One group meeting. Closing it is a service operation, not a model save.

    `id` is a UUID the client may generate before it has any connectivity, which
    is what makes an offline capture stable across a later sync rather than
    acquiring an identity only when it reaches the server.
    """

    group = models.ForeignKey("wlt.Group", on_delete=models.PROTECT, related_name="meetings", verbose_name=_("group"))
    scheduled_for = models.DateField(_("scheduled for"))
    held_on = models.DateField(_("held on"), null=True, blank=True, db_index=True)
    meeting_no = models.PositiveIntegerField(_("meeting number"))
    bylaw_version = models.ForeignKey(
        "wlt.BylawVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="meetings",
        verbose_name=_("bylaws in force"),
    )

    opening_cash_etb = models.DecimalField(
        _("opening cash (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    closing_cash_etb = models.DecimalField(
        _("closing cash (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    counted_cash_etb = models.DecimalField(
        _("counted cash (ETB)"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("What was physically in the box when the meeting closed."),
    )

    # Handbook 3.6 puts 15 to 30 minutes of social discussion on every agenda.
    # Below the minimum is a warning, not a block: the meeting happened.
    social_time_minutes = models.PositiveSmallIntegerField(_("social discussion (minutes)"), null=True, blank=True)
    social_topic = models.CharField(_("social topic"), max_length=255, blank=True)
    social_led_by = models.ForeignKey(
        "youth.Youth",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_led_discussions",
        verbose_name=_("discussion led by"),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=MeetingStatus.choices, default=MeetingStatus.OPEN, db_index=True
    )
    closed_at = models.DateTimeField(_("closed at"), null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_recorded_meetings",
        verbose_name=_("recorded by"),
    )

    # Offline provenance. `device_id` is what makes a two-device conflict
    # legible rather than mysterious; `synced_at` is what the readiness card
    # stamps itself with, because a stale card that is honest about its age
    # beats a fresh one that is wrong.
    device_id = models.CharField(_("device"), max_length=64, blank=True)
    synced_at = models.DateTimeField(_("synced at"), null=True, blank=True)

    history = HistoricalRecords()

    objects = MeetingQuerySet.as_manager()

    class Meta:
        verbose_name = _("meeting")
        verbose_name_plural = _("meetings")
        ordering = ["group", "-meeting_no"]
        constraints = [
            models.UniqueConstraint(fields=["group", "meeting_no"], name="wlt_meeting_no_unique_per_group"),
            models.CheckConstraint(
                condition=~models.Q(status=MeetingStatus.CLOSED)
                | models.Q(closing_cash_etb__isnull=False, counted_cash_etb__isnull=False),
                name="wlt_meeting_closed_needs_counts",
            ),
        ]
        indexes = [models.Index(fields=["group", "-held_on"])]

    def __str__(self):
        return f"{self.group.name} meeting {self.meeting_no}"


class Attendance(BaseModel):
    """Who was there. The numerator of the attendance rate."""

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendance", verbose_name=_("meeting"))
    person = models.ForeignKey(
        "youth.Youth", on_delete=models.PROTECT, related_name="wlt_attendance", verbose_name=_("member")
    )
    status = models.CharField(_("attendance"), max_length=16, choices=AttendanceStatus.choices)
    note = models.CharField(_("note"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("attendance")
        verbose_name_plural = _("attendance")
        constraints = [models.UniqueConstraint(fields=["meeting", "person"], name="wlt_attendance_one_per_member")]
        indexes = [models.Index(fields=["person"])]

    def __str__(self):
        return f"{self.person.full_name}: {self.get_status_display()}"


class LedgerEntryQuerySet(models.QuerySet):
    def cash(self):
        return self.filter(account=LedgerAccount.CASH)

    def not_reversed(self):
        """Entries no later reversal points at.

        A reversal and its original both stay on the record — that is the point
        of a reversal — so any sum over the ledger must either include both or
        exclude both. Every total in `services.ledger` includes both, so this is
        for display, not for arithmetic.
        """
        return self.exclude(pk__in=LedgerEntry.objects.filter(reverses__isnull=False).values("reverses_id"))


class LedgerEntry(BaseModel):
    """One line of the cashbook. Append-only, enforced by trigger (A5, A6).

    Django's `.update()` and `.delete()` will raise against these rows. That is
    intended: `services.ledger.reverse_entry` is the supported correction, and
    it writes a new row pointing at the original with a mandatory reason.
    """

    group = models.ForeignKey(
        "wlt.Group", on_delete=models.PROTECT, related_name="ledger_entries", verbose_name=_("group")
    )
    meeting = models.ForeignKey(
        Meeting,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("meeting"),
    )
    person = models.ForeignKey(
        "youth.Youth",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_ledger_entries",
        verbose_name=_("member"),
        help_text=_("Empty for a group-level entry such as a bank deposit."),
    )
    loan = models.ForeignKey(
        "wlt.Loan",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        verbose_name=_("loan"),
    )

    entry_type = models.CharField(_("entry type"), max_length=32, choices=EntryType.choices, db_index=True)
    account = models.CharField(
        _("account"), max_length=8, choices=LedgerAccount.choices, default=LedgerAccount.CASH, db_index=True
    )
    amount_etb = models.DecimalField(_("amount (ETB)"), max_digits=14, decimal_places=2)

    reverses = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversals",
        verbose_name=_("reverses"),
    )
    reversal_reason = models.TextField(_("reversal reason"), blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_ledger_entries",
        verbose_name=_("recorded by"),
    )

    objects = LedgerEntryQuerySet.as_manager()

    class Meta:
        verbose_name = _("ledger entry")
        verbose_name_plural = _("ledger entries")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount_etb=0), name="wlt_ledger_amount_nonzero"),
            models.CheckConstraint(
                condition=models.Q(reverses__isnull=True) | ~models.Q(reversal_reason=""),
                name="wlt_ledger_reversal_needs_reason",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "-created_at"]),
            models.Index(fields=["meeting"]),
        ]

    def __str__(self):
        return f"{self.get_entry_type_display()} {self.amount_etb} ETB"


class Loan(BaseModel):
    """An internal loan from the group's own fund.

    `charge_basis` and `charge_rate` are copied here at disbursement and never
    read live from the bylaw. A group that changes its rate in month 9 must not
    thereby change what an existing borrower owes.
    """

    group = models.ForeignKey("wlt.Group", on_delete=models.PROTECT, related_name="loans", verbose_name=_("group"))
    person = models.ForeignKey(
        "youth.Youth", on_delete=models.PROTECT, related_name="wlt_loans", verbose_name=_("borrower")
    )
    cycle_batch = models.PositiveIntegerField(
        _("cycle"),
        default=1,
        help_text=_("Loans issued in one lending round. A cycle completes when every loan in it is fully repaid."),
    )

    approved_at_meeting = models.ForeignKey(
        Meeting,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="loans_approved",
        verbose_name=_("approved at"),
    )
    disbursed_at_meeting = models.ForeignKey(
        Meeting,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="loans_disbursed",
        verbose_name=_("disbursed at"),
    )
    disbursed_on = models.DateField(_("disbursed on"), null=True, blank=True)

    principal_etb = models.DecimalField(_("principal (ETB)"), max_digits=14, decimal_places=2)
    charge_basis = models.CharField(_("service charge basis"), max_length=24)
    charge_rate = models.DecimalField(_("service charge rate"), max_digits=6, decimal_places=4)

    purpose = models.CharField(_("purpose"), max_length=16, choices=LoanPurpose.choices)
    purpose_note = models.CharField(_("purpose note"), max_length=255, blank=True)
    due_on = models.DateField(_("due on"))

    status = models.CharField(
        _("status"), max_length=16, choices=LoanStatus.choices, default=LoanStatus.REQUESTED, db_index=True
    )
    written_off_on = models.DateField(_("written off on"), null=True, blank=True)
    write_off_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_write_offs",
        verbose_name=_("write-off approved by"),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("loan")
        verbose_name_plural = _("loans")
        ordering = ["-disbursed_on", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(principal_etb__gt=0), name="wlt_loan_principal_positive"),
            models.CheckConstraint(condition=models.Q(charge_rate__gte=0), name="wlt_loan_charge_rate_nonneg"),
            models.CheckConstraint(
                condition=models.Q(disbursed_on__isnull=True) | models.Q(due_on__gte=models.F("disbursed_on")),
                name="wlt_loan_due_after_disbursal",
            ),
        ]
        indexes = [
            models.Index(fields=["group", "status"]),
            models.Index(fields=["person"]),
        ]

    def __str__(self):
        return f"{self.person.full_name}: {self.principal_etb} ETB"

    @property
    def principal_repaid_etb(self):
        return self.repayments.aggregate(total=models.Sum("principal_etb"))["total"] or 0

    @property
    def outstanding_principal_etb(self):
        return self.principal_etb - self.principal_repaid_etb

    @property
    def first_unpaid_due_on(self):
        """The reference date for delinquency.

        The earliest instalment not yet covered, falling back to `due_on` for a
        single-maturity loan with no schedule. The handoff's `sql/004` uses
        `due_on` unconditionally and flags the limitation; this closes it, which
        is why PAR30 here can differ from the bundle's own number on a loan that
        carries a schedule.
        """
        instalments = list(self.schedule.order_by("due_on"))
        if not instalments:
            return self.due_on
        paid = self.principal_repaid_etb
        for instalment in instalments:
            paid -= instalment.principal_due_etb
            if paid < 0:
                return instalment.due_on
        return instalments[-1].due_on


class LoanSchedule(BaseModel):
    """Instalments, where a loan has them."""

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="schedule", verbose_name=_("loan"))
    instalment_no = models.PositiveSmallIntegerField(_("instalment"))
    due_on = models.DateField(_("due on"))
    principal_due_etb = models.DecimalField(_("principal due (ETB)"), max_digits=14, decimal_places=2)
    charge_due_etb = models.DecimalField(_("service charge due (ETB)"), max_digits=14, decimal_places=2)

    class Meta:
        verbose_name = _("loan instalment")
        verbose_name_plural = _("loan instalments")
        ordering = ["loan", "instalment_no"]
        constraints = [
            models.UniqueConstraint(fields=["loan", "instalment_no"], name="wlt_schedule_instalment_unique"),
        ]

    def __str__(self):
        return f"instalment {self.instalment_no} of {self.loan_id}"


class Repayment(BaseModel):
    """Money coming back. Principal and service charge are separate columns
    because PAR30 is a statement about principal alone."""

    loan = models.ForeignKey(Loan, on_delete=models.PROTECT, related_name="repayments", verbose_name=_("loan"))
    meeting = models.ForeignKey(
        Meeting,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="repayments",
        verbose_name=_("meeting"),
    )
    paid_on = models.DateField(_("paid on"))
    principal_etb = models.DecimalField(_("principal (ETB)"), max_digits=14, decimal_places=2, default=0)
    charge_etb = models.DecimalField(_("service charge (ETB)"), max_digits=14, decimal_places=2, default=0)

    class Meta:
        verbose_name = _("repayment")
        verbose_name_plural = _("repayments")
        ordering = ["loan", "paid_on"]
        constraints = [
            models.CheckConstraint(condition=models.Q(principal_etb__gte=0), name="wlt_repayment_principal_nonneg"),
            models.CheckConstraint(condition=models.Q(charge_etb__gte=0), name="wlt_repayment_charge_nonneg"),
            models.CheckConstraint(
                condition=models.Q(principal_etb__gt=0) | models.Q(charge_etb__gt=0),
                name="wlt_repayment_nonzero",
            ),
        ]
        indexes = [models.Index(fields=["loan", "paid_on"])]

    def __str__(self):
        return f"{self.principal_etb + self.charge_etb} ETB on {self.paid_on}"


class SyncConflict(BaseModel):
    """Two devices recorded the same thing. Both are kept; neither is merged.

    The handoff asks for meeting numbers unique and sequential per group *and*
    for a two-device duplicate to be kept and flagged rather than silently
    merged. Those pull against each other: the unique index refuses the second
    write. This row is where the refused payload goes, exactly as it arrived,
    for a facilitator to resolve.

    **Financial records are never auto-merged.** Resolution is a person choosing,
    with both versions in front of her.
    """

    group = models.ForeignKey(
        "wlt.Group", on_delete=models.PROTECT, related_name="sync_conflicts", verbose_name=_("group")
    )
    entity = models.CharField(_("entity"), max_length=32, help_text=_("Which record the payload was for."))
    natural_key = models.CharField(
        _("natural key"), max_length=128, help_text=_("For a meeting, its number within the group.")
    )
    payload = models.JSONField(_("payload"), help_text=_("The rejected record, as the device sent it."))
    device_id = models.CharField(_("device"), max_length=64, blank=True)
    detail = models.TextField(_("detail"), blank=True)

    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_resolved_conflicts",
        verbose_name=_("resolved by"),
    )
    resolution_note = models.TextField(_("resolution"), blank=True)

    class Meta:
        verbose_name = _("sync conflict")
        verbose_name_plural = _("sync conflicts")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["group", "resolved_at"])]

    def __str__(self):
        return f"{self.entity} {self.natural_key} on {self.group.name}"
