"""User (Actor) — spec §4.12, with the role model from §7.

The ten roles and their record-level scoping are declared in `ACCESS_MATRIX`
below, transcribed directly from the spec §7 table. Permission classes read that
matrix rather than hardcoding role checks at each call site, so when the Phase 1
workshops revise the access model there is exactly one place to change.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import UUIDModel


class Role(models.TextChoices):
    """The ten user types in spec §7."""

    OUTREACH_WORKER = "OUTREACH_WORKER", _("Outreach worker / community facilitator")
    CASE_MANAGER = "CASE_MANAGER", _("Youth case manager")
    TRAINER = "TRAINER", _("Trainer / training officer")
    EMPLOYER_LIAISON = "EMPLOYER_LIAISON", _("Employer liaison staff")
    ENTERPRISE_OFFICER = "ENTERPRISE_OFFICER", _("Enterprise development officer")
    PARTNER_STAFF = "PARTNER_STAFF", _("Referral partner staff")
    SUPERVISOR = "SUPERVISOR", _("Woreda / programme supervisor")
    PROGRAMME_MANAGER = "PROGRAMME_MANAGER", _("Programme manager")
    MNE_STAFF = "MNE_STAFF", _("M&E staff")
    SYSTEM_ADMIN = "SYSTEM_ADMIN", _("System administrator")


class AccountStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("Active")
    SUSPENDED = "SUSPENDED", _("Suspended")
    INACTIVE = "INACTIVE", _("Inactive")


class Scope(models.TextChoices):
    """How widely a role may see case and referral records.

    Ordered loosely narrow → wide. `LINKED` means "only records this user's own
    organisation or activity is attached to", which is narrower than woreda and
    is resolved per-entity by that entity's queryset filter.
    """

    NONE = "NONE", _("No case content")
    LINKED = "LINKED", _("Linked records only")
    OWN_CASELOAD = "OWN_CASELOAD", _("Own caseload")
    OWN_WOREDA = "OWN_WOREDA", _("Own woreda")
    ALL = "ALL", _("All records")


# Spec §7, transcribed. `write` means the role may change the record, not that it
# may change every field — field-level permissions are a configuration detail
# layered on top of this record-level scoping (§7 preamble).
ACCESS_MATRIX = {
    Role.OUTREACH_WORKER: {
        "case_scope": Scope.OWN_WOREDA,
        "case_write": True,  # create at intake
        "referral_scope": Scope.OWN_WOREDA,
        "referral_write": False,
    },
    Role.CASE_MANAGER: {
        "case_scope": Scope.OWN_CASELOAD,
        "case_write": True,
        "referral_scope": Scope.OWN_CASELOAD,
        "referral_write": True,
    },
    Role.TRAINER: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": False,
    },
    Role.EMPLOYER_LIAISON: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": True,
    },
    Role.ENTERPRISE_OFFICER: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": True,
    },
    Role.PARTNER_STAFF: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,  # further narrowed to own institution
        "referral_write": True,
    },
    Role.SUPERVISOR: {
        "case_scope": Scope.OWN_WOREDA,
        "case_write": False,
        "referral_scope": Scope.OWN_WOREDA,
        "referral_write": False,
    },
    Role.PROGRAMME_MANAGER: {
        "case_scope": Scope.ALL,
        "case_write": False,
        "referral_scope": Scope.ALL,
        "referral_write": False,
    },
    Role.MNE_STAFF: {
        "case_scope": Scope.ALL,
        "case_write": False,
        "referral_scope": Scope.ALL,
        "referral_write": False,
    },
    Role.SYSTEM_ADMIN: {
        # "Configuration only, no case content by default" (§7). Deliberately not
        # a superuser over case data: an administrator who needs case access gets
        # a second account with a case-facing role, so the audit trail stays honest.
        "case_scope": Scope.NONE,
        "case_write": False,
        "referral_scope": Scope.NONE,
        "referral_write": False,
    },
}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Users require a username.")
        extra_fields.setdefault("account_status", AccountStatus.ACTIVE)
        email = extra_fields.pop("email", "")
        user = self.model(username=username, email=self.normalize_email(email) if email else "", **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.SYSTEM_ADMIN)
        extra_fields.setdefault("full_name", username)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(username, password, **extra_fields)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    """Spec §4.12. `user_id` is `id` here, per the §4 type-translation guide."""

    # Not in the §4.12 field list, but authentication needs a credential handle.
    # Username rather than email: woreda-level field staff often have no work
    # email address, and the spec's contact fields sit on Partner, not User.
    username = models.CharField(_("username"), max_length=150, unique=True)
    email = models.EmailField(_("email address"), blank=True)

    full_name = models.CharField(_("full name"), max_length=255)
    role = models.CharField(_("role"), max_length=32, choices=Role.choices, db_index=True)

    # §4.12 `woreda_assignment` is Multi-select. Woreda is free text on Youth
    # (§4.1) in the pilot, so this stores woreda names; Sprint 1's location
    # reference data may promote both sides to FKs.
    woreda_assignment = ArrayField(
        models.CharField(max_length=128),
        default=list,
        blank=True,
        verbose_name=_("woreda assignment"),
        help_text=_("Woredas this user may work in. Ignored for roles scoped to all records."),
    )

    # §4.12: "set for referral-partner-staff accounts; scopes their referral
    # visibility". PROTECT rather than CASCADE — deleting a partner must never
    # silently remove the staff accounts whose actions the audit trail records.
    partner = models.ForeignKey(
        "partners.Partner",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="staff",
        verbose_name=_("partner organisation"),
        help_text=_("Required for referral partner staff; scopes them to their own institution's referrals."),
    )

    account_status = models.CharField(
        max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE, db_index=True
    )

    is_staff = models.BooleanField(default=False, help_text=_("Django admin access."))
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    history = HistoricalRecords()  # §9 audit trail

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["full_name"]
        indexes = [models.Index(fields=["role", "account_status"])]

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    # -- access helpers ---------------------------------------------------

    @property
    def access(self):
        """This user's row from ACCESS_MATRIX (spec §7)."""
        return ACCESS_MATRIX.get(self.role, ACCESS_MATRIX[Role.SYSTEM_ADMIN])

    def case_scope(self):
        return self.access["case_scope"]

    def referral_scope(self):
        return self.access["referral_scope"]

    def can_write_cases(self):
        return self.access["case_write"]

    def can_write_referrals(self):
        return self.access["referral_write"]

    @property
    def is_operational(self):
        """Authenticated is not sufficient — a suspended account must not act."""
        return self.is_active and self.account_status == AccountStatus.ACTIVE

    def clean(self):
        """Keep the partner link consistent with the role (spec §4.12, §7)."""
        errors = {}

        if self.role == Role.PARTNER_STAFF and not self.partner_id:
            # Without an institution there is nothing to scope this account to,
            # and `apply_linked_scope` would correctly show them nothing — an
            # account that appears to work but sees an empty system.
            errors["partner"] = _("Referral partner staff must be linked to a partner organisation.")

        if self.role != Role.PARTNER_STAFF and self.partner_id:
            errors["partner"] = _("Only referral partner staff are linked to a partner organisation.")

        if errors:
            raise ValidationError(errors)
