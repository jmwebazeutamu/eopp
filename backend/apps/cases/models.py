"""Case — spec §4.2. The entity a case manager opens first.

Wraps the youth's operational status: where they are, who owns them, and what
happens next. `last_activity_date` is the field the stall alert in §6 reads, so
every event that touches a case must call `touch()`.
"""

from datetime import date, timedelta

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class CaseStatus(models.TextChoices):
    """Spec §4.2: Active / Stalled / Referral Pending / Placed / Exited."""

    ACTIVE = "ACTIVE", _("Active")
    STALLED = "STALLED", _("Stalled")
    REFERRAL_PENDING = "REFERRAL_PENDING", _("Referral Pending")
    PLACED = "PLACED", _("Placed")
    EXITED = "EXITED", _("Exited")

    @classmethod
    def open_statuses(cls):
        """Everything except a closed case. Drives caseload counts."""
        return [cls.ACTIVE, cls.STALLED, cls.REFERRAL_PENDING, cls.PLACED]


class CaseQuerySet(models.QuerySet):
    def open(self):
        return self.filter(case_status__in=CaseStatus.open_statuses())

    def for_case_manager(self, user):
        return self.filter(case_manager=user)

    def in_woredas(self, woredas):
        return self.filter(woreda__in=woredas)

    def stalled_beyond_threshold(self, threshold_days=None, as_of=None):
        """Cases whose last activity predates the stall threshold (spec §6, §8).

        The Sprint 4 stall-detection job reads this. Kept on the queryset rather
        than in the task so the 'Stalled case alerts' dashboard in §8 and the
        alert job cannot drift apart.
        """
        threshold_days = threshold_days if threshold_days is not None else settings.STALL_ALERT_THRESHOLD_DAYS
        cutoff = (as_of or date.today()) - timedelta(days=threshold_days)
        # `lte`, not `lt`: a case last touched exactly `threshold_days` ago has
        # reached the threshold and must alert. This has to agree with
        # Case.is_stalled_by_threshold, which tests `days_since >= threshold` —
        # the two were off by one at the boundary, so the property called a case
        # stalled while the queryset that feeds the alert job skipped it.
        return self.open().filter(last_activity_date__lte=cutoff)


class CaseActionType(models.TextChoices):
    NEXT_ACTION = "NEXT_ACTION", _("Next action")
    FEEDBACK = "FEEDBACK", _("Feedback")
    FOLLOW_UP = "FOLLOW_UP", _("Follow-up")
    STATUS_NOTE = "STATUS_NOTE", _("Status note")


class CaseActionStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    DONE = "DONE", _("Done")
    SUPERSEDED = "SUPERSEDED", _("Superseded")


