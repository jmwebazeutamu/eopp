"""Registry extension — handoff decisions D1 and D5, `sql/001` section B.

D1: the registry stays as is. There is one identity, and the module creates no
person table of its own. On this platform that identity is `youth.Youth` — the
only person table the system has. The name is from the youth employment
programme it was built for; a WLT member is a woman in a PSNP household, often
well outside the 15-29 band, and `Youth.is_age_eligible` is a warning rather
than a constraint, so the row holds her honestly. Renaming the model to `Person`
would touch every app and every migration for a label, and is worth doing when
something other than a second programme depends on it.

What matters is the consequence D1 was after: the youth side and the WLT side
can never disagree about who someone is, because there is one row.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class EnrolmentRoute(models.TextChoices):
    """How a woman reached the candidate pool (D5, hybrid enrolment)."""

    IMPORT = "IMPORT", _("PSNP ELS caseload import")
    FACILITATOR = "FACILITATOR", _("Added by a facilitator")


class VerificationStatus(models.TextChoices):
    VERIFIED = "VERIFIED", _("Verified")
    PENDING = "PENDING", _("Pending verification")
    REJECTED = "REJECTED", _("Rejected")


class LiteracyLevel(models.TextChoices):
    """Handbook 3.3 selection criteria. Not captured is not enforceable."""

    NONE = "NONE", _("None")
    BASIC = "BASIC", _("Basic")
    FUNCTIONAL = "FUNCTIONAL", _("Functional")


class DigitalLiteracy(models.TextChoices):
    NONE = "NONE", _("None")
    BASIC = "BASIC", _("Basic")


class MatchResolution(models.TextChoices):
    PENDING = "PENDING", _("Pending woreda confirmation")
    CONFIRMED = "CONFIRMED", _("Confirmed as the same woman")
    REJECTED = "REJECTED", _("Rejected — a different woman")
    NEW_PERSON = "NEW_PERSON", _("Registered as a new person")


class BeneficiaryProfileQuerySet(models.QuerySet):
    def verified(self):
        return self.filter(verification_status=VerificationStatus.VERIFIED)

    def programme_eligible(self):
        """The four hard eligibility conditions of handoff §3.3.

        Female, an ELS package completed, the ELS grant received, and a PSNP
        status that is not "not PSNP". Expressed as a queryset as well as a
        property so the candidate pool is one query rather than a loop.
        """
        from apps.youth.models import PsnpStatus, Sex

        return self.filter(
            person__sex=Sex.FEMALE,
            els_completed_on__isnull=False,
            els_grant_received_on__isnull=False,
        ).exclude(person__psnp_status=PsnpStatus.NOT_PSNP)

    def unassigned(self):
        """Not currently in an open group membership.

        `Exists`, not `exclude(person__wlt_memberships__exited_on__isnull=True)`.
        That reads correctly and compiles to a LEFT OUTER JOIN inside the
        subquery, so a woman with *no* membership row gets a joined NULL,
        matches `exited_on IS NULL`, and is excluded — the exact opposite of
        what the method is for. It made the candidate pool empty of everyone who
        had never been in a group, which is everyone a facilitator wants to add.
        """
        from .formation import GroupMembership

        return self.exclude(
            models.Exists(GroupMembership.objects.filter(person=models.OuterRef("person_id"), exited_on__isnull=True))
        )


class BeneficiaryProfile(BaseModel):
    """WLT-specific attributes, hanging off the shared identity (D1).

    Everything here is a WLT concept — PSNP client id, ELS completion, the
    handbook's selection criteria — and none of it belongs on the person row,
    where it would be null for every youth-side registration.
    """

    person = models.OneToOneField(
        "youth.Youth",
        on_delete=models.PROTECT,
        related_name="wlt_profile",
        verbose_name=_("person"),
    )

    # The join key to the PSNP MIS. Without it there is no eligibility
    # verification and no reconciliation — handoff open question 5.
    psnp_client_id = models.CharField(_("PSNP client ID"), max_length=64, blank=True, db_index=True)
    psnp_woreda = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_profiles_by_woreda",
        verbose_name=_("PSNP woreda"),
    )
    psnp_kebele = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_profiles_by_kebele",
        verbose_name=_("PSNP kebele"),
    )

    # ELS pre-conditions. Handbook §2: members complete the ELS package and
    # receive the grant before transitioning into WLT.
    els_completed_on = models.DateField(_("ELS completed on"), null=True, blank=True)
    els_grant_received_on = models.DateField(_("ELS grant received on"), null=True, blank=True)
    els_grant_amount_etb = models.DecimalField(
        _("ELS grant amount (ETB)"), max_digits=14, decimal_places=2, null=True, blank=True
    )

    # Handbook 3.3 selection criteria. The last three are what make the
    # "at least one member with a device" formation rule enforceable at all.
    primary_iga = models.CharField(_("primary IGA"), max_length=128, blank=True)
    literacy_level = models.CharField(_("literacy"), max_length=16, choices=LiteracyLevel.choices, blank=True)
    digital_literacy = models.CharField(
        _("digital literacy"), max_length=16, choices=DigitalLiteracy.choices, blank=True
    )
    has_device = models.BooleanField(_("has a mobile device"), null=True, blank=True)
    household_head = models.BooleanField(_("household head"), null=True, blank=True)

    enrolment_route = models.CharField(
        _("enrolment route"), max_length=16, choices=EnrolmentRoute.choices, db_index=True
    )
    verification_status = models.CharField(
        _("verification status"),
        max_length=16,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
        db_index=True,
    )
    verification_note = models.TextField(_("verification note"), blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_verified_profiles",
        verbose_name=_("verified by"),
    )
    verified_on = models.DateField(_("verified on"), null=True, blank=True)

    history = HistoricalRecords()

    objects = BeneficiaryProfileQuerySet.as_manager()

    class Meta:
        verbose_name = _("WLT beneficiary profile")
        verbose_name_plural = _("WLT beneficiary profiles")
        ordering = ["person__full_name"]
        constraints = [
            # A verification status with nobody behind it is not a verification.
            # In the database because the exception route is the control that
            # stops facilitator additions becoming the main path (D5), and a
            # control enforced only in a serializer is not enforced on import.
            models.CheckConstraint(
                condition=~models.Q(verification_status=VerificationStatus.VERIFIED)
                | models.Q(verified_on__isnull=False),
                name="wlt_verified_needs_date",
            ),
        ]
        indexes = [models.Index(fields=["verification_status", "enrolment_route"])]

    def __str__(self):
        return f"{self.person.full_name} (WLT)"

    # -- derived ----------------------------------------------------------

    @property
    def is_programme_eligible(self):
        """Handoff §3.3 layer one: may she join WLT at all.

        Computed rather than stored, so it cannot go stale behind a profile
        edit. Group *fit* — same kebele, similar circumstances, willing to
        commit — is deliberately not here: those are facilitator judgements and
        the handbook is explicit that participation is voluntary, so they
        surface as prompts and never as blocks.
        """
        from apps.youth.models import PsnpStatus, Sex

        return bool(
            self.person.sex == Sex.FEMALE
            and self.els_completed_on
            and self.els_grant_received_on
            and self.person.psnp_status != PsnpStatus.NOT_PSNP
        )

    @property
    def is_assignable(self):
        """Eligible, verified, and not already in a group.

        Reads the `open_memberships` prefetch when the caller set one up. It is
        the same question the register's group column asks, and answering it
        with `.exists()` per row cost one query per woman on a screen that
        lists the whole kebele. `is not None` rather than truthiness: an empty
        prefetched list means "prefetched, and she is in no group", which is a
        different thing from "nobody prefetched anything".
        """
        prefetched = getattr(self.person, "open_memberships", None)
        if prefetched is None:
            in_a_group = self.person.wlt_memberships.filter(exited_on__isnull=True).exists()
        else:
            in_a_group = bool(prefetched)

        return (
            self.is_programme_eligible
            and self.verification_status == VerificationStatus.VERIFIED
            and not in_a_group
        )


class ImportMatchCandidate(BaseModel):
    """The fuzzy-match queue from the caseload import (D5).

    **Never auto-merged.** Merging two different women is worse than carrying a
    duplicate: one of them loses her savings history and neither can be told
    which. A high-confidence match queues here for a woreda officer to confirm.
    """

    import_batch = models.CharField(_("import batch"), max_length=64, db_index=True)
    source_row = models.JSONField(_("source row"), help_text=_("The extract row, exactly as it arrived."))
    matched_person = models.ForeignKey(
        "youth.Youth",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_import_matches",
        verbose_name=_("matched person"),
    )
    confidence = models.DecimalField(
        _("confidence"), max_digits=4, decimal_places=3, null=True, blank=True, help_text=_("0.000 to 1.000.")
    )
    resolution = models.CharField(
        _("resolution"), max_length=16, choices=MatchResolution.choices, default=MatchResolution.PENDING, db_index=True
    )
    resolution_reason = models.TextField(_("reason"), blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="wlt_resolved_matches",
        verbose_name=_("resolved by"),
    )
    resolved_at = models.DateTimeField(_("resolved at"), null=True, blank=True)

    class Meta:
        verbose_name = _("import match candidate")
        verbose_name_plural = _("import match candidates")
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True) | models.Q(confidence__gte=0, confidence__lte=1),
                name="wlt_match_confidence_range",
            ),
        ]

    def __str__(self):
        return f"{self.import_batch}: {self.get_resolution_display()}"
