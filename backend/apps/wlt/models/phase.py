"""Phase machine and risk flags — handoff README §8, `sql/001` section E.

The system computes readiness; a human approves. Never auto-graduate — a phase
transition is a governance decision about a group of women, and the handbook
treats it as one.

Two properties carry the audit: the submitter cannot be the approver (A24, even
in a thin woreda office where one person holds both roles), and every decision
freezes the whole gate result it was taken on (A25, A26). `gate_snapshot` holds
the entire `GateResult`, not a summary, because the question asked two years
later is "on what numbers", and a boolean cannot answer it.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel

from .formation import Phase


class PhaseDirection(models.TextChoices):
    PROMOTION = "PROMOTION", _("Promotion")
    DEMOTION = "DEMOTION", _("Demotion")


class RiskReason(models.TextChoices):
    """The at-risk trigger list from DEFINITIONS.md.

    At risk is an early warning that is visible to the facilitator. It does not
    by itself move a group backwards — de-graduation is a separate decision with
    an approver behind it.
    """

    LOW_ATTENDANCE = "LOW_ATTENDANCE", _("Attendance below the floor")
    HIGH_PAR = "HIGH_PAR", _("PAR30 above the ceiling")
    MISSED_MEETINGS = "MISSED_MEETINGS", _("Two consecutive meetings missed")
    NO_TREASURER = "NO_TREASURER", _("No treasurer on record")
    EXTERNAL_DISTRESS = "EXTERNAL_DISTRESS", _("An external linkage is distressed or defaulted")
    UNBALANCED_TILL = "UNBALANCED_TILL", _("A meeting failed to reconcile")


class RiskSubjectType(models.TextChoices):
    GROUP = "GROUP", _("SHG")
    CLA = "CLA", _("Cluster level association")
    FEDERATION = "FEDERATION", _("Federation")


class PhaseEvent(BaseModel):
    """One phase decision. Immutable — enforced by trigger (A26).

    Django's `.save()` on an existing row and `.delete()` will raise. There is
    no correction path by design: a decision made wrongly is superseded by
    another decision, which is what an audit trail is.
    """

    group = models.ForeignKey(
        "wlt.Group", on_delete=models.CASCADE, related_name="phase_events", verbose_name=_("group")
    )
    from_phase = models.CharField(_("from phase"), max_length=2, choices=Phase.choices, blank=True)
    to_phase = models.CharField(_("to phase"), max_length=2, choices=Phase.choices)
    direction = models.CharField(
        _("direction"), max_length=16, choices=PhaseDirection.choices, default=PhaseDirection.PROMOTION
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_submitted_phase_events",
        verbose_name=_("submitted by"),
    )
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_decided_phase_events",
        verbose_name=_("decided by"),
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)

    policy_version = models.ForeignKey(
        "wlt.PolicyVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="phase_events",
        verbose_name=_("policy version"),
    )
    gate_snapshot = models.JSONField(
        _("gate snapshot"),
        help_text=_("Every condition, threshold and actual value at the moment of the decision."),
    )
    override_reason = models.TextField(_("override reason"), blank=True)
    formation_event = models.ForeignKey(
        "wlt.FormationEvent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="phase_events",
        verbose_name=_("formation event"),
        help_text=_("Set when the transition came from a CLA or federation formation."),
    )

    class Meta:
        verbose_name = _("phase event")
        verbose_name_plural = _("phase events")
        ordering = ["group", "-decided_at"]
        constraints = [
            # A24. Two columns compared in the database, because the case this
            # guards against is a thin office where the same person genuinely
            # holds both roles and the UI would happily let her.
            models.CheckConstraint(
                condition=models.Q(submitted_by__isnull=True)
                | models.Q(decided_by__isnull=True)
                | ~models.Q(submitted_by=models.F("decided_by")),
                name="wlt_phase_no_self_approval",
            ),
        ]
        indexes = [models.Index(fields=["group", "-decided_at"])]

    def __str__(self):
        return f"{self.group.name}: {self.from_phase or '—'} → {self.to_phase}"


class RiskFlagQuerySet(models.QuerySet):
    def open(self):
        return self.filter(cleared_on__isnull=True)

    def for_group(self, group):
        return self.filter(subject_type=RiskSubjectType.GROUP, subject_id=group.pk)


class RiskFlag(BaseModel):
    """An open early warning on a group, CLA or federation.

    The subject is a type plus an id rather than four nullable FKs: unlike the
    referral subject, nothing joins to this in the reporting layer, and it never
    carries an obligation. Where referential integrity earns its cost the module
    pays it (see `structural_membership`); here it would only add columns.
    """

    subject_type = models.CharField(_("subject type"), max_length=16, choices=RiskSubjectType.choices)
    subject_id = models.UUIDField(_("subject"))
    reason_code = models.CharField(_("reason"), max_length=24, choices=RiskReason.choices)
    raised_on = models.DateField(_("raised on"), db_index=True)
    cleared_on = models.DateField(_("cleared on"), null=True, blank=True)
    detail = models.JSONField(_("detail"), default=dict, blank=True)

    objects = RiskFlagQuerySet.as_manager()

    class Meta:
        verbose_name = _("risk flag")
        verbose_name_plural = _("risk flags")
        ordering = ["-raised_on"]
        constraints = [
            # Idempotent detection: one open flag per subject and reason, so a
            # nightly sweep that runs twice does not raise it twice. Partial,
            # because a cleared flag must be re-raisable when it recurs.
            models.UniqueConstraint(
                fields=["subject_type", "subject_id", "reason_code"],
                condition=models.Q(cleared_on__isnull=True),
                name="wlt_risk_one_open_per_reason",
            ),
        ]
        indexes = [models.Index(fields=["subject_type", "subject_id", "cleared_on"])]

    def __str__(self):
        return f"{self.get_reason_code_display()} ({self.subject_type})"