class Case(BaseModel):
    """Spec §4.2. `case_id` is `id`, per the §4 type-translation guide."""

    youth = models.OneToOneField(
        "youth.Youth",
        on_delete=models.PROTECT,
        related_name="case",
        verbose_name=_("youth"),
    )
    case_status = models.CharField(
        _("case status"),
        max_length=20,
        choices=CaseStatus.choices,
        default=CaseStatus.ACTIVE,
        db_index=True,
    )
    case_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="managed_cases",
        verbose_name=_("case manager"),
        help_text=_("Currently assigned case manager."),
    )

    # §4.2: "Denormalised from Youth for caseload filtering." Kept in sync by
    # save(); the youth's woreda remains the source of truth.
    woreda = models.CharField(_("woreda"), max_length=128, db_index=True)

    opened_date = models.DateField(_("opened date"), default=date.today, db_index=True)
    closed_date = models.DateField(_("closed date"), null=True, blank=True)
    exit_reason = models.TextField(_("exit reason"), blank=True)

    last_activity_date = models.DateField(
        _("last activity date"),
        default=date.today,
        db_index=True,
        help_text=_("System updated on any case event. Drives the stall alert."),
    )

    # §4.2: "Points to the pathway record marked current."
    #
    # Redundant with PathwayAssignment.is_current by design — the spec defines
    # both. PathwayAssignment.revise() is the only writer and maintains them
    # together; a partial unique index on the other side makes a second current
    # row impossible, so the two cannot silently disagree.
    current_pathway_assignment = models.ForeignKey(
        "cases.PathwayAssignment",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("current pathway assignment"),
    )

    # §4.2: "Answers Core Design Principle questions 10 and 11" — what happens
    # next, and who owns it. Surfaced on the case screen in Sprint 4.
    next_action = models.TextField(_("next action"), blank=True)
    next_action_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owned_next_actions",
        verbose_name=_("next action owner"),
    )

    history = HistoricalRecords()  # §9 audit trail

    objects = CaseQuerySet.as_manager()

    class Meta:
        verbose_name = _("case")
        verbose_name_plural = _("cases")
        ordering = ["-last_activity_date"]
        indexes = [
            models.Index(fields=["woreda", "case_status"]),
            models.Index(fields=["case_manager", "case_status"]),
            models.Index(fields=["last_activity_date"]),
        ]

    def __str__(self):
        return f"Case for {self.youth.full_name}"

    # -- derived ----------------------------------------------------------

    @property
    def is_open(self):
        return self.case_status in CaseStatus.open_statuses()

    @property
    def days_since_activity(self):
        return (date.today() - self.last_activity_date).days

    @property
    def is_stalled_by_threshold(self):
        """Whether the stall threshold has elapsed.

        Distinct from `case_status == STALLED`: this is the computed condition,
        that is the recorded state. The Sprint 4 job reads the first to set the
        second, so a case can satisfy this before anyone has acted on it.
        """
        return self.is_open and self.days_since_activity >= settings.STALL_ALERT_THRESHOLD_DAYS

    @property
    def current_profiling(self):
        """The latest profiling record — §3's "latest record is current"."""
        return self.profiling_records.first()  # ordering is -assessed_date, -created_at

    # -- behaviour --------------------------------------------------------

    def touch(self, when=None, save=True):
        """Record case activity. Every case event must call this.

        Spec §4.2 makes `last_activity_date` system-maintained, and §6 hangs the
        stall alert off it. Referral transitions (Sprint 3), follow-ups and
        training updates (Sprints 5-6) all route through here.
        """
        self.last_activity_date = when or date.today()
        if save:
            self.save(update_fields=["last_activity_date", "updated_at"])
        return self.last_activity_date

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        # §7 assigns caseload ownership to the youth case manager role. Any other
        # role in this field would give someone a caseload the access matrix
        # never grants them, leaving the case invisible to its own owner.
        if self.case_manager_id and self.case_manager.role != "CASE_MANAGER":
            errors["case_manager"] = _("The assigned case manager must hold the Youth case manager role.")

        if self.case_status == CaseStatus.EXITED:
            if not self.closed_date:
                errors["closed_date"] = _("An exited case needs a closed date.")
            if not self.exit_reason:
                errors["exit_reason"] = _("An exited case needs an exit reason.")
        elif self.closed_date:
            errors["closed_date"] = _("Only an exited case may have a closed date.")

        if self.closed_date and self.opened_date and self.closed_date < self.opened_date:
            errors["closed_date"] = _("A case cannot close before it opened.")

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Keep the denormalised woreda true to the youth record it copies.
        # Doing it here rather than in the serializer means the admin, the API
        # and future import scripts all stay consistent.
        if self.youth_id:
            youth_woreda = self.youth.woreda
            if self.woreda != youth_woreda:
                self.woreda = youth_woreda
                update_fields = kwargs.get("update_fields")
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {"woreda"}
        return super().save(*args, **kwargs)


