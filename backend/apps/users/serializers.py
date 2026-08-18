"""Serializers for User (spec §4.12)."""

from django.contrib.auth.password_validation import validate_password
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.locations.models import Location, LocationLevel

from .models import ACCESS_MATRIX, AccountStatus, Role, User


class UserSerializer(serializers.ModelSerializer):
    """Read/write representation used by the administrator's user management UI."""

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    partner_name = serializers.CharField(source="partner.partner_name", read_only=True, default=None)
    password = serializers.CharField(write_only=True, required=False, style={"input_type": "password"})
    # Annotated by the viewset; 0 for an account that manages no cases.
    caseload_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "work_email",
            "personal_email",
            "work_phone",
            "personal_phone",
            "full_name",
            "role",
            "role_display",
            "woreda_assignment",
            "partner",
            "partner_name",
            "account_status",
            "caseload_count",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "last_login", "date_joined"]

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        role = attrs.get("role", getattr(self.instance, "role", None))
        woredas = attrs.get("woreda_assignment", getattr(self.instance, "woreda_assignment", []))
        partner = attrs.get("partner", getattr(self.instance, "partner", None))

        # A woreda-scoped role with no woredas can see nothing, which reads as a
        # broken account rather than a deliberate restriction. Catch it at entry.
        if role in {Role.OUTREACH_WORKER, Role.CASE_MANAGER, Role.SUPERVISOR} and not woredas:
            raise serializers.ValidationError(
                {"woreda_assignment": f"Role {role} is woreda-scoped and needs at least one woreda."}
            )

        # Mirrors User.clean (§4.12) so the API reports a field error rather than
        # letting an inconsistent account reach the database.
        if role == Role.PARTNER_STAFF and not partner:
            raise serializers.ValidationError(
                {"partner": "Referral partner staff must be linked to a partner organisation."}
            )
        if role != Role.PARTNER_STAFF and partner:
            raise serializers.ValidationError(
                {"partner": "Only referral partner staff are linked to a partner organisation."}
            )

        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Required when creating a user."})
        return User.objects.create_user(password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class CurrentUserSerializer(serializers.ModelSerializer):
    """`/me/` — what the web and mobile clients read to build their navigation.

    Exposes the resolved §7 access row so the frontend can hide actions the API
    would reject anyway. The API still enforces independently; this is for UX.
    """

    role_display = serializers.CharField(source="get_role_display", read_only=True)
    partner_name = serializers.CharField(source="partner.partner_name", read_only=True, default=None)
    access = serializers.SerializerMethodField()
    scopable_woredas = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "work_email",
            "personal_email",
            "work_phone",
            "personal_phone",
            "full_name",
            "role",
            "role_display",
            "woreda_assignment",
            "partner",
            "partner_name",
            "account_status",
            "access",
            "scopable_woredas",
        ]
        read_only_fields = fields

    def get_scopable_woredas(self, obj):
        """Woredas this account may narrow a screen to.

        The shell's scope selector reads this. `woreda_assignment` cannot serve
        the purpose on its own: an ALL-scope account — administrator, programme
        manager, M&E — carries an empty assignment, which is why the header
        rendered "Woreda: —" for exactly the users who can see every woreda.

        An ALL scope gets the programme's woredas from the location reference
        data; everyone else gets their own assignment, because that is already
        the only set `ScopedQuerySetMixin` will return rows for. Offering more
        would offer a filter that silently returns nothing.
        """
        if str(ACCESS_MATRIX.get(obj.role, {}).get("case_scope", "")) == "ALL":
            return list(
                Location.objects.filter(level=LocationLevel.WOREDA, is_active=True)
                .order_by("name")
                .values_list("name", flat=True)
            )
        return list(obj.woreda_assignment or [])

    def get_access(self, obj):
        # Scopes are TextChoices and must serialise as their string value;
        # the write flags stay real booleans so clients can test them directly.
        matrix = ACCESS_MATRIX.get(obj.role, {})
        return {key: value if isinstance(value, bool) else str(value) for key, value in matrix.items()}


class ScopedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Refuse tokens to accounts that are not operational.

    Django's `is_active` check happens in `authenticate()`, but spec §4.12 keeps
    a separate `account_status`. A SUSPENDED account with `is_active=True` would
    otherwise still be issued a 14-day refresh token.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        if self.user.account_status != AccountStatus.ACTIVE:
            raise serializers.ValidationError("This account is not active.")
        data["user"] = CurrentUserSerializer(self.user).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        # Claims the mobile client reads offline, when it cannot call /me/.
        token["role"] = user.role
        token["full_name"] = user.full_name
        return token


class AssignableUserSerializer(serializers.ModelSerializer):
    """Minimal shape for assignment pickers.

    §7 keeps user management with the system administrator, so this deliberately
    exposes only what is needed to choose an assignee — no email, account status
    or partner link.
    """

    class Meta:
        model = User
        fields = ["id", "full_name", "woreda_assignment"]
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    """What a user may change about their own account.

    Deliberately a separate serializer from `UserSerializer` rather than a
    permission check on it. `UserSerializer` writes `role`, `woreda_assignment`,
    `partner` and `account_status`; exposing it on a self-service route would
    make privilege escalation a matter of adding one field to a request body.
    Here those fields are not writable because they are not present, which is
    the difference between a rule and a boundary.

    §7 stays the administrator's to set. §9's trail comes from
    `HistoricalRecords` on the model, so a self-edit is attributed like any
    other.
    """

    class Meta:
        model = User
        fields = ["full_name", "work_email", "personal_email", "work_phone", "personal_phone"]

    def validate_work_email(self, value):
        return self._unique_email(value)

    def validate_personal_email(self, value):
        return self._unique_email(value)

    def _unique_email(self, value):
        """Normalised, and not already claimed by any account in either slot.

        Neither column carries a unique constraint, so two accounts can hold
        one address. That is tolerable while sign-in is by username and stops
        being tolerable the moment a password reset is sent to an address — so
        it is refused here rather than discovered then.

        Both columns are checked, not just the matching one: an address is one
        address, and "someone else has it as their personal" is the same
        collision as "someone else has it as their work".
        """
        if not value:
            return value
        value = User.objects.normalize_email(value).strip()
        clash = User.objects.filter(Q(work_email__iexact=value) | Q(personal_email__iexact=value))
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError(_("Another account already uses this email address."))
        return value

    def validate(self, attrs):
        """The two addresses on one account must also differ from each other."""
        work = (attrs.get("work_email") or getattr(self.instance, "work_email", "")).lower()
        personal = (attrs.get("personal_email") or getattr(self.instance, "personal_email", "")).lower()
        if work and work == personal:
            raise serializers.ValidationError(
                {"personal_email": _("Use a different address from your work email, or leave it blank.")}
            )
        return attrs

    def validate_full_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError(_("A name is required."))
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """A user changing their own password.

    `current_password` is required even though the caller is authenticated:
    an access token lasts an hour and these are shared machines, so a screen
    left unlocked must not be enough to take the account over.
    """

    current_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError(_("That is not your current password."))
        return value

    def validate_new_password(self, value):
        # Django's configured validators — length, common passwords, similarity
        # to the username. Passing the user is what enables the last of those.
        validate_password(value, user=self.context["request"].user)
        return value

    def validate(self, attrs):
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": _("The new password must be different.")})
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
