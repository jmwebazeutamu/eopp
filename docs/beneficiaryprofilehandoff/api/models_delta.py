"""
Beneficiary profile — model additions.

Every new field is nullable. The registry already holds partial records,
so a non-null constraint would break the existing rows and block the
migration. Enforce completeness in the UI (the "N details missing" chip)
and in an export validator, not in the schema.

Split into two migrations:
  0001  add columns, all null=True            <- safe, no downtime
  0002  backfill from the PSNP import where a value exists
"""

from django.db import models


class MaritalStatus(models.TextChoices):
    SINGLE = "single", "Single"
    MARRIED = "married", "Married"
    WIDOWED = "widowed", "Widowed"
    DIVORCED = "divorced", "Divorced"
    SEPARATED = "separated", "Separated"


class DisabilityType(models.TextChoices):
    NONE = "none", "None"
    PHYSICAL = "physical", "Physical"
    VISUAL = "visual", "Visual"
    HEARING = "hearing", "Hearing"
    INTELLECTUAL = "intellectual", "Intellectual"
    MULTIPLE = "multiple", "Multiple"


class EducationLevel(models.TextChoices):
    NONE = "none", "No formal education"
    ADULT_LITERACY = "adult_literacy", "Adult literacy"
    PRIMARY = "primary", "Primary"
    SECONDARY = "secondary", "Secondary"
    TVET = "tvet", "TVET"
    TERTIARY = "tertiary", "Tertiary"


class BeneficiaryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    EXITED = "exited", "Exited"


class Beneficiary(models.Model):
    # --- already exists (shown for context, do not re-add) -----------------
    # full_name, kebele, registered_on

    # --- identity ----------------------------------------------------------
    reference_code = models.CharField(max_length=24, unique=True, db_index=True)
    psnp_client_number = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    photo = models.ImageField(upload_to="beneficiaries/", null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # used only where DOB is genuinely unknown; UI marks the age "estimated"
    estimated_age = models.PositiveSmallIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)  # store E.164
    woreda = models.ForeignKey("geo.Woreda", null=True, blank=True, on_delete=models.PROTECT)
    household_size = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=BeneficiaryStatus.choices, default=BeneficiaryStatus.ACTIVE
    )
    exited_on = models.DateField(null=True, blank=True)
    exit_reason = models.CharField(max_length=120, null=True, blank=True)

    # --- household ---------------------------------------------------------
    is_head_of_household = models.BooleanField(null=True, blank=True)
    marital_status = models.CharField(
        max_length=12, choices=MaritalStatus.choices, null=True, blank=True
    )
    dependants_count = models.PositiveSmallIntegerField(null=True, blank=True)
    dependants_under_5 = models.PositiveSmallIntegerField(null=True, blank=True)
    disability_type = models.CharField(
        max_length=14, choices=DisabilityType.choices, null=True, blank=True
    )
    disability_notes = models.CharField(max_length=240, null=True, blank=True)
    education_level = models.CharField(
        max_length=16, choices=EducationLevel.choices, null=True, blank=True
    )
    education_grade = models.PositiveSmallIntegerField(null=True, blank=True)

    # --- case --------------------------------------------------------------
    development_agent = models.ForeignKey(
        "staff.Staff", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="assigned_beneficiaries",
    )

    class Meta:
        indexes = [
            models.Index(fields=["status", "woreda"]),
            models.Index(fields=["psnp_client_number"]),
        ]

    # --- derived, never stored --------------------------------------------
    @property
    def age(self):
        if self.date_of_birth:
            today = timezone.localdate()
            return (
                today.year
                - self.date_of_birth.year
                - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
            )
        return self.estimated_age

    @property
    def age_is_estimated(self):
        return self.date_of_birth is None and self.estimated_age is not None

    #: fields the header renders; drives the "N details missing" chip
    HEADER_FIELDS = (
        "psnp_client_number", "photo", "phone", "woreda",
        "kebele", "household_size",
    )

    @property
    def missing_field_count(self):
        return sum(1 for f in self.HEADER_FIELDS if not getattr(self, f, None)) + (
            0 if (self.date_of_birth or self.estimated_age) else 1
        )
