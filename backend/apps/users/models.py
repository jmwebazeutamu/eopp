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
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from apps.common.models import BaseModel, UUIDModel


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

    # WLT group module (PSNP 6 Women's Livelihoods Transformation). A separate
    # programme with a separate subject — a savings group rather than a young
    # person — and its own approval chain, so it gets its own roles rather than
    # being mapped onto the ten in §7.
    #
    # Mapping the four onto SUPERVISOR / PROGRAMME_MANAGER would have been
    # cheaper and wrong in the one way that matters: the WLT handoff's §9 puts
    # approval at woreda, region and federal level with **no self-approval**,
    # and a role that is simultaneously a youth supervisor and a WLT approver
    # carries a youth case scope into the group domain. These four have
    # `case_scope: NONE`, which is what makes "a facilitator who can see a group
    # roster must not thereby see those women's youth-side case files" a
    # property of the matrix rather than of every viewset that remembers.
    WLT_FACILITATOR = "WLT_FACILITATOR", _("WLT group facilitator")
    WLT_WOREDA_OFFICER = "WLT_WOREDA_OFFICER", _("WLT woreda officer (FSCO)")
    WLT_REGION_OFFICER = "WLT_REGION_OFFICER", _("WLT region officer (FSCO)")
    WLT_FEDERAL_OFFICER = "WLT_FEDERAL_OFFICER", _("WLT federal officer (FSCO)")

    @classmethod
    def wlt_roles(cls):
        return {cls.WLT_FACILITATOR, cls.WLT_WOREDA_OFFICER, cls.WLT_REGION_OFFICER, cls.WLT_FEDERAL_OFFICER}


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


class GroupScope(models.TextChoices):
    """How widely a role may see WLT group records.

    Separate from `Scope` because the group domain scopes on different keys. A
    youth case is scoped by caseload or by woreda name; a savings group is
    scoped by the facilitator who runs it and by a point in the administrative
    tree (`User.wlt_scope_location`), which is what lets one enum serve a
    woreda officer, a region officer and a federal officer without three
    near-identical values.

    `OWN_GROUPS` is object-level: the groups this user facilitates. It is
    narrower than a geography, because two facilitators work the same kebele.
    """

    NONE = "NONE", _("No group content")
    OWN_GROUPS = "OWN_GROUPS", _("Own groups")
    OWN_GEOGRAPHY = "OWN_GEOGRAPHY", _("Own assigned geography")
    ALL = "ALL", _("All groups")


# WLT approval levels, in escalation order — the handoff's §9 chain. A decision
# needing level 2 cannot be taken by a level 1 officer, and an override
# escalates by one level. `None` means the role approves nothing.
WLT_APPROVAL_LEVELS = {
    Role.WLT_WOREDA_OFFICER: 1,
    Role.WLT_REGION_OFFICER: 2,
    Role.WLT_FEDERAL_OFFICER: 3,
}


# The access row for a role the matrix does not cover.
#
# Kept as its own constant, and deliberately not an alias for any real role's
# row: `User.access` falls back to it, so a role added to `Role` but forgotten
# here, or a stale value read off an old database row, sees nothing rather than
# inheriting whatever the fallback role happens to be allowed at the time. It
# used to be the system administrator's row, which stopped being safe the moment
# that role was widened below.
NO_ACCESS = {
    "case_scope": Scope.NONE,
    "case_write": False,
    "referral_scope": Scope.NONE,
    "referral_write": False,
    "group_scope": GroupScope.NONE,
    "group_write": False,
    "delivery_write": False,
}


