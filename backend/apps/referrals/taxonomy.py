"""Referral taxonomy — spec §5, governed per §9.

§4.6 types `referral_category`, `outcome_type` and `failure_reason_code` as
Enums, but §9 overrides that for storage:

    "Taxonomy governance: referral_category, outcome_type, and
    failure_reason_code are configuration data, not code. The system
    administrator role should own changes to these lists post go-live, with
    changes logged for audit."

and §10.1's Definition of Done requires that "any new configuration data
(referral categories, outcome types, failure codes) is entered through the admin
interface, not hardcoded". So these are lookup tables, not `TextChoices`. The
§5 lists ship as seed data (`seed_referral_taxonomy`), which is a starting point
the programme can extend without a deployment.

`referral_trigger` and `status` are deliberately NOT here. Those are state
machine mechanics from §5.2 and §6.1 — adding a status through the admin would
mean a transition table with no rule for it, so they stay in code.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords


class TaxonomyQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class TaxonomyTerm(models.Model):
    """Shared shape for the three configurable lists.

    Keyed by a stable `code` rather than a UUID: referral rows, imports and the
    §8 dashboards all refer to terms by code, and a human-readable key survives
    a database reload in a way a generated UUID does not.
    """

    code = models.SlugField(_("code"), max_length=64, primary_key=True)
    label = models.CharField(_("label"), max_length=128)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Deactivate to retire a term. Existing referrals keep it."),
    )
    sort_order = models.PositiveSmallIntegerField(_("sort order"), default=100)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TaxonomyQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["sort_order", "label"]

    def __str__(self):
        return self.label


class ReferralCategory(TaxonomyTerm):
    """Spec §5.1. What kind of service the referral is toward."""

    # §6.3: "Complementary Service referrals ... are explicitly allowed to run
    # alongside any other active referral." That behaviour has to survive an
    # administrator renaming the term, so it is a flag on the row rather than a
    # hardcoded comparison against the code "COMPLEMENTARY_SERVICE".
    exempt_from_parallel_cap = models.BooleanField(
        _("exempt from the parallel cap"),
        default=False,
        help_text=_(
            "Referrals in this category run alongside the two-referral cap rather than counting toward it "
            "(spec §6.3 — working default, pending Phase 1 sign-off)."
        ),
    )
    requires_note = models.BooleanField(
        _("requires a note"),
        default=False,
        help_text=_("Catch-all categories such as Other require a free-text note (spec §5.1)."),
    )

    # §4.5's training enrolments are created *from* a referral, and which
    # referrals qualify is a property of the category row — same reasoning as
    # `exempt_from_parallel_cap` above and `OutcomeType.counts_as_placement`.
    #
    # It replaced a hardcoded `("TRAINING",)` tuple in `apps.training.models`.
    # §9 makes the taxonomy the administrator's to extend, and the tuple meant
    # that a category she added — "Vocational Training", "Apprenticeship
    # Training" — silently could not create an enrolment, with no way to fix it
    # short of a deploy and nothing on screen to say why.
    creates_training_enrolment = models.BooleanField(
        _("creates a training enrolment"),
        default=False,
        help_text=_(
            "A referral in this category may open a §4.5 training enrolment. Seeded true for Training; "
            "set it on any other category that delivers a course."
        ),
    )

    creates_placement = models.BooleanField(
        _("creates a placement"),
        default=False,
        help_text=_(
            "A referral in this category may open a §4.7 placement. Seeded true for Employment and " "Apprenticeship."
        ),
    )

    creates_enterprise = models.BooleanField(
        _("creates an enterprise record"),
        default=False,
        help_text=_(
            "A referral in this category may open a §4.8 enterprise record. Seeded true for Enterprise and "
            "Finance Access."
        ),
    )

    # Which kinds of subject this category may be raised against — the WLT
    # module's stage 0 (handoff decision D4, backlog S0.2).
    #
    # This is a safeguarding control before it is a data-modelling one. A
    # protection or GBV category lists CASE and YOUTH only, so a disclosure can
    # never be created against a savings group and can never appear on a group
    # timeline. The handbook puts GBV on the meeting agenda; this is what turns
    # its confidentiality norm into a database-backed rule rather than a
    # convention somebody has to remember.
    #
    # Every existing category is backfilled to ["CASE"], which preserves current
    # behaviour exactly: today every referral hangs off a case.
    allowed_subject_types = models.JSONField(
        _("allowed subject types"),
        default=list,
        blank=True,
        help_text=_("Subjects a referral in this category may name: CASE, YOUTH, GROUP, CLA or FEDERATION."),
    )

    history = HistoricalRecords()

    class Meta(TaxonomyTerm.Meta):
        verbose_name = _("referral category")
        verbose_name_plural = _("referral categories")

    def permits(self, subject_type):
        """Whether this category may name a subject of the given type.

        An empty list is **not** "anything": it is a category configured before
        subject types existed, and it means CASE, which is what every referral
        was. Reading it as unrestricted would open the safeguarding rule the
        moment somebody cleared the field.
        """
        return subject_type in (self.allowed_subject_types or ["CASE"])


class OutcomeType(TaxonomyTerm):
    """Spec §5.3. What a completed referral achieved."""

    # §5.3 maps each outcome to the categories it applies to. Modelled as a
    # relation so the admin can rewire it; an empty set means "any category",
    # which is how §5.3's "Other" row behaves.
    applies_to = models.ManyToManyField(
        ReferralCategory,
        blank=True,
        related_name="outcome_types",
        verbose_name=_("applies to categories"),
        help_text=_("Leave empty to allow this outcome for any category."),
    )
    requires_note = models.BooleanField(_("requires a note"), default=False)

    # The programme dashboard's placement count keys off this flag rather than a
    # list of codes, for the same reason `exempt_from_parallel_cap` does: §9
    # makes this table configuration the system administrator owns, so a new
    # outcome that means "the youth is in work" must be countable without a
    # deploy. Training Completion is deliberately not one — it completes a
    # referral without putting anyone in a job.
    counts_as_placement = models.BooleanField(
        _("counts as a placement"),
        default=False,
        help_text=_("Include referrals closed with this outcome in the programme dashboard's placement figures."),
    )

    history = HistoricalRecords()

    class Meta(TaxonomyTerm.Meta):
        verbose_name = _("outcome type")
        verbose_name_plural = _("outcome types")

    def is_valid_for(self, category):
        """Whether this outcome may be recorded against a given category."""
        if not self.pk:
            return False
        # No restriction configured means it applies everywhere (§5.3 "Other").
        if not self.applies_to.exists():
            return True
        return self.applies_to.filter(pk=category.pk).exists()


class FailureReasonCode(TaxonomyTerm):
    """Spec §5.4.

    The spec is explicit that its list "need local validation with frontline
    staff during Phase 1. They are a starting point, not a final list." Storing
    them as configuration is what makes that revision possible without a release.
    """

    requires_note = models.BooleanField(_("requires a note"), default=False)

    history = HistoricalRecords()

    class Meta(TaxonomyTerm.Meta):
        verbose_name = _("failure reason code")
        verbose_name_plural = _("failure reason codes")


def validate_taxonomy_term_active(term, field_name):
    """Reject a retired term on a new referral.

    Deactivated terms stay readable on historical rows — the §8 dashboards group
    by them — but must not be selectable for new work.
    """
    if term is not None and not term.is_active:
        raise ValidationError({field_name: _("'%(label)s' has been retired.") % {"label": term.label}})
