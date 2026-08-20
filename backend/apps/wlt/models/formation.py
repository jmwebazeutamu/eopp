"""Group formation — handoff decision D2, README §4, `sql/001` section C.

A four-state flow: Mobilisation → Draft → Constituted → Active. A group becomes
Active when its first savings meeting closes with a balanced till, and only then
does the phase machine take over.

Creating groups already active was rejected because it hides the drop-off
between mobilisation and first savings, which is exactly what the pilot needs to
measure. Everything abandoned on the way is retained, never deleted: a kebele
that produced no groups is programme learning, and it is invisible if only
successes are stored.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class GroupStatus(models.TextChoices):
    """The formation and lifecycle state. Separate from phase — see `Group`."""

    DRAFT = "DRAFT", _("Draft")
    CONSTITUTED = "CONSTITUTED", _("Constituted")
    ACTIVE = "ACTIVE", _("Active")
    AT_RISK = "AT_RISK", _("At risk")
    DORMANT = "DORMANT", _("Dormant")
    SPLIT = "SPLIT", _("Split")
    MERGED = "MERGED", _("Merged")
    DISSOLVED = "DISSOLVED", _("Dissolved")
    ABANDONED = "ABANDONED", _("Abandoned")

    # Both return tuples, in a fixed order, and not sets. A set literal in a
    # constraint's `__in` renders in whatever order the process hashed it, so
    # `makemigrations` proposed a fresh AlterConstraint on every run and the
    # migration graph never settled.
    @classmethod
    def operating(cls):
        """Statuses in which a group holds money and meets."""
        return (cls.ACTIVE, cls.AT_RISK, cls.DORMANT)

    @classmethod
    def phase_bearing(cls):
        """Statuses a `current_phase` may accompany.

        A draft has no phase because it has never saved; a dissolved group keeps
        the phase it reached, because its history is still reported on.
        """
        return (cls.ACTIVE, cls.AT_RISK, cls.DORMANT, cls.SPLIT, cls.MERGED, cls.DISSOLVED)


class Phase(models.TextChoices):
    """Maturity, handbook section 4. Null until activation."""

    P1 = "P1", _("Phase 1 — formation and savings discipline")
    P2 = "P2", _("Phase 2 — internal lending")
    P3 = "P3", _("Phase 3 — cluster level association")
    P4 = "P4", _("Phase 4 — federation")

    @classmethod
    def order(cls):
        return [cls.P1, cls.P2, cls.P3, cls.P4]

    @classmethod
    def short_label(cls, phase):
        """ "Phase 2", without the description.

        The full labels explain what a phase *is*, which is right in a form and
        wrong in a gate condition: "Phase 1 — formation and savings discipline
        (need Phase 2 — internal lending)" buries the one word that matters.
        """
        return _("Phase %(number)s") % {"number": phase[-1]} if phase else ""

    @classmethod
    def at_least(cls, phase, minimum):
        if phase is None:
            return False
        order = cls.order()
        return order.index(phase) >= order.index(minimum)


class MeetingCadence(models.TextChoices):
    WEEKLY = "WEEKLY", _("Weekly")
    FORTNIGHTLY = "FORTNIGHTLY", _("Fortnightly")
    MONTHLY = "MONTHLY", _("Monthly")

    @classmethod
    def days(cls, cadence):
        """Nominal days between meetings. Used for adherence and dormancy."""
        return {cls.WEEKLY: 7, cls.FORTNIGHTLY: 14, cls.MONTHLY: 30}[cadence]


class ServiceChargeBasis(models.TextChoices):
    """Open question Q4 — deliberately with **no default**.

    A flat 5% per loan and 5% per month on a three-month loan differ by a factor
    of three. A default here would let the system pick one silently and misstate
    every group's fund position, so the field is nullable and the form cannot be
    submitted without an explicit choice.
    """

    FLAT_PER_LOAN = "FLAT_PER_LOAN", _("Flat, per loan")
    PER_MONTH = "PER_MONTH", _("Per month")
    DECLINING_BALANCE = "DECLINING_BALANCE", _("Declining balance")


class ExitReason(models.TextChoices):
    MOVED = "MOVED", _("Moved away")
    MARRIED_OUT = "MARRIED_OUT", _("Married out of the kebele")
    DIED = "DIED", _("Died")
    WITHDREW = "WITHDREW", _("Withdrew")
    EXPELLED = "EXPELLED", _("Expelled")
    PSNP_EXIT = "PSNP_EXIT", _("Left the PSNP caseload")
    GROUP_SPLIT = "GROUP_SPLIT", _("Moved in a group split")


class OfficeRole(models.TextChoices):
    CHAIR = "CHAIR", _("Chair")
    SECRETARY = "SECRETARY", _("Secretary")
    TREASURER = "TREASURER", _("Treasurer")


class TrainingModule(models.TextChoices):
    SHG_PRINCIPLES = "SHG_PRINCIPLES", _("SHG principles")
    BOOKKEEPING = "BOOKKEEPING", _("Bookkeeping")
    SAVINGS_CREDIT = "SAVINGS_CREDIT", _("Savings and credit")
    FINANCIAL_LITERACY = "FINANCIAL_LITERACY", _("Financial literacy")
    SOCIAL_EMPOWERMENT = "SOCIAL_EMPOWERMENT", _("Social empowerment")
    LEADERSHIP = "LEADERSHIP", _("Leadership")


class MobilisationEvent(BaseModel):
    """Handbook 3.4 step 1 — the community meeting.

    Recorded whether or not the community endorsed the group. A refused
    endorsement is the row that explains a kebele with no groups in it
    (assertion A30), and it only exists because nothing deletes it.

    No individual attendee names beyond the facilitator: this is a community
    meeting, and counts by category are what the handbook asks for.
    """

    kebele = models.ForeignKey(
        "locations.Location",
        on_delete=models.PROTECT,
        related_name="wlt_mobilisation_events",
        verbose_name=_("kebele"),
    )
    held_on = models.DateField(_("held on"), db_index=True)
    facilitator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wlt_mobilisation_events",
        verbose_name=_("facilitator"),
    )

    attendees_potential = models.PositiveIntegerField(_("potential members attending"), null=True, blank=True)
    attendees_husbands = models.PositiveIntegerField(_("husbands attending"), null=True, blank=True)
    attendees_elders = models.PositiveIntegerField(_("elders attending"), null=True, blank=True)
    attendees_leaders = models.PositiveIntegerField(_("kebele leaders attending"), null=True, blank=True)

    endorsement_obtained = models.BooleanField(_("endorsement obtained"))
    endorsement_note = models.TextField(_("endorsement note"), blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("mobilisation event")
        verbose_name_plural = _("mobilisation events")
        ordering = ["-held_on"]

    def __str__(self):
        outcome = _("endorsed") if self.endorsement_obtained else _("refused")
        return f"{self.kebele.name} {self.held_on} ({outcome})"


class GroupQuerySet(models.QuerySet):
    def operating(self):
        return self.filter(status__in=GroupStatus.operating())

    def active(self):
        return self.filter(status=GroupStatus.ACTIVE)

    def cla_eligible(self):
        """Groups that count toward a kebele's CLA threshold (assertion A29)."""
        return self.filter(status=GroupStatus.ACTIVE, current_phase__in=[Phase.P2, Phase.P3, Phase.P4])