# Spec §7, transcribed. `write` means the role may change the record, not that it
# may change every field — field-level permissions are a configuration detail
# layered on top of this record-level scoping (§7 preamble).
ACCESS_MATRIX = {
    Role.OUTREACH_WORKER: {
        "case_scope": Scope.OWN_WOREDA,
        "case_write": True,  # create at intake
        "referral_scope": Scope.OWN_WOREDA,
        "referral_write": False,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": False,
    },
    Role.CASE_MANAGER: {
        "case_scope": Scope.OWN_CASELOAD,
        "case_write": True,
        "referral_scope": Scope.OWN_CASELOAD,
        "referral_write": True,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": True,
    },
    Role.TRAINER: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": False,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": True,
    },
    Role.EMPLOYER_LIAISON: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": True,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": True,
    },
    Role.ENTERPRISE_OFFICER: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,
        "referral_write": True,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": True,
    },
    Role.PARTNER_STAFF: {
        "case_scope": Scope.LINKED,
        "case_write": False,
        "referral_scope": Scope.LINKED,  # further narrowed to own institution
        "referral_write": True,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": False,
    },
    Role.SUPERVISOR: {
        "case_scope": Scope.OWN_WOREDA,
        "case_write": False,
        "referral_scope": Scope.OWN_WOREDA,
        "referral_write": False,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": False,
    },
    Role.PROGRAMME_MANAGER: {
        "case_scope": Scope.ALL,
        "case_write": False,
        "referral_scope": Scope.ALL,
        "referral_write": False,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": False,
    },
    Role.MNE_STAFF: {
        "case_scope": Scope.ALL,
        "case_write": False,
        "referral_scope": Scope.ALL,
        "referral_write": False,
        "group_scope": GroupScope.NONE,
        "group_write": False,
        "delivery_write": False,
    },
    Role.SYSTEM_ADMIN: {
        # TODO(spec-deviation): §7 says "Configuration only, no case content by
        # default" and the original implementation followed it — an administrator
        # who needed case access took a second account with a case-facing role,
        # so §9 could attribute every action to a person in a known role.
        #
        # Widened to full access on 2026-08-16 at the programme's request, with
        # the trade-off stated: an administrator now reads and writes every case
        # and referral in every woreda, and work done from a shared admin login
        # is harder to attribute than the same work done from a named case-facing
        # account. Carry this to Phase 1 sign-off rather than treating it as
        # settled — it is the one place the matrix departs from §7 as written.
        "case_scope": Scope.ALL,
        "case_write": True,
        "referral_scope": Scope.ALL,
        "referral_write": True,
        # The 2026-08-16 widening reads across to the group domain for the same
        # reason it was granted: an administrator who cannot see a record cannot
        # support the person using it. Same trade-off, same Phase 1 review.
        "group_scope": GroupScope.ALL,
        "group_write": True,
        "delivery_write": True,
    },
    # ---- WLT group module -------------------------------------------------
    #
    # Every row below has `case_scope: NONE`. That is the module boundary, not
    # an oversight: WLT staff work with savings groups, and the women in those
    # groups may also hold youth-employment cases. Reading a roster must not
    # open those case files (WLT handoff §9, S0.3), and the cheapest place to
    # guarantee it is here, once, rather than in every viewset.
    Role.WLT_FACILITATOR: {
        "case_scope": Scope.NONE,
        "case_write": False,
        "referral_scope": Scope.NONE,
        "referral_write": False,
        "group_scope": GroupScope.OWN_GROUPS,
        "group_write": True,
        "delivery_write": False,
    },
    Role.WLT_WOREDA_OFFICER: {
        "case_scope": Scope.NONE,
        "case_write": False,
        "referral_scope": Scope.NONE,
        "referral_write": False,
        "group_scope": GroupScope.OWN_GEOGRAPHY,
        # Read and approve, not record. Meetings and the ledger belong to the
        # facilitator who was in the room; an officer who could post a ledger
        # entry could also settle a discrepancy nobody witnessed.
        "group_write": False,
        "delivery_write": False,
    },
    Role.WLT_REGION_OFFICER: {
        "case_scope": Scope.NONE,
        "case_write": False,
        "referral_scope": Scope.NONE,
        "referral_write": False,
        "group_scope": GroupScope.OWN_GEOGRAPHY,
        "group_write": False,
        "delivery_write": False,
    },
    Role.WLT_FEDERAL_OFFICER: {
        "case_scope": Scope.NONE,
        "case_write": False,
        "referral_scope": Scope.NONE,
        "referral_write": False,
        # Federal sits above every regional allocation, and the handoff's §9
        # gives it aggregate visibility plus the final approval level.
        "group_scope": GroupScope.ALL,
        "group_write": False,
        "delivery_write": False,
    },
}


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("Users require a username.")
        extra_fields.setdefault("account_status", AccountStatus.ACTIVE)
        # `email` is still accepted as an alias for `work_email`: createsuperuser
        # and any caller written before the rename passes it, and silently
        # dropping an address is worse than accepting it under its old name.
        # Addresses are rows now, so they are pulled out here and written after
        # the user exists. `email` stays accepted as an alias for the work
        # address: createsuperuser passes it, and silently dropping an address
        # is worse than accepting it under its old name.
        addresses = {
            "WORK": extra_fields.pop("work_email", "") or extra_fields.pop("email", ""),
            "PERSONAL": extra_fields.pop("personal_email", ""),
        }
        extra_fields.pop("email", None)
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        for kind, address in addresses.items():
            if address:
                user.emails.create(kind=kind, address=address)
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
    # Four contact points: work and personal, for each of email and phone.
    #
    # `work_email` is the renamed `email`. Nothing depended on it —
    # USERNAME_FIELD is `username`, it is not in REQUIRED_FIELDS, and no code
    # read it — so the rename is a label change with the data carried across,
    # and it avoids the asymmetry of `email` sitting beside `personal_email`.
    #
    # Whichever address a password reset would use has to be decided before one
    # is built; today nothing sends mail. See PROFILE-1 in the UI backlog.
    # Emails live in `UserEmail`, one row per address, because "an address is
    # registered once" is a statement about addresses and cannot be expressed
    # across two columns: `unique=True` on each would still allow one account's
    # work address to equal another's personal, or its own.
    #
    # Phones stay flat. Numbers are shared far more loosely than mailboxes — a
    # shared office line is normal — so the same constraint would be wrong.
    work_phone = models.CharField(_("work phone"), max_length=32, blank=True)
    personal_phone = models.CharField(_("personal phone"), max_length=32, blank=True)

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

    # WLT handoff §9. The group domain scopes on a point in the administrative
    # tree rather than on `woreda_assignment`, which is a list of woreda *names*
    # carried over from §4.1's text location fields. A region officer cannot be
    # expressed as a list of woreda names without re-listing every woreda in the
    # region and re-listing it again when one is added.
    #
    # Null means unscoped, which is only meaningful for a role whose group scope
    # is ALL; `clean` refuses it on the two roles that would otherwise see
    # nothing at all.
    wlt_scope_location = models.ForeignKey(
        "locations.Location",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="scoped_users",
        verbose_name=_("WLT scope"),
        help_text=_("Region, woreda or kebele this WLT account works in. Groups below it are visible."),
    )

    account_status = models.CharField(
        max_length=16, choices=AccountStatus.choices, default=AccountStatus.ACTIVE, db_index=True
    )

    is_staff = models.BooleanField(default=False, help_text=_("Django admin access."))
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    # When the password last changed. Every JWT issued before this moment is
    # refused at authentication, which is how changing a password signs other
    # devices out.
    #
    # Stamped in `set_password`, so an administrator reset and the
    # `set_password` management command cut off stolen sessions exactly as a
    # self-service change does — the case that matters most is the one where
    # the account holder is not the one asking.
    password_changed_at = models.DateTimeField(null=True, blank=True, editable=False)

    history = HistoricalRecords()  # §9 audit trail

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["full_name"]
        indexes = [models.Index(fields=["role", "account_status"])]

    def set_password(self, raw_password):
        """Stamp the moment, so tokens issued earlier stop working.

        Overridden here rather than in the serializer because the serializer is
        not the only caller: the admin, `createsuperuser` and the
        `set_password` management command all arrive through this method, and a
        rule that holds on one route only is not a rule. The case that matters
        most is the one where the account holder is not the one asking.
        """
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()

    def save(self, *args, **kwargs):
        """Keep `password_changed_at` with the password it describes.

        Every caller that resets a password saves narrowly —
        `update_fields=["password"]` — which wrote the new hash and dropped the
        stamp, so the sessions the change was meant to end carried on. The
        administrator reset was the one that mattered most and the one that
        failed. Rather than fix three call sites and hope the fourth remembers,
        the stamp travels with the column.
        """
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            if "password" in update_fields:
                update_fields.add("password_changed_at")
                kwargs["update_fields"] = update_fields
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    # -- access helpers ---------------------------------------------------

    @property
    def access(self):
        """This user's row from ACCESS_MATRIX (spec §7), or nothing if unlisted."""
        return ACCESS_MATRIX.get(self.role, NO_ACCESS)

    def case_scope(self):
        return self.access["case_scope"]

    def referral_scope(self):
        return self.access["referral_scope"]

    def can_write_cases(self):
        return self.access["case_write"]

    def can_write_referrals(self):
        return self.access["referral_write"]

    def group_scope(self):
        """WLT group visibility (WLT handoff §9)."""
        return self.access["group_scope"]

    def can_write_groups(self):
        return self.access["group_write"]

    def can_record_delivery(self):
        """May this role record what a service actually delivered.

        Separate from `case_write` because §7 separates them: an employer
        liaison may not edit a case record and **is** the person who records the
        placement and makes the 30/60/90-day calls. Gating her on `case_write`
        left her unable to action her own queue, which is the one thing that
        screen exists for.

        Covers Training Enrolment (§4.5), Placement (§4.7) and, when Sprint 6
        lands, Enterprise (§4.8) — the entities that hang off a case and are
        written by the person who did the work rather than by the case owner.
        """
        return self.access["delivery_write"]

    @property
    def wlt_approval_level(self):
        """Approval level in the WLT chain, or None if this role approves nothing.

        Read by `wlt.services` rather than compared against a role name, so the
        chain in `ServiceLinkageType.approval_chain` stays configuration.
        """
        return WLT_APPROVAL_LEVELS.get(self.role)

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

        # A WLT account scoped to a geography and given none sees an empty
        # system that looks like a working one — the same failure `partner`
        # above guards against, so it is refused the same way. The federal
        # officer is unscoped by design and the facilitator is scoped by the
        # groups she runs, so neither is required to carry one.
        if self.role in {Role.WLT_WOREDA_OFFICER, Role.WLT_REGION_OFFICER} and not self.wlt_scope_location_id:
            errors["wlt_scope_location"] = _("A WLT woreda or region officer needs an assigned geography.")

        if self.role not in Role.wlt_roles() and self.wlt_scope_location_id:
            errors["wlt_scope_location"] = _("Only WLT accounts carry a WLT scope.")

        if errors:
            raise ValidationError(errors)


