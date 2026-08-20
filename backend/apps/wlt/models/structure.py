"""Structural linkage — handoff decision D3, README §6.2, `sql/001` section F.

Structural linkage is *vertical and exclusive*: an SHG belongs to one CLA, a CLA
to one federation. It carries governance and delegates. Service linkage is
external and concurrent, carries obligations and money, and lives elsewhere —
in `wlt.models.linkage` and in the referral engine. They share nothing but the
word, which is why one generic `Linkage` table was rejected: it would have been
mostly nulls with a type column deciding which half applied.

Rows in `StructuralMembership` are created **only** by a `FormationEvent`. A CLA
is not something one group joins; it is something eight groups form together,
and modelling it as a per-record action loses the event that a woreda approved.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class BodyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    AT_RISK = "AT_RISK", _("At risk")
    DORMANT = "DORMANT", _("Dormant")
    DISSOLVED = "DISSOLVED", _("Dissolved")


class LegalStatus(models.TextChoices):
    """Where a federation stands with cooperative registration.

    Registration itself is a *linkage* with its own lifecycle, not an attribute:
    it can fail and it can lapse. This field is the cached headline; the
    `cooperative_registration` linkage is the record.
    """

    UNREGISTERED = "UNREGISTERED", _("Unregistered")
    IN_PROGRESS = "IN_PROGRESS", _("Registration in progress")
    REGISTERED = "REGISTERED", _("Registered")


class ParentType(models.TextChoices):
    CLA = "CLA", _("Cluster level association")
    FEDERATION = "FEDERATION", _("Federation")


class ChildType(models.TextChoices):
    GROUP = "GROUP", _("SHG")
    CLA = "CLA", _("Cluster level association")


class FormationStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    SUBMITTED = "SUBMITTED", _("Submitted")
    RETURNED = "RETURNED", _("Returned")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")
    EXPIRED = "EXPIRED", _("Expired")


class CLA(BaseModel):
    """Cluster Level Association: eight or more mature SHGs in one kebele."""

    name = models.CharField(_("name"), max_length=255)
    kebele = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="wlt_clas", verbose_name=_("kebele")
    )
    formed_on = models.DateField(_("formed on"))
    constitution_ref = models.CharField(_("constitution reference"), max_length=128, blank=True)
    meeting_cadence = models.CharField(
        _("meeting cadence"),
        max_length=16,
        choices=[("MONTHLY", _("Monthly")), ("QUARTERLY", _("Quarterly")), ("BIANNUAL", _("Twice a year"))],
        blank=True,
    )
    status = models.CharField(_("status"), max_length=16, choices=BodyStatus.choices, default=BodyStatus.ACTIVE)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("cluster level association")
        verbose_name_plural = _("cluster level associations")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def member_groups(self):
        from .formation import Group

        ids = StructuralMembership.objects.filter(
            parent_type=ParentType.CLA, parent_id=self.pk, child_type=ChildType.GROUP, exited_on__isnull=True
        ).values_list("child_id", flat=True)
        return Group.objects.filter(pk__in=ids)


class Federation(BaseModel):
    """Woreda-level body formed from CLAs. Schema only in the pre-pilot (D8).

    Phase 4 needs 10 CLAs of 8 to 12 SHGs — 80 to 120 groups inside one woreda —
    and the largest regional allocation is 80 groups across a whole region. It is
    arithmetically unreachable here, so the tables exist and the screens do not.
    Say so in the pilot documentation too, or the pilot will be judged against a
    milestone that was never achievable.
    """

    name = models.CharField(_("name"), max_length=255)
    woreda = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="wlt_federations", verbose_name=_("woreda")
    )
    formed_on = models.DateField(_("formed on"))
    constitution_ref = models.CharField(_("constitution reference"), max_length=128, blank=True)
    status = models.CharField(_("status"), max_length=16, choices=BodyStatus.choices, default=BodyStatus.ACTIVE)
    legal_status = models.CharField(
        _("legal status"), max_length=16, choices=LegalStatus.choices, default=LegalStatus.UNREGISTERED
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("federation")
        verbose_name_plural = _("federations")
        ordering = ["name"]

    def __str__(self):
        return self.name


class FormationEvent(BaseModel):
    """The multi-party event that creates a CLA or a federation (W1, W3).

    The hardest workflow in the module, because it is a many-to-one event rather
    than a per-record action: it stays open until every selected SHG has recorded
    its two delegates at its own meeting, and only then can it be submitted.
    """

    target_type = models.CharField(_("forms a"), max_length=16, choices=ParentType.choices)
    target_id = models.UUIDField(_("formed body"), null=True, blank=True, help_text=_("Populated on approval."))
    geography = models.ForeignKey(
        "locations.Location", on_delete=models.PROTECT, related_name="wlt_formation_events", verbose_name=_("place")
    )

    status = models.CharField(
        _("status"), max_length=16, choices=FormationStatus.choices, default=FormationStatus.OPEN, db_index=True
    )
    opened_on = models.DateField(_("opened on"))
    expires_on = models.DateField(_("expires on"))

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_submitted_formations",
        verbose_name=_("submitted by"),
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_decided_formations",
        verbose_name=_("decided by"),
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)
    gate_snapshot = models.JSONField(_("gate snapshot"), null=True, blank=True)
    return_reason = models.TextField(_("return reason"), blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("formation event")
        verbose_name_plural = _("formation events")
        ordering = ["-opened_on"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(submitted_by__isnull=True)
                | models.Q(decided_by__isnull=True)
                | ~models.Q(submitted_by=models.F("decided_by")),
                name="wlt_formation_no_self_approval",
            ),
        ]

    def __str__(self):
        return f"{self.get_target_type_display()} formation at {self.geography.name}"


class FormationCandidate(BaseModel):
    """One SHG (or CLA) selected into a formation event.

    Excluding one requires an explicit action with a reason, visible on that
    group's own record. A group that drops below threshold while the approval
    sits in a queue is flagged at approval time, never dropped quietly.
    """

    formation_event = models.ForeignKey(
        FormationEvent, on_delete=models.CASCADE, related_name="candidates", verbose_name=_("formation event")
    )
    child_type = models.CharField(_("child type"), max_length=16, choices=ChildType.choices)
    child_id = models.UUIDField(_("child"))
    included = models.BooleanField(_("included"), default=True)
    exclusion_reason = models.TextField(_("exclusion reason"), blank=True)

    class Meta:
        verbose_name = _("formation candidate")
        verbose_name_plural = _("formation candidates")
        constraints = [
            models.UniqueConstraint(
                fields=["formation_event", "child_type", "child_id"], name="wlt_formation_candidate_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(included=True) | ~models.Q(exclusion_reason=""),
                name="wlt_formation_exclusion_needs_reason",
            ),
        ]

    def __str__(self):
        return f"{self.child_type} {self.child_id}"


class StructuralMembership(BaseModel):
    """A child body inside a parent body, over a dated range.

    Two invariants, both in the database (A21, A22): one open parent per child,
    and a federation contains CLAs — never groups directly.
    """

    parent_type = models.CharField(_("parent type"), max_length=16, choices=ParentType.choices)
    parent_id = models.UUIDField(_("parent"))
    child_type = models.CharField(_("child type"), max_length=16, choices=ChildType.choices)
    child_id = models.UUIDField(_("child"))

    joined_on = models.DateField(_("joined on"))
    exited_on = models.DateField(_("exited on"), null=True, blank=True)
    exit_reason = models.TextField(_("exit reason"), blank=True)
    formation_event = models.ForeignKey(
        FormationEvent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="memberships",
        verbose_name=_("formation event"),
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("structural membership")
        verbose_name_plural = _("structural memberships")
        ordering = ["-joined_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["child_type", "child_id"],
                condition=models.Q(exited_on__isnull=True),
                name="wlt_structural_one_open_parent_per_child",
            ),
            models.CheckConstraint(
                condition=models.Q(parent_type=ParentType.CLA, child_type=ChildType.GROUP)
                | models.Q(parent_type=ParentType.FEDERATION, child_type=ChildType.CLA),
                name="wlt_structural_hierarchy_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(exited_on__isnull=True) | models.Q(exited_on__gte=models.F("joined_on")),
                name="wlt_structural_period_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(exited_on__isnull=True) | ~models.Q(exit_reason=""),
                name="wlt_structural_exit_needs_reason",
            ),
        ]
        indexes = [models.Index(fields=["parent_type", "parent_id", "exited_on"])]

    def __str__(self):
        return f"{self.child_type} {self.child_id} in {self.parent_type} {self.parent_id}"


class Delegate(BaseModel):
    """The two representatives each SHG elects into its CLA.

    Never edited in place. "Who represented this group at the CLA meeting that
    approved the loan" is a question that gets asked, and a rotation that
    overwrote the row could not answer it (W2, assertion A23).
    """

    cla = models.ForeignKey(CLA, on_delete=models.CASCADE, related_name="delegates", verbose_name=_("CLA"))
    group = models.ForeignKey("wlt.Group", on_delete=models.PROTECT, related_name="delegates", verbose_name=_("group"))
    person = models.ForeignKey(
        "youth.Youth", on_delete=models.PROTECT, related_name="wlt_delegacies", verbose_name=_("delegate")
    )
    elected_at_meeting = models.ForeignKey(
        "wlt.Meeting",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="delegate_elections",
        verbose_name=_("elected at"),
    )
    from_date = models.DateField(_("from"))
    to_date = models.DateField(_("to"), null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("delegate")
        verbose_name_plural = _("delegates")
        ordering = ["cla", "group", "-from_date"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(to_date__isnull=True) | models.Q(to_date__gt=models.F("from_date")),
                name="wlt_delegate_period_valid",
            ),
        ]
        indexes = [models.Index(fields=["cla", "group", "to_date"])]

    def __str__(self):
        return f"{self.person.full_name} for {self.group.name}"
