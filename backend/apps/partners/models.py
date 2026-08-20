"""Partner / Provider Organisation — spec §4.11.

Receives referrals (§4.6 `receiving_partner_id`) and runs trainings (§4.5
`training_provider_id`). Also the institution a referral-partner-staff account is
scoped to (§4.12 `partner_id`, §7).
"""

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class PartnerType(models.TextChoices):
    """Spec §4.11, verbatim."""

    TVET_INSTITUTION = "TVET_INSTITUTION", _("TVET Institution")
    EMPLOYER = "EMPLOYER", _("Employer")
    ENTERPRISE_DEVELOPMENT_AGENCY = "ENTERPRISE_DEVELOPMENT_AGENCY", _("Enterprise Development Agency")
    SAVINGS_GROUP = "SAVINGS_GROUP", _("Savings Group")
    HEALTH_SERVICE = "HEALTH_SERVICE", _("Health Service")
    PSYCHOSOCIAL_SERVICE = "PSYCHOSOCIAL_SERVICE", _("Psychosocial Service")
    LEGAL_AID = "LEGAL_AID", _("Legal Aid")
    FINANCE_INSTITUTION = "FINANCE_INSTITUTION", _("Finance Institution")
    # Added for the WLT group module (handoff README §6.6). RUSACCOs are the
    # incumbent rural financial structure in Ethiopia, and lumping them under
    # "Other" hides the unresolved question of whether WLT federations compete
    # with them or join them — which is a question the pilot is meant to answer,
    # and cannot if the data does not distinguish them.
    RUSACCO = "RUSACCO", _("RUSACCO (rural savings and credit cooperative)")
    COOPERATIVE = "COOPERATIVE", _("Cooperative")
    BUYER = "BUYER", _("Buyer / offtaker")
    OTHER = "OTHER", _("Other")


class Standing(models.TextChoices):
    """Whether this organisation may be proposed for new work, and why not.

    `active_status` (spec §4.11) answers "may they receive new referrals". This
    answers "on what grounds", and the WLT module needs the distinction:
    blacklisting a provider **flags open linkages for review and does not close
    them**, because the obligation still exists and a group's money is still
    with them. Suspension and blacklisting are not the same instruction to a
    field worker, and a single boolean cannot carry both.

    Kept consistent with `active_status` in `save`, so the two cannot drift.
    """

    ACTIVE = "ACTIVE", _("Active")
    SUSPENDED = "SUSPENDED", _("Suspended")
    BLACKLISTED = "BLACKLISTED", _("Blacklisted")


class MouStatus(models.TextChoices):
    """Tracks the referral-relationship mapping (spec §4.11).

    TODO(spec-gap): §4.11 names `mou_status` as an Enum without listing values.
    These follow the usual agreement lifecycle; confirm during Phase 1.
    """

    NONE = "NONE", _("No MOU")
    DRAFT = "DRAFT", _("Draft")
    SIGNED = "SIGNED", _("Signed")
    EXPIRED = "EXPIRED", _("Expired")
    TERMINATED = "TERMINATED", _("Terminated")


class PartnerQuerySet(models.QuerySet):
    def active(self):
        return self.filter(active_status=True)

    def covering(self, woreda):
        return self.filter(woreda_coverage__contains=[woreda])

    def of_type(self, partner_type):
        return self.filter(partner_type=partner_type)


class Partner(BaseModel):
    """Spec §4.11. `partner_id` is `id`, per the §4 type-translation guide."""

    partner_name = models.CharField(_("partner name"), max_length=255, db_index=True)
    partner_type = models.CharField(_("partner type"), max_length=32, choices=PartnerType.choices, db_index=True)

    # §4.11 Multi-select. Woreda names, matching the text convention used by
    # Youth (§4.1) and Case (§4.2); apps.locations is the controlled vocabulary.
    woreda_coverage = ArrayField(
        models.CharField(max_length=128),
        default=list,
        verbose_name=_("woreda coverage"),
        help_text=_("Woredas this partner serves."),
    )

    contact_name = models.CharField(_("contact name"), max_length=255)
    phone = models.CharField(_("phone"), max_length=32)
    email = models.EmailField(_("email"))

    active_status = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive partners cannot receive new referrals but keep their history."),
    )

    standing = models.CharField(
        _("standing"),
        max_length=16,
        choices=Standing.choices,
        default=Standing.ACTIVE,
        db_index=True,
        help_text=_("Suspended or blacklisted organisations cannot be proposed for new referrals or linkages."),
    )

    mou_status = models.CharField(
        _("MOU status"), max_length=16, choices=MouStatus.choices, default=MouStatus.NONE, blank=True
    )
    mou_date = models.DateField(_("MOU date"), null=True, blank=True)

    performance_notes = models.TextField(
        _("performance notes"),
        blank=True,
        help_text=_("Qualitative input alongside the quantitative referral performance dashboard (spec §8)."),
    )

    history = HistoricalRecords()  # §9 audit trail

    objects = PartnerQuerySet.as_manager()

    class Meta:
        verbose_name = _("partner")
        verbose_name_plural = _("partners")
        ordering = ["partner_name"]
        constraints = [
            models.UniqueConstraint(fields=["partner_name", "partner_type"], name="unique_partner_name_per_type"),
        ]
        indexes = [models.Index(fields=["partner_type", "active_status"])]

    def __str__(self):
        return self.partner_name

    @property
    def can_receive_referrals(self):
        """Whether a new referral may be sent here.

        Read by the Sprint 3 referral engine. An inactive partner keeps its
        referral history — §8's failed-rate-by-partner dashboard needs it — but
        must not appear in the destination picker.
        """
        return self.active_status and self.standing == Standing.ACTIVE

    @property
    def is_blacklisted(self):
        return self.standing == Standing.BLACKLISTED

    def covers(self, woreda):
        return woreda in self.woreda_coverage

    def save(self, *args, **kwargs):
        """Keep `standing` and `active_status` from drifting apart.

        Two fields describing overlapping facts is how a partner comes to be
        blacklisted on one screen and available in a picker on another. The
        direction is one-way on purpose: losing standing withdraws the partner
        from new work, and restoring it is a separate decision somebody makes
        explicitly rather than a side effect.
        """
        if self.standing != Standing.ACTIVE:
            self.active_status = False
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"active_status"}
        return super().save(*args, **kwargs)

    def clean(self):
        errors = {}

        if self.mou_status in {MouStatus.SIGNED, MouStatus.EXPIRED, MouStatus.TERMINATED} and not self.mou_date:
            errors["mou_date"] = _("Record the date for a %(status)s MOU.") % {"status": self.get_mou_status_display()}

        if not self.woreda_coverage:
            # A partner covering nothing can never be matched to a case, so this
            # is a data-entry mistake rather than a valid state.
            errors["woreda_coverage"] = _("List at least one woreda this partner covers.")

        if errors:
            raise ValidationError(errors)