class EmailKind(models.TextChoices):
    WORK = "WORK", _("Work")
    PERSONAL = "PERSONAL", _("Personal")


class UserEmail(BaseModel):
    """One email address, held by one account.

    The uniqueness the programme asked for is a property of the *address*, not
    of a column, so the address is the row. Two constraints carry it, both in
    the database rather than in a serializer:

    - `unique_address` — a case-insensitive unique index across every row, so
      an address cannot be registered twice however it is filed. Two flat
      columns could not express this: `unique=True` on each would still permit
      one account's work address to equal another's personal, or its own.
    - `one_per_kind` — a user holds at most one work and one personal address.

    Case-insensitive because mailboxes are: `A@x.com` and `a@x.com` are one
    inbox, and a constraint that let both through would enforce nothing.
    """

    user = models.ForeignKey(
        "users.User",
        verbose_name=_("user"),
        related_name="emails",
        on_delete=models.CASCADE,
        help_text=_("Deleting the account removes its addresses; they mean nothing without it."),
    )
    kind = models.CharField(_("kind"), max_length=16, choices=EmailKind.choices)
    address = models.EmailField(_("address"))

    history = HistoricalRecords()  # §9 audit trail

    class Meta:
        verbose_name = _("user email")
        verbose_name_plural = _("user emails")
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(
                Lower("address"),
                name="user_email_unique_address",
                violation_error_message=_("Another account already uses this email address."),
            ),
            models.UniqueConstraint(
                fields=["user", "kind"],
                name="user_email_one_per_kind",
                violation_error_message=_("That account already has an address of this kind."),
            ),
        ]

    def __str__(self):
        return f"{self.address} ({self.get_kind_display()})"

    def save(self, *args, **kwargs):
        # Normalised on the way in, so the unique index and the value agree.
        self.address = UserEmail.normalize(self.address)
        return super().save(*args, **kwargs)

    @staticmethod
    def normalize(address):
        """Trim, and lowercase the domain — the half that is case-insensitive
        by RFC. The local part is left alone; the unique index is what makes
        the comparison case-insensitive."""
        from django.contrib.auth.models import BaseUserManager

        return BaseUserManager.normalize_email((address or "").strip())
