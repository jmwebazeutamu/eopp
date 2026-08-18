"""Referral — spec §4.6, the central entity.

Every referral of every category and trigger is one row here. The chain fields
(`parent_referral`, `replacement_referral`) and `parallel_group_id` are what let
the system reconstruct the referral stack (§6.4).

The state machine lives in this module as explicit application code, per §2.3:
never database triggers or stored procedures, so the business rules stay
auditable and testable and can be handed to a government IT team at scale-up.
"""

import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel

from .taxonomy import FailureReasonCode, OutcomeType, ReferralCategory  # noqa: F401  (re-exported)


class ReferralTrigger(models.TextChoices):
    """Spec §5.2. How the referral came to exist.

    In code rather than configuration: each value carries state machine
    behaviour (Onward and Replacement are system-prompted and set
    `parent_referral`), so a new one could not be handled without new code.
    """

    MANUAL = "MANUAL", _("Manual")
    ONWARD = "ONWARD", _("Onward")
    REPLACEMENT = "REPLACEMENT", _("Replacement")


class ReferralStatus(models.TextChoices):
    """Spec §6.1.

    §4.6 abbreviates the first value to "Pending"; §6.1 is the state machine's
    source of truth and names it "Pending Confirmation", which is what is used
    here — it says what the referral is waiting on.
    """

    PENDING_CONFIRMATION = "PENDING_CONFIRMATION", _("Pending Confirmation")
    ACTIVE = "ACTIVE", _("Active")
    COMPLETED = "COMPLETED", _("Completed")
    FAILED = "FAILED", _("Failed")
    REPLACED = "REPLACED", _("Replaced")
    CANCELLED = "CANCELLED", _("Cancelled")

    @classmethod
    def terminal(cls):
        return {cls.COMPLETED, cls.FAILED, cls.REPLACED, cls.CANCELLED}

    @classmethod
    def open_statuses(cls):
        return {cls.PENDING_CONFIRMATION, cls.ACTIVE}


class VerificationSource(models.TextChoices):
    """How an outcome was verified — OQ-2, settled 2026-08-18.

    Without this every outcome is self-reported, and a self-reported placement
    rate is an aspiration rather than a result. §8.3 of the dashboard handoff
    makes the externally-verified subset the reportable headline, which is not
    expressible until the source is recorded as data rather than as the free
    text in `outcome_verification_method`.

    Ordered weakest to strongest; `is_external` in the model reads the split.
    """

    SELF_REPORTED = "SELF_REPORTED", _("Self-reported by the youth")
    PROVIDER_CONFIRMED = "PROVIDER_CONFIRMED", _("Confirmed by the receiving provider")
    EMPLOYER_CONFIRMED = "EMPLOYER_CONFIRMED", _("Confirmed by the employer")
    DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED", _("Verified against a document")


class ConfirmationStatus(models.TextChoices):
    """Spec §4.6. The receiving partner's response."""

    PENDING = "PENDING", _("Pending Confirmation")
    CONFIRMED = "CONFIRMED", _("Confirmed")
    DECLINED = "DECLINED", _("Declined")


class TransitionError(ValidationError):
    """An attempt to move a referral along an edge the §6.2 table does not have."""


class Transition:
    """One row of the spec §6.2 table."""

    def __init__(self, to_status, description, requires=(), sets_confirmation=None):
        self.to_status = to_status
        self.description = description
        self.requires = tuple(requires)
        self.sets_confirmation = sets_confirmation