class Group(BaseModel):
    """A Self Help Group: 15 to 25 women saving and lending together.

    **Status and phase are two fields, not one.** Status is the lifecycle
    (draft, active, dormant, dissolved); phase is maturity (P1 to P4) and is
    null until activation. Collapsing them would mean either a lifecycle that
    cannot express "active and at P2" or a phase that resets when a group falls
    dormant — and dormancy is recoverable, while phase is a governance decision
    with an approval behind it.
    """

    name = models.CharField(_("name"), max_length=255, db_index=True)
    kebele = models.ForeignKey(
        "locations.Location",
        on_delete=models.PROTECT,
        related_name="wlt_groups",
        verbose_name=_("kebele"),
    )
    mobilisation_event = models.ForeignKey(
        MobilisationEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="groups",
        verbose_name=_("mobilisation event"),
    )

    # The accountable field worker. Also the object-level scoping key: a
    # facilitator sees the groups she runs (`GroupScope.OWN_GROUPS`).
    facilitator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wlt_groups",
        verbose_name=_("facilitator"),
    )

    status = models.CharField(
        _("status"), max_length=16, choices=GroupStatus.choices, default=GroupStatus.DRAFT, db_index=True
    )
    current_phase = models.CharField(_("phase"), max_length=2, choices=Phase.choices, blank=True, db_index=True)

    drafted_on = models.DateField(_("drafted on"), db_index=True)
    constituted_on = models.DateField(_("constituted on"), null=True, blank=True)
    activated_on = models.DateField(_("activated on"), null=True, blank=True, db_index=True)
    phase_entered_on = models.DateField(
        _("entered current phase on"),
        null=True,
        blank=True,
        help_text=_("Set by the phase machine. The P2 gate measures 52 weeks from P1 entry against it."),
    )
    closed_on = models.DateField(_("closed on"), null=True, blank=True)
    closure_reason = models.TextField(_("closure reason"), blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_created_groups",
        verbose_name=_("created by"),
    )

    history = HistoricalRecords()

    objects = GroupQuerySet.as_manager()

    class Meta:
        verbose_name = _("SHG")
        verbose_name_plural = _("SHGs")
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(current_phase="") | models.Q(status__in=GroupStatus.phase_bearing()),
                name="wlt_phase_only_when_operating",
            ),
            models.CheckConstraint(
                condition=models.Q(activated_on__isnull=True) | models.Q(constituted_on__isnull=False),
                name="wlt_activated_needs_constituted",
            ),
        ]
        indexes = [
            models.Index(fields=["kebele", "status"]),
            models.Index(fields=["status", "current_phase"]),
        ]

    def __str__(self):
        return self.name

    # -- derived ----------------------------------------------------------

    @property
    def current_bylaw(self):
        """The version in force. One at a time — a partial unique index says so."""
        return self.bylaw_versions.filter(effective_to__isnull=True).first()

    def bylaw_on(self, on_date):
        """The version in force on a date.

        Compliance for months 1-7 must compute against the contribution that
        applied then, not the one a group raised in month 8. That is the whole
        reason bylaws are versioned rather than edited.
        """
        return (
            self.bylaw_versions.filter(effective_from__lte=on_date)
            .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=on_date))
            .first()
        )

    def roster_on(self, on_date):
        """Membership as it stood on a date — the denominator for every rate.

        Not the roster today. A woman who joined in month 6 must not make months
        1 to 5 look worse (assertions A13, A14).
        """
        return self.memberships.filter(joined_on__lte=on_date).filter(
            models.Q(exited_on__isnull=True) | models.Q(exited_on__gt=on_date)
        )

    @property
    def current_members(self):
        return self.memberships.filter(exited_on__isnull=True)

    def office_holder_on(self, role, on_date):
        return (
            self.office_holders.filter(role=role, from_date__lte=on_date)
            .filter(models.Q(to_date__isnull=True) | models.Q(to_date__gt=on_date))
            .first()
        )

    @property
    def has_treasurer(self):
        return self.office_holders.filter(role=OfficeRole.TREASURER, to_date__isnull=True).exists()


