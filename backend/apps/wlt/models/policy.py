"""Policy layer — WLT handoff decision D6, `sql/001` section A.

Every threshold FSCO can change lives here, effective-dated and geography-scoped.

The reason is in the handoff and it is not a style preference: the source
handbook describes itself as a living document, and it already states group size
three ways, the CLA threshold two ways and the federation threshold two ways.
Values will move mid-pilot. A constant in gate logic means a deploy per revision
and, worse, a phase decision taken in March under an 80% attendance rule that
cannot be explained in September when the rule reads 75%.

`PolicyVersion` is how that stays explicable: a decision records the *snapshot*
it was taken under, not a pointer to a table that has since changed.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class PolicyParameterQuerySet(models.QuerySet):
    def in_force(self, on_date):
        return self.filter(effective_from__lte=on_date).filter(
            models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=on_date)
        )


class PolicyParameter(BaseModel):
    """One threshold, in force over a date range, optionally scoped to a place.

    Values are JSON so one table can carry integers, booleans, decimals and the
    occasional string (`gate.credit.min_phase` is `"p4"`). The alternative —
    a column per type, or everything as text — either multiplies the table or
    loses the distinction between the number 8 and the string "8".
    """

    key = models.CharField(_("key"), max_length=128, db_index=True)
    scope_location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_policy_parameters",
        verbose_name=_("scope"),
        help_text=_("Leave empty for the global value. A more specific place overrides a less specific one."),
    )
    value = models.JSONField(_("value"))
    effective_from = models.DateField(_("effective from"), db_index=True)
    effective_to = models.DateField(
        _("effective to"),
        null=True,
        blank=True,
        help_text=_("Leave empty while this value is current. Closing a row is how a threshold is superseded."),
    )
    note = models.TextField(_("note"), blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wlt_policy_parameters",
        verbose_name=_("created by"),
    )

    history = HistoricalRecords()  # §9 audit trail: who changed a threshold, and when

    objects = PolicyParameterQuerySet.as_manager()

    class Meta:
        verbose_name = _("policy parameter")
        verbose_name_plural = _("policy parameters")
        ordering = ["key", "-effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=models.F("effective_from")),
                name="wlt_policy_period_valid",
            ),
        ]
        indexes = [models.Index(fields=["key", "effective_from"])]

    def __str__(self):
        where = self.scope_location.name if self.scope_location_id else _("global")
        return f"{self.key} = {self.value} ({where})"


class PolicyVersion(BaseModel):
    """A frozen snapshot of the whole parameter set at a decision moment.

    Referenced by every phase and linkage decision. It is the audit defence when
    somebody questions a graduation two years later: the decision is judged
    against the rules that applied, not the rules that apply.
    """

    label = models.CharField(_("label"), max_length=128)
    parameters = models.JSONField(_("parameters"))

    class Meta:
        verbose_name = _("policy version")
        verbose_name_plural = _("policy versions")
        ordering = ["-created_at"]

    def __str__(self):
        return self.label


class EnrolmentAllocation(BaseModel):
    """The pre-pilot ceiling, by region — handoff README §3.5.

    5,000 women across five regions, enforced rather than tracked in a
    spreadsheet three months late. Allocations are policy data, so a revision is
    an admin edit and not a deployment (backlog S1.4, assertion A31).
    """

    location = models.ForeignKey(
        "locations.Location",
        on_delete=models.PROTECT,
        related_name="wlt_allocations",
        verbose_name=_("region"),
    )
    phase_label = models.CharField(_("programme phase"), max_length=32, default="pre_pilot")
    target_members = models.PositiveIntegerField(_("target members"))
    target_groups = models.PositiveIntegerField(_("target groups"), null=True, blank=True)
    effective_from = models.DateField(_("effective from"))
    effective_to = models.DateField(_("effective to"), null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name = _("enrolment allocation")
        verbose_name_plural = _("enrolment allocations")
        ordering = ["location__name"]
        constraints = [
            models.CheckConstraint(condition=models.Q(target_members__gt=0), name="wlt_allocation_target_positive"),
        ]

    def __str__(self):
        return f"{self.location.name}: {self.target_members} ({self.phase_label})"