# Spec §6.2, transcribed. Keys are the `from` status; None is a referral that
# does not exist yet, which the create path handles. Every edge the platform
# permits is here — `transition_to` refuses anything absent, so an unlisted move
# fails loudly instead of silently corrupting the stack.
TRANSITIONS = {
    ReferralStatus.PENDING_CONFIRMATION: {
        ReferralStatus.ACTIVE: Transition(
            ReferralStatus.ACTIVE,
            "Receiving partner confirms.",
            sets_confirmation=ConfirmationStatus.CONFIRMED,
        ),
        ReferralStatus.FAILED: Transition(
            ReferralStatus.FAILED,
            "Receiving partner declines.",
            requires=("failure_reason_code",),
            sets_confirmation=ConfirmationStatus.DECLINED,
        ),
        ReferralStatus.CANCELLED: Transition(
            ReferralStatus.CANCELLED,
            "Case manager withdraws before confirmation.",
        ),
    },
    ReferralStatus.ACTIVE: {
        ReferralStatus.COMPLETED: Transition(
            ReferralStatus.COMPLETED,
            "Outcome recorded and verified via follow-up visit.",
            requires=("outcome_type",),
        ),
        ReferralStatus.FAILED: Transition(
            ReferralStatus.FAILED,
            "Non-attendance, dropout, or other failure identified.",
            requires=("failure_reason_code",),
        ),
    },
    ReferralStatus.FAILED: {
        ReferralStatus.REPLACED: Transition(
            ReferralStatus.REPLACED,
            "Case manager confirms the Replacement prompt.",
        ),
    },
    # COMPLETED is terminal for this referral. Confirming the Onward prompt
    # creates a *new* referral (§6.2 last row) and leaves this one Completed.
    ReferralStatus.COMPLETED: {},
    ReferralStatus.REPLACED: {},
    ReferralStatus.CANCELLED: {},
}


class ReferralQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status__in=ReferralStatus.open_statuses())

    def active(self):
        return self.filter(status=ReferralStatus.ACTIVE)

    def for_case(self, case):
        return self.filter(case=case)

    def with_recorded_outcome(self):
        """Completed with an outcome recorded. **Recorded is not verified.**"""
        return self.filter(status=ReferralStatus.COMPLETED, outcome_type__isnull=False)

    def externally_verified(self):
        """Outcomes somebody other than the youth stood behind.

        A blank source is **not** verified. The dashboards used to test
        `outcome_verified_by IS NOT NULL`, which only says a staff member signed
        the record off — 59 self-reported outcomes were being counted as
        verified, and the loop-closure rate read 50% where the verified figure
        was 32%. A self-reported placement rate is an aspiration.
        """
        return self.with_recorded_outcome().exclude(verification_source__in=["", VerificationSource.SELF_REPORTED])

    def placements(self):
        """**The** definition of a placement. Nothing else may restate it.

        A placement is a referral that completed with an outcome the
        administrator has flagged `counts_as_placement` — job, apprenticeship or
        enterprise. It is deliberately a queryset rather than a constant so the
        flag stays admin-editable configuration (§9) and every consumer picks up
        a change without a deploy.

        Four separate copies of this filter had drifted across the dashboard
        modules, three counting referrals and one counting youth, which is how
        one screen came to show three different placement totals.
        """
        return self.filter(status=ReferralStatus.COMPLETED, outcome_type__counts_as_placement=True)

    def placed_youth_ids(self):
        """Distinct youth with at least one placement.

        The unit that matters for every programme and donor figure: a youth
        placed twice is one young person in work, not two.
        """
        return set(self.placements().values_list("case__youth_id", flat=True))

    def placed_case_ids(self):
        return set(self.placements().values_list("case_id", flat=True))

    def counting_toward_parallel_cap(self):
        """Active referrals that occupy a concurrency slot (spec §6.3).

        Categories flagged `exempt_from_parallel_cap` — Complementary Service by
        default — run as a third stream and are excluded.
        """
        return self.active().filter(referral_category__exempt_from_parallel_cap=False)

    def awaiting_onward_prompt(self):
        """Completed referrals that have not yet spawned an onward referral.

        Spec §6.2 generates an Onward prompt on completion. The prompt is not
        stored: it is this condition. Sprint 4's alert job materialises these
        into Alert rows, and confirming one creates the child referral, which
        removes it from this queryset.
        """
        return self.filter(status=ReferralStatus.COMPLETED, children__isnull=True)

    def awaiting_replacement_prompt(self):
        """Failed referrals not yet replaced (spec §6.2).

        A referral moves to Replaced once its replacement exists, so filtering
        on FAILED is sufficient — but `replacement_referral__isnull` is kept
        explicit so a row left inconsistent by a data fix cannot re-prompt.
        """
        return self.filter(status=ReferralStatus.FAILED, replacement_referral__isnull=True)


