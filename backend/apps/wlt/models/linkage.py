"""Service linkage — handoff decision D4 as adapted, README §6.3 to §6.6.

D4 says service linkage rides the existing referral engine. Half of that lands
here and half in `apps.referrals`, and the split is deliberate:

* **The subject generalises.** `referrals.Referral` now accepts a case, a youth,
  a group, a CLA or a federation, with typed nullable FK columns and an
  exactly-one check — the pattern D4 chose, for the reasons D4 gives. Category
  rows carry `allowed_subject_types`, which is what turns handbook §3.6's
  confidentiality norm into a database constraint: a protection referral permits
  a person only and can never be created against a group.

* **The lifecycle does not.** The platform's referral status field is spec §6.2
  transcribed — six states, partner-confirmation shaped. The gated linkage
  lifecycle is twelve states with screening, a multi-level approval chain and a
  distress cascade, and the two share no state but "active". Folding them into
  one field would mean every youth-side queryset, dashboard tier and alert job
  re-audited for group-subject leakage, which the handoff itself calls the
  highest-risk item in the plan.

So: `service_referral` and `protection_referral` are referral categories and ride
the engine unchanged (workflow W7). The gated types — savings account, market
offtake, cooperative membership and registration, credit facility — are
`ServiceLinkage` rows. They share the provider directory (`partners.Partner`),
the gate service and the reporting funnel; what is not shared is the state
machine, which was never the same machine.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel, TimeStampedModel


class LinkageSubjectType(models.TextChoices):
    GROUP = "GROUP", _("SHG")
    CLA = "CLA", _("Cluster level association")
    FEDERATION = "FEDERATION", _("Federation")


class LinkageStatus(models.TextChoices):
    """One lifecycle for every gated linkage type.

    Types vary by gate and approval chain, not by lifecycle. `BLOCKED` is a
    first-class state and not an error: it tells the facilitator exactly what
    the subject still needs to reach, which is the single most behaviour-changing
    screen in the module.
    """

    PROPOSED = "PROPOSED", _("Proposed")
    SCREENED = "SCREENED", _("Screened")
    BLOCKED = "BLOCKED", _("Blocked")
    PENDING_APPROVAL = "PENDING_APPROVAL", _("Pending approval")
    RETURNED = "RETURNED", _("Returned")
    APPROVED = "APPROVED", _("Approved")
    REJECTED = "REJECTED", _("Rejected")
    LAPSED = "LAPSED", _("Lapsed")
    ACTIVE = "ACTIVE", _("Active")
    DISTRESSED = "DISTRESSED", _("Distressed")
    DEFAULTED = "DEFAULTED", _("Defaulted")
    CLOSED = "CLOSED", _("Closed")

    @classmethod
    def terminal(cls):
        return (cls.REJECTED, cls.LAPSED, cls.CLOSED)

    @classmethod
    def open_statuses(cls):
        """Statuses in which the linkage still has a live obligation or claim."""
        return (cls.ACTIVE, cls.DISTRESSED, cls.DEFAULTED)


class LinkageTransitionError(ValidationError):
    """A move the lifecycle does not have."""


# The state machine of README §6.5, transcribed. Explicit application code in
# the domain layer, exactly as the platform's own referral engine is, so the
# rules stay testable and can be handed on at scale-up.
LINKAGE_TRANSITIONS = {
    LinkageStatus.PROPOSED: {LinkageStatus.SCREENED, LinkageStatus.BLOCKED, LinkageStatus.CLOSED},
    # Re-screening is how a blocked subject comes back once it has moved: the
    # facilitator does not raise a second proposal, so the block history and the
    # reasons that produced it stay on one record.
    # BLOCKED to BLOCKED is deliberate. Re-screening a subject that has not
    # moved far enough is a normal event, and it refreshes the reasons the
    # facilitator reads; refusing it would make "check again" an error.
    LinkageStatus.BLOCKED: {LinkageStatus.SCREENED, LinkageStatus.BLOCKED, LinkageStatus.CLOSED},
    LinkageStatus.SCREENED: {LinkageStatus.PENDING_APPROVAL, LinkageStatus.BLOCKED, LinkageStatus.CLOSED},
    LinkageStatus.PENDING_APPROVAL: {
        LinkageStatus.APPROVED,
        LinkageStatus.RETURNED,
        LinkageStatus.REJECTED,
        LinkageStatus.BLOCKED,
    },
    LinkageStatus.RETURNED: {LinkageStatus.SCREENED, LinkageStatus.CLOSED},
    LinkageStatus.APPROVED: {LinkageStatus.ACTIVE, LinkageStatus.LAPSED},
    LinkageStatus.ACTIVE: {LinkageStatus.DISTRESSED, LinkageStatus.CLOSED},
    LinkageStatus.DISTRESSED: {LinkageStatus.ACTIVE, LinkageStatus.DEFAULTED, LinkageStatus.CLOSED},
    LinkageStatus.DEFAULTED: {LinkageStatus.CLOSED},
    LinkageStatus.REJECTED: set(),
    LinkageStatus.LAPSED: set(),
    LinkageStatus.CLOSED: set(),
}


class ServiceLinkageTypeQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class ServiceLinkageType(TimeStampedModel):
    """The linkage taxonomy — data, not a class hierarchy.

    Seeded by `seed_wlt_taxonomy` and owned by the administrator thereafter,
    which is the same treatment §9 of the youth spec gives referral categories:
    a new pathway is a row, and the gate it must clear is a field on that row.
    """

    # Keyed by a readable code rather than a UUID, exactly as the youth-side
    # referral taxonomy is: linkage rows, seeds and reports all refer to a type
    # by code, and a human-readable key survives a database reload.
    code = models.SlugField(_("code"), max_length=64, primary_key=True)
    label = models.CharField(_("label"), max_length=128)
    description = models.TextField(_("description"), blank=True)

    allowed_subject_types = models.JSONField(
        _("allowed subject types"),
        default=list,
        help_text=_("Which subjects this linkage may be raised against, from GROUP, CLA and FEDERATION."),
    )
    min_phase = models.CharField(
        _("earliest phase"),
        max_length=2,
        blank=True,
        help_text=_("The phase a subject must have reached. Empty means any phase."),
    )
    approval_chain = models.JSONField(
        _("approval chain"),
        default=list,
        help_text=_("Roles that must approve, in order. An empty chain means the facilitator alone."),
    )
    restricted = models.BooleanField(
        _("restricted"),
        default=False,
        help_text=_("Confidential. Kept off shared timelines and aggregate exports."),
    )
    gate_set = models.CharField(
        _("gate set"),
        max_length=64,
        blank=True,
        help_text=_("Named set of conditions in the gate service, evaluated at screening and again at approval."),
    )
    lapse_days = models.PositiveSmallIntegerField(
        _("lapse after (days)"),
        null=True,
        blank=True,
        help_text=_("An approved linkage the counterparty never activates lapses after this many days."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=100)

    history = HistoricalRecords()

    objects = ServiceLinkageTypeQuerySet.as_manager()

    class Meta:
        verbose_name = _("service linkage type")
        verbose_name_plural = _("service linkage types")
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label

    def permits(self, subject_type):
        return subject_type in (self.allowed_subject_types or [])


class ServiceLinkageQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=LinkageStatus.open_statuses())

    def for_group(self, group):
        return self.filter(subject_group=group)

    def distressed(self):
        return self.filter(status__in=[LinkageStatus.DISTRESSED, LinkageStatus.DEFAULTED])


class ServiceLinkage(BaseModel):
    """A group, CLA or federation connected to an external provider.

    Subject is typed nullable FKs plus an exactly-one check, the pattern D4
    argues for: the reporting layer joins these in SQL, a deleted group must not
    leave a dangling obligation, and four columns index cleanly where a generic
    foreign key needs a contenttypes lookup per row.
    """

    linkage_type = models.ForeignKey(
        ServiceLinkageType, on_delete=models.PROTECT, related_name="linkages", verbose_name=_("type")
    )
    provider = models.ForeignKey(
        "partners.Partner",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_linkages",
        verbose_name=_("provider"),
        help_text=_("The bank, RUSACCO, cooperative or buyer on the other side."),
    )

    subject_group = models.ForeignKey(
        "wlt.Group",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="linkages",
        verbose_name=_("SHG"),
    )
    subject_cla = models.ForeignKey(
        "wlt.CLA", null=True, blank=True, on_delete=models.PROTECT, related_name="linkages", verbose_name=_("CLA")
    )
    subject_federation = models.ForeignKey(
        "wlt.Federation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="linkages",
        verbose_name=_("federation"),
    )
    subject_type = models.GeneratedField(
        expression=models.Case(
            models.When(subject_group__isnull=False, then=models.Value(LinkageSubjectType.GROUP)),
            models.When(subject_cla__isnull=False, then=models.Value(LinkageSubjectType.CLA)),
            models.When(subject_federation__isnull=False, then=models.Value(LinkageSubjectType.FEDERATION)),
            output_field=models.CharField(max_length=16),
        ),
        output_field=models.CharField(max_length=16),
        db_persist=True,
        verbose_name=_("subject type"),
    )

    status = models.CharField(
        _("status"), max_length=24, choices=LinkageStatus.choices, default=LinkageStatus.PROPOSED, db_index=True
    )
    opened_on = models.DateField(_("opened on"), db_index=True)
    approved_on = models.DateField(_("approved on"), null=True, blank=True)
    activated_on = models.DateField(_("activated on"), null=True, blank=True)
    closed_on = models.DateField(_("closed on"), null=True, blank=True)

    value_etb = models.DecimalField(_("value (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True)
    terms = models.JSONField(_("terms"), default=dict, blank=True)
    guarantors = models.JSONField(
        _("guarantors"), default=list, blank=True, help_text=_("Named at approval, for a credit facility.")
    )

    # The reasons the last screening produced. Kept on the row as well as in the
    # event log because the blocked screen reads it on every page load, and a
    # facilitator asking "what do we still need" should not wait on a join.
    block_reasons = models.JSONField(_("block reasons"), default=list, blank=True)

    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_initiated_linkages",
        verbose_name=_("initiated by"),
    )

    history = HistoricalRecords()

    objects = ServiceLinkageQuerySet.as_manager()

    class Meta:
        verbose_name = _("service linkage")
        verbose_name_plural = _("service linkages")
        ordering = ["-opened_on"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(subject_group__isnull=False, subject_cla__isnull=True, subject_federation__isnull=True)
                    | models.Q(subject_group__isnull=True, subject_cla__isnull=False, subject_federation__isnull=True)
                    | models.Q(subject_group__isnull=True, subject_cla__isnull=True, subject_federation__isnull=False)
                ),
                name="wlt_linkage_exactly_one_subject",
            ),
        ]
        indexes = [
            models.Index(fields=["linkage_type", "status"]),
            models.Index(fields=["subject_group", "status"]),
        ]

    def __str__(self):
        return f"{self.linkage_type.label} for {self.subject}"

    # -- subject ----------------------------------------------------------

    SUBJECT_FIELDS = ("subject_group", "subject_cla", "subject_federation")

    @property
    def subject(self):
        for field in self.SUBJECT_FIELDS:
            value = getattr(self, field)
            if value is not None:
                return value
        return None

    @property
    def resolved_subject_type(self):
        """The subject type without waiting for the database to generate it.

        `subject_type` is a stored generated column and is only populated after
        a refresh, so validation before the first save has to derive it. Same
        trap the handoff records for its BEFORE trigger.
        """
        if self.subject_group_id:
            return LinkageSubjectType.GROUP
        if self.subject_cla_id:
            return LinkageSubjectType.CLA
        if self.subject_federation_id:
            return LinkageSubjectType.FEDERATION
        return None

    @property
    def subject_group_ids(self):
        """The SHGs this linkage's distress would cascade to.

        A federation default is its member CLAs' exposure, and theirs is their
        member SHGs'. Returned as ids rather than objects because the caller
        raises risk flags, which key on ids.
        """
        from .structure import ChildType, ParentType, StructuralMembership

        if self.subject_group_id:
            return [self.subject_group_id]

        if self.subject_cla_id:
            parents = [(ParentType.CLA, self.subject_cla_id)]
        elif self.subject_federation_id:
            cla_ids = StructuralMembership.objects.filter(
                parent_type=ParentType.FEDERATION,
                parent_id=self.subject_federation_id,
                child_type=ChildType.CLA,
                exited_on__isnull=True,
            ).values_list("child_id", flat=True)
            parents = [(ParentType.CLA, cla_id) for cla_id in cla_ids]
        else:
            return []

        group_ids = []
        for parent_type, parent_id in parents:
            group_ids += list(
                StructuralMembership.objects.filter(
                    parent_type=parent_type,
                    parent_id=parent_id,
                    child_type=ChildType.GROUP,
                    exited_on__isnull=True,
                ).values_list("child_id", flat=True)
            )
        return group_ids

    # -- state machine ----------------------------------------------------

    @property
    def allowed_transitions(self):
        return sorted(LINKAGE_TRANSITIONS.get(self.status, set()))

    def can_transition_to(self, new_status):
        return new_status in LINKAGE_TRANSITIONS.get(self.status, set())

    @transaction.atomic
    def transition_to(self, new_status, actor=None, reason="", gate_snapshot=None, **fields):
        """Move to `new_status`, validating against README §6.5.

        The only supported way to change `status`: the serializer marks the
        field read-only for the same reason the referral engine does. Every move
        writes a `LinkageEvent` carrying the actor, the reason and the evidence
        the decision was taken on.
        """
        if not self.can_transition_to(new_status):
            allowed = ", ".join(self.allowed_transitions) or "none"
            raise LinkageTransitionError(
                _("Cannot move a linkage from %(from)s to %(to)s. Allowed from here: %(allowed)s.")
                % {
                    "from": self.get_status_display(),
                    "to": LinkageStatus(new_status).label,
                    "allowed": allowed,
                }
            )

        previous = self.status
        for field, value in fields.items():
            setattr(self, field, value)

        today = timezone.localdate()
        if new_status == LinkageStatus.APPROVED and not self.approved_on:
            self.approved_on = today
        if new_status == LinkageStatus.ACTIVE and not self.activated_on:
            self.activated_on = today
        if new_status in LinkageStatus.terminal() and not self.closed_on:
            self.closed_on = today

        self.status = new_status
        self.save()

        LinkageEvent.objects.create(
            linkage=self,
            from_status=previous,
            to_status=new_status,
            actor=actor,
            reason=reason,
            gate_snapshot=gate_snapshot,
        )
        return self


class LinkageEvent(BaseModel):
    """One transition, with the evidence it was taken on. Append-only.

    Every transition writes an immutable snapshot: indicator values, policy
    version, actor, timestamp. Gates are evaluated at screening **and again at
    approval**, and both results are here — a subject can drift below threshold
    while an approval sits in a queue, and approving against stale numbers is
    how bad credit linkages happen.
    """

    linkage = models.ForeignKey(
        ServiceLinkage, on_delete=models.CASCADE, related_name="events", verbose_name=_("linkage")
    )
    from_status = models.CharField(_("from"), max_length=24, choices=LinkageStatus.choices, blank=True)
    to_status = models.CharField(_("to"), max_length=24, choices=LinkageStatus.choices)
    occurred_at = models.DateTimeField(_("occurred at"), auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_linkage_events",
        verbose_name=_("actor"),
    )
    reason = models.TextField(_("reason"), blank=True)
    gate_snapshot = models.JSONField(_("gate snapshot"), null=True, blank=True)

    class Meta:
        verbose_name = _("linkage event")
        verbose_name_plural = _("linkage events")
        ordering = ["linkage", "occurred_at"]

    def __str__(self):
        return f"{self.from_status or '—'} → {self.to_status}"


class LinkageApproval(BaseModel):
    """One step of the approval chain.

    Chains are per type and can be three levels long. Recording each step
    separately is what makes "no self-approval" checkable at every level rather
    than only at the last, and what lets an override escalate by one level
    instead of skipping the rest.
    """

    linkage = models.ForeignKey(
        ServiceLinkage, on_delete=models.CASCADE, related_name="approvals", verbose_name=_("linkage")
    )
    level = models.PositiveSmallIntegerField(_("level"))
    required_role = models.CharField(_("required role"), max_length=32)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_linkage_approvals",
        verbose_name=_("decided by"),
    )
    decided_at = models.DateTimeField(_("decided at"), null=True, blank=True)
    decision = models.CharField(
        _("decision"),
        max_length=16,
        blank=True,
        choices=[("APPROVED", _("Approved")), ("RETURNED", _("Returned")), ("REJECTED", _("Rejected"))],
    )
    note = models.TextField(_("note"), blank=True)
    is_escalation = models.BooleanField(
        _("added by an override"),
        default=False,
        help_text=_("An override of a blocked gate escalates the chain by one level."),
    )

    class Meta:
        verbose_name = _("linkage approval")
        verbose_name_plural = _("linkage approvals")
        ordering = ["linkage", "level"]
        constraints = [
            models.UniqueConstraint(fields=["linkage", "level"], name="wlt_linkage_approval_level_unique"),
        ]

    def __str__(self):
        return f"level {self.level}: {self.decision or _('pending')}"


class LinkageObligation(BaseModel):
    """A scheduled payment a linkage commits its subject to.

    Schema for stage 9 (credit facility, post-pilot) and used today by the
    savings and market types where a delivery or a deposit is promised on a
    date. A missed obligation is what moves a linkage to `DISTRESSED`; without a
    row to miss, distress could only ever be set by hand.
    """

    linkage = models.ForeignKey(
        ServiceLinkage, on_delete=models.CASCADE, related_name="obligations", verbose_name=_("linkage")
    )
    due_on = models.DateField(_("due on"), db_index=True)
    description = models.CharField(_("description"), max_length=255, blank=True)
    amount_etb = models.DecimalField(_("amount (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True)
    settled_on = models.DateField(_("settled on"), null=True, blank=True)
    settled_amount_etb = models.DecimalField(
        _("settled amount (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )

    class Meta:
        verbose_name = _("linkage obligation")
        verbose_name_plural = _("linkage obligations")
        ordering = ["linkage", "due_on"]

    def __str__(self):
        return f"{self.due_on}: {self.description or self.amount_etb}"