class CaseAction(BaseModel):
    """Append-only case activity: next actions, feedback, and follow-up notes."""

    case = models.ForeignKey("cases.Case", on_delete=models.CASCADE, related_name="actions", verbose_name=_("case"))
    action_type = models.CharField(
        _("action type"), max_length=20, choices=CaseActionType.choices, default=CaseActionType.NEXT_ACTION
    )
    body = models.TextField(_("body"))
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_case_actions",
        verbose_name=_("created by"),
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_case_actions",
        verbose_name=_("assigned to"),
    )
    status = models.CharField(
        _("status"), max_length=20, choices=CaseActionStatus.choices, default=CaseActionStatus.OPEN
    )
    due_date = models.DateField(_("due date"), null=True, blank=True)
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    class Meta:
        verbose_name = _("case action")
        verbose_name_plural = _("case actions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["case", "action_type", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} for {self.case}"

    def clean(self):
        errors = {}
        if self.status == CaseActionStatus.DONE and not self.resolved_at:
            errors["resolved_at"] = _("A completed action needs a resolved timestamp.")
        if self.status == CaseActionStatus.OPEN and self.resolved_at:
            errors["resolved_at"] = _("Only completed actions may have a resolved timestamp.")
        if errors:
            raise ValidationError(errors)

    @classmethod
    def sync_case_summary(cls, case):
        """Keep Case.next_action and owner aligned with the latest open next action."""
        current = (
            cls.objects.filter(case=case, action_type=CaseActionType.NEXT_ACTION, status=CaseActionStatus.OPEN)
            .select_related("assigned_to")
            .order_by("-created_at")
            .first()
        )
        case.next_action = current.body if current else ""
        case.next_action_owner = current.assigned_to if current else None
        case.save(update_fields=["next_action", "next_action_owner", "updated_at"])


class Pathway(models.TextChoices):
    """The four programme pathways.

    Spec §4.4 `selected_pathway` and §4.3 `eligibility_flags` list the same four
    values, so one enum serves both: eligibility records which pathways a youth
    *may* take, the assignment records which one they *are* taking.
    """

    WAGE_EMPLOYMENT = "WAGE_EMPLOYMENT", _("Wage Employment")
    SELF_EMPLOYMENT = "SELF_EMPLOYMENT", _("Self-Employment")
    APPRENTICESHIP = "APPRENTICESHIP", _("Apprenticeship")
    TRAINING = "TRAINING", _("Training")


class ProfilingRecord(BaseModel):
    """Profiling and Eligibility Record — spec §4.3.

    §3 calls this "one-to-one with Case (may be revised; latest record is
    current)". Revision creates a new row rather than overwriting, so the
    relation is modelled as one-to-many and `Case.current_profiling` returns the
    most recent. Overwriting would destroy the assessment history that §9's
    audit requirement exists to preserve.
    """

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="profiling_records",
        verbose_name=_("case"),
    )

    work_history_summary = models.TextField(_("work history summary"), blank=True)
    skills_list = ArrayField(
        models.CharField(max_length=128),
        default=list,
        blank=True,
        verbose_name=_("skills"),
    )

    # TODO(open-question): spec §11 — "Define the vulnerability_index_score
    # methodology with M&E." Stored but never computed here; nothing reads it to
    # make a decision until the methodology is agreed.
    vulnerability_index_score = models.DecimalField(
        _("vulnerability index score"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Methodology pending definition with M&E (spec §11)."),
    )

    eligibility_flags = ArrayField(
        models.CharField(max_length=32, choices=Pathway.choices),
        default=list,
        verbose_name=_("eligibility flags"),
        help_text=_("Pathways this youth is eligible for."),
    )
    priority_flag = models.BooleanField(
        _("priority"),
        default=False,
        help_text=_("Marks a high-vulnerability case for priority handling."),
    )

    assessed_date = models.DateField(_("assessed date"), default=date.today, db_index=True)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="profiling_assessments",
        verbose_name=_("assessor"),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("profiling and eligibility record")
        verbose_name_plural = _("profiling and eligibility records")
        # Newest first: "latest record is current" is the whole access pattern.
        ordering = ["-assessed_date", "-created_at"]
        indexes = [models.Index(fields=["case", "-assessed_date"])]

    def __str__(self):
        return f"Profiling for {self.case.youth.full_name} on {self.assessed_date}"

    def clean(self):
        errors = {}

        # §4.3 marks eligibility_flags required. An empty list would leave the
        # Sprint 3 referral engine with no pathway to validate a referral against.
        if not self.eligibility_flags:
            errors["eligibility_flags"] = _("Record at least one pathway the youth is eligible for.")

        invalid = set(self.eligibility_flags or []) - set(Pathway.values)
        if invalid:
            errors["eligibility_flags"] = _("Unknown pathway(s): %(values)s.") % {"values": ", ".join(sorted(invalid))}

        if self.assessed_date and self.assessed_date > date.today():
            errors["assessed_date"] = _("Assessment date cannot be in the future.")

        if errors:
            raise ValidationError(errors)


class PathwayAssignmentQuerySet(models.QuerySet):
    def current(self):
        return self.filter(is_current=True)


class PathwayAssignment(BaseModel):
    """Pathway Assignment — spec §4.4. One-to-many with Case, one marked current."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="pathway_assignments",
        verbose_name=_("case"),
    )

    assessed_interests = models.TextField(_("assessed interests"), blank=True)
    capacities = models.TextField(_("capacities"), blank=True)
    barriers = models.TextField(_("barriers"), blank=True)

    selected_pathway = models.CharField(_("selected pathway"), max_length=32, choices=Pathway.choices, db_index=True)

    assessment_date = models.DateField(_("assessment date"), default=date.today, db_index=True)
    assessor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="pathway_assessments",
        verbose_name=_("assessor"),
    )

    is_current = models.BooleanField(_("is current"), default=True, db_index=True)

    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supersedes",
        verbose_name=_("superseded by"),
    )
    revision_reason = models.TextField(_("revision reason"), blank=True)

    history = HistoricalRecords()

    objects = PathwayAssignmentQuerySet.as_manager()

    class Meta:
        verbose_name = _("pathway assignment")
        verbose_name_plural = _("pathway assignments")
        ordering = ["-assessment_date", "-created_at"]
        constraints = [
            # §4.4: "Only one record per case set true." Enforced by a partial
            # unique index rather than application code, so a concurrent revision
            # cannot produce two current pathways for the same case.
            models.UniqueConstraint(
                fields=["case"],
                condition=models.Q(is_current=True),
                name="one_current_pathway_per_case",
            ),
        ]
        indexes = [models.Index(fields=["case", "-assessment_date"])]

    def __str__(self):
        return f"{self.get_selected_pathway_display()} for {self.case.youth.full_name}"

    def clean(self):
        errors = {}

        if self.assessment_date and self.assessment_date > date.today():
            errors["assessment_date"] = _("Assessment date cannot be in the future.")

        if self.superseded_by_id and self.is_current:
            errors["is_current"] = _("A superseded pathway cannot also be the current one.")

        if errors:
            raise ValidationError(errors)

    @transaction.atomic
    def revise(self, selected_pathway, assessor, revision_reason, **fields):
        """Supersede this assignment with a new current one (spec §4.4).

        The order is load-bearing. The partial unique index permits exactly one
        current row per case, and Postgres checks it per statement, so this
        assignment must be stood down before the replacement is inserted —
        inserting first would violate the constraint. Wrapped in a transaction
        so a failure cannot leave a case with no current pathway at all.
        """
        if not self.is_current:
            raise ValidationError("Only the current pathway assignment can be revised.")

        self.is_current = False
        self.revision_reason = revision_reason
        self.save(update_fields=["is_current", "revision_reason", "updated_at"])

        replacement = PathwayAssignment.objects.create(
            case=self.case,
            selected_pathway=selected_pathway,
            assessor=assessor,
            is_current=True,
            assessed_interests=fields.get("assessed_interests", self.assessed_interests),
            capacities=fields.get("capacities", self.capacities),
            barriers=fields.get("barriers", self.barriers),
            assessment_date=fields.get("assessment_date", date.today()),
        )

        self.superseded_by = replacement
        self.save(update_fields=["superseded_by", "updated_at"])

        # §4.2 keeps a pointer on the Case as well; both are updated together.
        self.case.current_pathway_assignment = replacement
        self.case.save(update_fields=["current_pathway_assignment", "updated_at"])
        self.case.touch()

        return replacement
