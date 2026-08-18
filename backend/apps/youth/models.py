"""Youth (Participant) — spec §4.1. The root of the case.

Source module: Youth Intake and Registration.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel


class Sex(models.TextChoices):
    """Spec §4.1: 'Male / Female / Other, per Ethiopian data standards'."""

    MALE = "MALE", _("Male")
    FEMALE = "FEMALE", _("Female")
    OTHER = "OTHER", _("Other")


class PsnpStatus(models.TextChoices):
    """Spec §4.1: Enrolled / Graduated / Not PSNP."""

    ENROLLED = "ENROLLED", _("Enrolled")
    GRADUATED = "GRADUATED", _("Graduated")
    NOT_PSNP = "NOT_PSNP", _("Not PSNP")


class EducationLevel(models.TextChoices):
    """Feeds the profiling score (spec §4.3).

    TODO(spec-gap): §4.1 names this field but does not enumerate its values. The
    ladder below follows the Ethiopian system; confirm with M&E when the
    `vulnerability_index_score` methodology is defined, since the two interact.
    """

    NONE = "NONE", _("No formal education")
    PRIMARY_INCOMPLETE = "PRIMARY_INCOMPLETE", _("Primary incomplete (grades 1-8)")
    PRIMARY_COMPLETE = "PRIMARY_COMPLETE", _("Primary complete (grade 8)")
    SECONDARY_INCOMPLETE = "SECONDARY_INCOMPLETE", _("Secondary incomplete (grades 9-12)")
    SECONDARY_COMPLETE = "SECONDARY_COMPLETE", _("Secondary complete (grade 12)")
    TVET = "TVET", _("TVET certificate or diploma")
    TERTIARY = "TERTIARY", _("University degree or above")


class DisabilityStatus(models.TextChoices):
    """For vulnerability screening and priority flagging (spec §4.1).

    TODO(spec-gap): values not enumerated in the spec. These follow the Washington
    Group functional-domain categories; validate with the disability inclusion
    focal point during Phase 1.
    """

    NONE = "NONE", _("No disability")
    PHYSICAL = "PHYSICAL", _("Physical / mobility")
    VISUAL = "VISUAL", _("Visual")
    HEARING = "HEARING", _("Hearing")
    INTELLECTUAL = "INTELLECTUAL", _("Intellectual")
    PSYCHOSOCIAL = "PSYCHOSOCIAL", _("Psychosocial")
    MULTIPLE = "MULTIPLE", _("Multiple")
    UNDISCLOSED = "UNDISCLOSED", _("Not disclosed")


class SettlementType(models.TextChoices):
    """Rural / peri-urban / urban — OQ-11, settled 2026-08-18.

    Both the ILO and the World Bank frameworks require a rural/urban cut on
    every indicator, and nothing in §4.1 supported one. Deliberately **not**
    proxied from woreda: an Ethiopian woreda routinely contains both, so
    inferring it would produce a confident number that is wrong rather than an
    honest gap.

    Optional, because it is being added after intake has begun and back-filling
    a guess is worse than a blank.
    """

    RURAL = "RURAL", _("Rural")
    PERI_URBAN = "PERI_URBAN", _("Peri-urban")
    URBAN = "URBAN", _("Urban")


class YouthQuerySet(models.QuerySet):
    def in_woredas(self, woredas):
        return self.filter(woreda__in=woredas)

    def consented(self):
        return self.filter(consent_given=True)


class Youth(BaseModel):
    """Spec §4.1. `youth_id` is `id`, per the §4 type-translation guide."""

    full_name = models.CharField(_("full name"), max_length=255, db_index=True)
    sex = models.CharField(_("sex"), max_length=8, choices=Sex.choices)
    date_of_birth = models.DateField(_("date of birth"), help_text=_("Used to confirm youth age band eligibility."))

    phone_number = models.CharField(
        _("phone number"),
        max_length=32,
        blank=True,
        help_text=_("Youth or next-of-kin contact."),
    )
    national_or_kebele_id = models.CharField(
        _("national or kebele ID"),
        max_length=64,
        blank=True,
        help_text=_("Local identification, where available."),
    )

    # Spec §4.1 stores the location hierarchy as text. apps.locations holds the
    # controlled vocabulary these are validated against; see that app's docstring.
    region = models.CharField(_("region"), max_length=128)
    zone = models.CharField(_("zone"), max_length=128)
    woreda = models.CharField(_("woreda"), max_length=128, db_index=True)
    kebele = models.CharField(_("kebele"), max_length=128)
    settlement_type = models.CharField(
        _("settlement type"),
        max_length=16,
        choices=SettlementType.choices,
        blank=True,
        db_index=True,
        help_text=_("Rural, peri-urban or urban. Required by the ILO and World Bank disaggregation."),
    )

    # §4.1 types this as a Reference, but the PSNP household registry is an
    # external system and no Household entity exists among the fourteen in §3.
    # Stored as the foreign identifier until an integration is specified.
    household_id = models.CharField(
        _("PSNP household ID"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("Identifier in the PSNP household registration system, where the youth is linked to one."),
    )
    psnp_status = models.CharField(
        _("PSNP status"), max_length=16, choices=PsnpStatus.choices, blank=True, db_index=True
    )

    education_level = models.CharField(_("education level"), max_length=24, choices=EducationLevel.choices, blank=True)
    disability_status = models.CharField(
        _("disability status"), max_length=16, choices=DisabilityStatus.choices, blank=True
    )

    # §4.1 marks both as required, and §9 makes consent the basis for holding
    # this record at all. See `clean` for why consent_given must be true.
    consent_given = models.BooleanField(_("consent given"), default=False)
    consent_date = models.DateField(_("consent date"), null=True, blank=True)

    registration_date = models.DateField(_("registration date"), auto_now_add=True, db_index=True)
    registering_worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="registered_youth",
        verbose_name=_("registering worker"),
        help_text=_("Outreach worker or facilitator who registered the youth."),
    )

    history = HistoricalRecords()  # §9 audit trail

    objects = YouthQuerySet.as_manager()

    class Meta:
        verbose_name = _("youth")
        verbose_name_plural = _("youth")
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["woreda", "full_name"]),
            models.Index(fields=["registration_date"]),
        ]

    def __str__(self):
        return self.full_name

    # -- derived ----------------------------------------------------------

    def age_at(self, on_date=None):
        """Age in whole years. Defaults to today."""
        on_date = on_date or date.today()
        born = self.date_of_birth
        return on_date.year - born.year - ((on_date.month, on_date.day) < (born.month, born.day))

    @property
    def age(self):
        return self.age_at()

    @property
    def is_age_eligible(self):
        return settings.YOUTH_AGE_MIN <= self.age <= settings.YOUTH_AGE_MAX

    # -- validation -------------------------------------------------------

    def clean(self):
        errors = {}

        if self.date_of_birth and self.date_of_birth > date.today():
            errors["date_of_birth"] = _("Date of birth cannot be in the future.")

        # §9 makes consent the legal basis for holding the record. A youth who
        # has not consented should not have one, so this is refused at write
        # time rather than stored as a flag someone must remember to check.
        if not self.consent_given:
            errors["consent_given"] = _("A youth cannot be registered without recorded consent.")

        if self.consent_given and not self.consent_date:
            errors["consent_date"] = _("Record the date consent was given.")

        if self.consent_date and self.consent_date > date.today():
            errors["consent_date"] = _("Consent date cannot be in the future.")

        if errors:
            raise ValidationError(errors)