class Referral(BaseModel):
    """Spec §4.6. `referral_id` is `id`, per the §4 type-translation guide."""

    case = models.ForeignKey(
        "cases.Case",
        on_delete=models.CASCADE,
        related_name="referrals",
        verbose_name=_("case"),
    )

    referral_category = models.ForeignKey(
        "referrals.ReferralCategory",
        on_delete=models.PROTECT,
        related_name="referrals",
        verbose_name=_("referral category"),
    )
    referral_trigger = models.CharField(
        _("referral trigger"),
        max_length=16,
        choices=ReferralTrigger.choices,
        default=ReferralTrigger.MANUAL,
        db_index=True,
    )

    # §4.6 marks both System-set. is_parallel is a historical fact — that this
    # referral ran concurrently with another — and is not cleared when the other
    # one closes; "currently parallel" is a query over Active rows (§6.4).
    is_parallel = models.BooleanField(_("is parallel"), default=False)
    parallel_group_id = models.UUIDField(_("parallel group"), null=True, blank=True, db_index=True)

    parent_referral = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        verbose_name=_("parent referral"),
        help_text=_("Set for Onward and Replacement referrals; links to the referral that preceded it."),
    )
    replacement_referral = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="replaces",
        verbose_name=_("replacement referral"),
        help_text=_("Set once this referral has been replaced; forward link."),
    )

    receiving_partner = models.ForeignKey(
        "partners.Partner",
        on_delete=models.PROTECT,
        related_name="received_referrals",
        verbose_name=_("receiving partner"),
    )
    receiving_contact_name = models.CharField(_("receiving contact"), max_length=255, blank=True)

    initiated_date = models.DateField(_("initiated date"), default=date.today, db_index=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_referrals",
        verbose_name=_("initiated by"),
    )

    confirmation_status = models.CharField(
        _("confirmation status"),
        max_length=16,
        choices=ConfirmationStatus.choices,
        default=ConfirmationStatus.PENDING,
        db_index=True,
    )
    confirmed_date = models.DateField(_("confirmed date"), null=True, blank=True)
    # §4.6 types confirmed_by as Text, not a User reference: the person
    # confirming is often partner-side staff without a platform account. This
    # names whoever at the partner gave the answer.
    confirmed_by = models.CharField(_("confirmed by"), max_length=255, blank=True)

    # Who typed it in, which is not always who said it.
    #
    # A case manager may record a partner's confirmation on their behalf —
    # decided 2026-08-18, because partners in the pilot woredas may not log in
    # for days and a referral nobody can confirm sits in Pending forever.
    #
    # The two fields have to stay separate. Fold them together and partner
    # responsiveness stops being measurable: a partner who never answers looks
    # identical to one who answers promptly, because staff kept the queue moving
    # on their behalf. `confirmed_by` is the partner's word; this is the
    # platform account that entered it, and it is NULL when the partner
    # confirmed through their own login.
    confirmation_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_confirmations",
        verbose_name=_("confirmation recorded by"),
        help_text=_("Set when a staff member recorded the partner's answer rather than the partner entering it."),
    )

    status = models.CharField(
        _("status"),
        max_length=24,
        choices=ReferralStatus.choices,
        default=ReferralStatus.PENDING_CONFIRMATION,
        db_index=True,
    )

    outcome_type = models.ForeignKey(
        "referrals.OutcomeType",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="referrals",
        verbose_name=_("outcome type"),
    )
    outcome_date = models.DateField(_("outcome date"), null=True, blank=True)
    outcome_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_referral_outcomes",
        verbose_name=_("outcome verified by"),
    )
    outcome_verification_method = models.CharField(_("verification method"), max_length=255, blank=True)
    # OQ-2. The free-text method above says *how*; this says how strong it is,
    # in a form a report can filter on.
    verification_source = models.CharField(
        _("verification source"),
        max_length=24,
        choices=VerificationSource.choices,
        blank=True,
        db_index=True,
        help_text=_("Who verified the outcome. Anything but self-reported counts as externally verified."),
    )

    # OQ-1. The date the youth actually presented to the partner.
    #
    # Without it the pipeline cannot separate "the partner accepted" from "the
    # youth turned up", and that gap is the largest single loss in the pilot —
    # 50% between confirmation and outcome, at a median of 54 days. The stage
    # renders as not-yet-instrumented until this is populated, never as zero.
    service_start_date = models.DateField(
        _("service start date"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("The date the youth presented to the receiving partner."),
    )

    failure_reason_code = models.ForeignKey(
        "referrals.FailureReasonCode",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="referrals",
        verbose_name=_("failure reason"),
    )
    failure_date = models.DateField(_("failure date"), null=True, blank=True)

    notes = models.TextField(_("notes"), blank=True)

    history = HistoricalRecords()  # §9 audit trail

    objects = ReferralQuerySet.as_manager()

    class Meta:
        constraints = [
            # A confirmation date without a confirmation is not a state this
            # domain has. Enforced in the database because the write path that
            # produced it was subtle enough to survive review.
            models.CheckConstraint(
                condition=~models.Q(confirmation_status="PENDING", confirmed_date__isnull=False),
                name="referral_no_confirmed_date_while_pending",
            ),
        ]
        verbose_name = _("referral")
        verbose_name_plural = _("referrals")
        ordering = ["-initiated_date", "-created_at"]
        indexes = [
            models.Index(fields=["case", "-initiated_date"]),
            models.Index(fields=["status", "referral_category"]),
            models.Index(fields=["receiving_partner", "status"]),
            models.Index(fields=["parallel_group_id"]),
        ]

    def __str__(self):
        return f"{self.referral_category.label} referral for {self.case.youth.full_name}"

    @property
    def is_externally_verified(self):
        """Whether anyone other than the youth stood behind this outcome.

        Explicit, so no consumer has to pattern-match the free text in
        `outcome_verification_method`, which holds values like "Provider
        register", "interview" and "Follow-up visit" and cannot be read reliably.
        """
        return bool(self.verification_source) and self.verification_source != VerificationSource.SELF_REPORTED

    # -- derived ----------------------------------------------------------

    @property
    def is_open(self):
        return self.status in ReferralStatus.open_statuses()

    @property
    def is_terminal(self):
        return self.status in ReferralStatus.terminal()

    @property
    def allowed_transitions(self):
        """Statuses this referral may move to right now (spec §6.2)."""
        return sorted(TRANSITIONS.get(self.status, {}).keys())

    @property
    def counts_toward_parallel_cap(self):
        """Whether this referral occupies one of the two concurrency slots.

        TODO(open-question): spec §6.3 / §11 — Complementary Service sitting
        outside the cap is the stated working default, not an agreed policy.
        Driven by a flag on the category so the decision can be reversed in the
        admin rather than in code.
        """
        return not self.referral_category.exempt_from_parallel_cap

    # -- state machine (spec §6.2) ----------------------------------------

    def can_transition_to(self, new_status):
        return new_status in TRANSITIONS.get(self.status, {})

    @transaction.atomic
    def transition_to(self, new_status, actor=None, **kwargs):
        """Move this referral to `new_status`, validating against the §6.2 table.

        Raises TransitionError on any edge the table does not contain. This is
        the only supported way to change `status` — writing the field directly
        bypasses the required-field checks, the parallel-group bookkeeping and
        the case activity stamp.
        """
        # Re-read the concurrency fields under a row lock before deciding
        # anything. Two reasons, both load-bearing:
        #
        #  1. Staleness. `_join_or_open_parallel_group` stamps the group onto
        #     *sibling* rows, so a caller holding an instance loaded before that
        #     happened would save its stale is_parallel/parallel_group_id back
        #     over the database and erase the pairing §8 reports on.
        #  2. Races. Two partner confirmations arriving together would otherwise
        #     both read one active sibling, both pass the §6.3 cap check, and
        #     leave the case with three active referrals.
        #
        # Only these three fields are re-read — the caller's other unsaved edits
        # are theirs to keep, and status is what this method is about to change.
        if self.pk:
            locked = (
                Referral.objects.select_for_update()
                .filter(pk=self.pk)
                .values("status", "is_parallel", "parallel_group_id")
                .first()
            )
            if locked:
                self.status = locked["status"]
                self.is_parallel = locked["is_parallel"]
                self.parallel_group_id = locked["parallel_group_id"]

        transition = TRANSITIONS.get(self.status, {}).get(new_status)
        if transition is None:
            allowed = ", ".join(self.allowed_transitions) or "none"
            raise TransitionError(
                f"Cannot move a referral from {self.get_status_display()} to "
                f"{ReferralStatus(new_status).label}. Allowed from here: {allowed}."
            )

        # Apply the caller's field updates before checking requirements, so
        # "required on this transition" is evaluated against the final state.
        #
        # A failure past this point rolls the database back but leaves the
        # *instance* mutated, and a later transition on the same object then
        # persists those orphaned values. That is how two referrals came to hold
        # a `confirmed_date` while still Pending: the confirmation was refused
        # by the §6.3 cap, the caller caught it and cancelled the referral
        # instead, and the cancel wrote the confirmed date the refused
        # transition had set. `_restore_on_failure` below undoes the in-memory
        # half of the rollback.
        applied = {field: getattr(self, field, None) for field in kwargs}
        for field, value in kwargs.items():
            setattr(self, field, value)

        def _restore_on_failure(exc):
            """Put the instance back as it was, then re-raise.

            The transaction has already rolled the row back; this rolls the
            object back to match, so a caller that recovers from a refused
            transition is not holding values the database rejected.
            """
            for name, previous in applied.items():
                setattr(self, name, previous)
            raise exc

        missing = [
            field for field in transition.requires if not getattr(self, f"{field}_id", getattr(self, field, None))
        ]
        if missing:
            _restore_on_failure(
                ValidationError({field: _("Required when moving to this status.") for field in missing})
            )

        if new_status == ReferralStatus.ACTIVE:
            try:
                self._join_or_open_parallel_group()
            except Exception as exc:  # the §6.3 cap, and anything else that refuses
                _restore_on_failure(exc)

        if new_status == ReferralStatus.COMPLETED and not self.outcome_date:
            self.outcome_date = date.today()
        if new_status == ReferralStatus.FAILED and not self.failure_date:
            self.failure_date = date.today()

        if transition.sets_confirmation:
            self.confirmation_status = transition.sets_confirmation
            if transition.sets_confirmation == ConfirmationStatus.CONFIRMED and not self.confirmed_date:
                self.confirmed_date = date.today()
            # An actor with a platform account is staff recording the partner's
            # answer; a partner confirming through their own login is
            # `PARTNER_STAFF` and leaves this null, which is what keeps the
            # response-time metrics honest.
            if transition.sets_confirmation and actor is not None and self.confirmation_recorded_by_id is None:
                from apps.users.models import Role

                if getattr(actor, "role", None) != Role.PARTNER_STAFF:
                    self.confirmation_recorded_by = actor

        if new_status == ReferralStatus.COMPLETED and actor and not self.outcome_verified_by_id:
            self.outcome_verified_by = actor

        self.status = new_status
        self.full_clean(exclude=["parallel_group_id"], validate_unique=False)
        self.save()

        # A recorded placement moves the case to Placed.
        #
        # Source of truth is the referral outcome, not `case_status`: the
        # outcome carries a date, a verifier and a verification source, and the
        # status carries none of those. The status is derived from it here, in
        # the state machine, because that is the only route a referral is
        # allowed to change (§6.2) and so the only place the derivation cannot
        # be bypassed.
        #
        # Deliberately one-way. Removing an outcome does NOT demote the case:
        # `PLACED` is also a judgement a case manager may set by hand (§4.2),
        # and silently overwriting that would lose a human decision to a
        # cascade. `manage.py reconcile_case_placement` reports those instead.
        if new_status == ReferralStatus.COMPLETED and self.outcome_type_id:
            from apps.cases.models import CaseStatus

            if self.outcome_type.counts_as_placement and self.case.case_status != CaseStatus.PLACED:
                self.case.case_status = CaseStatus.PLACED
                self.case.save(update_fields=["case_status", "last_activity_date", "updated_at"])

        # Any referral movement is case activity (§4.2 last_activity_date).
        self.case.touch()
        return self

    def _join_or_open_parallel_group(self):
        """Apply the §6.3 concurrency rule as this referral becomes Active.

        Per §6.2: "if another referral is already Active for this case, assign
        shared parallel_group_id".
        """
        if not self.counts_toward_parallel_cap:
            # Exempt categories run as a third stream: no slot, no group.
            return

        siblings = list(Referral.objects.counting_toward_parallel_cap().filter(case=self.case).exclude(pk=self.pk))

        if len(siblings) >= settings.MAX_PARALLEL_ACTIVE_REFERRALS:
            raise ValidationError(
                {
                    "status": _(
                        "This case already has %(count)s active referrals, the maximum allowed to run in "
                        "parallel. Complete, fail, or cancel one first."
                    )
                    % {"count": len(siblings)}
                }
            )

        if not siblings:
            self.is_parallel = False
            self.parallel_group_id = None
            return

        # Reuse the sibling's group when it has one, so a pair shares an id.
        group_id = next((s.parallel_group_id for s in siblings if s.parallel_group_id), None) or uuid.uuid4()
        self.parallel_group_id = group_id
        self.is_parallel = True

        for sibling in siblings:
            if sibling.parallel_group_id != group_id or not sibling.is_parallel:
                sibling.parallel_group_id = group_id
                sibling.is_parallel = True
                sibling.save(update_fields=["parallel_group_id", "is_parallel", "updated_at"])

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        if self.status == ReferralStatus.COMPLETED:
            if not self.outcome_type_id:
                errors["outcome_type"] = _("A completed referral needs an outcome type.")
            elif self.referral_category_id and not self.outcome_type.is_valid_for(self.referral_category):
                # §5.3 maps outcomes to the categories they apply to.
                errors["outcome_type"] = _("'%(outcome)s' does not apply to a %(category)s referral.") % {
                    "outcome": self.outcome_type.label,
                    "category": self.referral_category.label,
                }

        if self.status == ReferralStatus.FAILED and not self.failure_reason_code_id:
            errors["failure_reason_code"] = _("A failed referral needs a failure reason code.")

        if self.outcome_type_id and self.outcome_type.requires_note and not self.notes:
            errors["notes"] = _("This outcome type requires a note.")

        if self.failure_reason_code_id and self.failure_reason_code.requires_note and not self.notes:
            errors["notes"] = _("This failure reason requires a note.")

        if self.referral_category_id and self.referral_category.requires_note and not self.notes:
            errors["notes"] = _("This referral category requires a note.")

        if (
            self.referral_trigger in {ReferralTrigger.ONWARD, ReferralTrigger.REPLACEMENT}
            and not self.parent_referral_id
        ):
            errors["parent_referral"] = _("Onward and replacement referrals must link to the referral they follow.")

        if self.referral_trigger == ReferralTrigger.MANUAL and self.parent_referral_id:
            errors["parent_referral"] = _("Only onward and replacement referrals have a parent.")

        if self.parent_referral_id and self.parent_referral_id == self.pk:
            errors["parent_referral"] = _("A referral cannot follow itself.")

        if errors:
            raise ValidationError(errors)


def build_referral_stack(case):
    """Reconstruct the referral stack for a case — spec §6.4.

    "The full referral stack is not a stored object. It is a query: all Referral
    records for a case_id, ordered by initiated_date, with parent_referral_id and
    replacement_referral_id used to draw the chain, and parallel_group_id used to
    mark concurrent pairs."

    Returns roots (referrals with no parent) in initiation order, each with its
    descendants nested, so the caller can render the chain without walking the
    table itself.
    """
    referrals = list(
        Referral.objects.filter(case=case)
        .select_related("referral_category", "receiving_partner", "outcome_type", "failure_reason_code")
        .order_by("initiated_date", "created_at")
    )

    children_by_parent = {}
    for referral in referrals:
        children_by_parent.setdefault(referral.parent_referral_id, []).append(referral)

    def node(referral):
        return {
            "referral": referral,
            "children": [node(child) for child in children_by_parent.get(referral.id, [])],
        }

    return [node(referral) for referral in children_by_parent.get(None, [])]