class BylawVersion(BaseModel):
    """The group's own rules, versioned rather than edited.

    A group raises its contribution in month 8; compliance for months 1 to 7
    still has to compute against the old figure. Superseding is closing the
    current row and opening the next (assertions A27, A28).
    """

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="bylaw_versions", verbose_name=_("group"))
    version_no = models.PositiveSmallIntegerField(_("version"))
    effective_from = models.DateField(_("effective from"))
    effective_to = models.DateField(_("effective to"), null=True, blank=True)

    meeting_cadence = models.CharField(_("meeting cadence"), max_length=16, choices=MeetingCadence.choices)
    meeting_day = models.CharField(_("meeting day"), max_length=16, blank=True)
    contribution_etb = models.DecimalField(_("contribution (ETB)"), max_digits=14, decimal_places=2)

    # Open question Q4. No default, and nullable, so the system cannot pick one.
    service_charge_basis = models.CharField(
        _("service charge basis"), max_length=24, choices=ServiceChargeBasis.choices, blank=True
    )
    service_charge_rate = models.DecimalField(
        _("service charge rate"), max_digits=6, decimal_places=4, null=True, blank=True
    )
    # Handbook 3.5 offers "service charge" for religious inclusivity while the
    # annex loan ledger still says "interest". The label is a per-group setting
    # and applies in every UI surface and export; the annexes need fixing.
    service_charge_label = models.CharField(
        _("service charge label"),
        max_length=32,
        default="service charge",
        help_text=_("What this group calls loan interest. Used verbatim in every screen and export."),
    )

    late_penalty_etb = models.DecimalField(
        _("late penalty (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    absence_penalty_etb = models.DecimalField(
        _("absence penalty (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    officer_rotation_months = models.PositiveSmallIntegerField(_("officer rotation (months)"), null=True, blank=True)
    loan_quorum_pct = models.PositiveSmallIntegerField(_("loan approval quorum (%)"), null=True, blank=True)
    max_concurrent_loans = models.PositiveSmallIntegerField(_("maximum concurrent loans"), null=True, blank=True)
    reserve_buffer_pct = models.PositiveSmallIntegerField(_("reserve buffer (%)"), null=True, blank=True)

    clauses_local_language = models.TextField(
        _("clauses in the local language"),
        blank=True,
        help_text=_("The group's own wording, stored alongside the structured fields rather than instead of them."),
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_recorded_bylaws",
        verbose_name=_("recorded by"),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("bylaw version")
        verbose_name_plural = _("bylaw versions")
        ordering = ["group", "-version_no"]
        constraints = [
            models.UniqueConstraint(fields=["group", "version_no"], name="wlt_bylaw_version_no_unique"),
            # A27: one version in force per group. Partial unique index, because
            # "in force" is the absence of an end date and not a flag.
            models.UniqueConstraint(
                fields=["group"],
                condition=models.Q(effective_to__isnull=True),
                name="wlt_bylaw_one_in_force_per_group",
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=models.F("effective_from")),
                name="wlt_bylaw_period_valid",
            ),
            models.CheckConstraint(condition=models.Q(contribution_etb__gt=0), name="wlt_bylaw_contribution_positive"),
        ]

    def __str__(self):
        return f"{self.group.name} bylaws v{self.version_no}"

    @property
    def cadence_days(self):
        return MeetingCadence.days(self.meeting_cadence)


class GroupMembership(BaseModel):
    """A dated range, never a flag.

    Every indicator computes against the roster as it stood on each meeting
    date, which an `is_active` boolean cannot express — and which is why one is
    deliberately absent here.
    """

    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="memberships", verbose_name=_("group"))
    person = models.ForeignKey(
        "youth.Youth", on_delete=models.PROTECT, related_name="wlt_memberships", verbose_name=_("member")
    )
    joined_on = models.DateField(_("joined on"))
    exited_on = models.DateField(_("exited on"), null=True, blank=True)
    exit_reason = models.CharField(_("exit reason"), max_length=16, choices=ExitReason.choices, blank=True)
    exit_note = models.TextField(_("exit note"), blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("group membership")
        verbose_name_plural = _("group memberships")
        ordering = ["group", "person__full_name"]
        constraints = [
            # A7. One open membership per person, across every group. The hybrid
            # enrolment route (D5) makes double assignment a realistic weekly
            # event, so it is refused by the database and not by a check
            # somebody has to remember to call.
            models.UniqueConstraint(
                fields=["person"],
                condition=models.Q(exited_on__isnull=True),
                name="wlt_membership_one_open_per_person",
            ),
            models.CheckConstraint(
                condition=models.Q(exited_on__isnull=True) | models.Q(exited_on__gte=models.F("joined_on")),
                name="wlt_membership_period_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(exited_on__isnull=True) | ~models.Q(exit_reason=""),
                name="wlt_membership_exit_needs_reason",
            ),
        ]
        indexes = [models.Index(fields=["group", "exited_on"])]

    def __str__(self):
        return f"{self.person.full_name} in {self.group.name}"


class OfficeHolder(BaseModel):
    """Chair, secretary and treasurer, rotating.

    "Who was treasurer on the date of that disbursement" is a question that gets
    asked, so a rotation closes the old term and opens a new one. Editing in
    place would answer it with today's officer (assertion A8).
    """

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="office_holders", verbose_name=_("group"))
    person = models.ForeignKey(
        "youth.Youth", on_delete=models.PROTECT, related_name="wlt_offices", verbose_name=_("office holder")
    )
    role = models.CharField(_("office"), max_length=16, choices=OfficeRole.choices)
    from_date = models.DateField(_("from"))
    to_date = models.DateField(_("to"), null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("office holder")
        verbose_name_plural = _("office holders")
        ordering = ["group", "role", "-from_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "role"],
                condition=models.Q(to_date__isnull=True),
                name="wlt_office_one_open_per_role",
            ),
            models.CheckConstraint(
                condition=models.Q(to_date__isnull=True) | models.Q(to_date__gt=models.F("from_date")),
                name="wlt_office_period_valid",
            ),
        ]

    def __str__(self):
        return f"{self.person.full_name}, {self.get_role_display()} of {self.group.name}"


class TrainingEvent(BaseModel):
    """Handbook 3.4 step 7. A Phase 1 evidence item, so it is data, not a note."""

    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="training_events", verbose_name=_("group"))
    module = models.CharField(_("module"), max_length=24, choices=TrainingModule.choices)
    held_on = models.DateField(_("held on"))
    facilitator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_training_events",
        verbose_name=_("facilitator"),
    )
    attendees = models.ManyToManyField(
        "youth.Youth", blank=True, related_name="wlt_trainings", verbose_name=_("attendees")
    )

    class Meta:
        verbose_name = _("training event")
        verbose_name_plural = _("training events")
        ordering = ["-held_on"]

    def __str__(self):
        return f"{self.get_module_display()} — {self.group.name}"


class ValidationOverride(BaseModel):
    """A soft warning a facilitator overrode during formation, with her reason.

    Reviewed at woreda level, and it also tells you which validation rules are
    wrong for the field. A rule overridden in nine kebeles out of ten is a rule
    that does not describe the programme.
    """

    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="validation_overrides", verbose_name=_("group")
    )
    rule_code = models.CharField(_("rule"), max_length=64, db_index=True)
    reason = models.TextField(_("reason"))
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_overrides",
        verbose_name=_("overridden by"),
    )

    class Meta:
        verbose_name = _("validation override")
        verbose_name_plural = _("validation overrides")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rule_code} on {self.group.name}"
