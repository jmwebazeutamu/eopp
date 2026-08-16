"""Serializers for User (spec §4.12)."""

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

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
            "email",
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

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "full_name",
            "role",
            "role_display",
            "woreda_assignment",
            "partner",
            "partner_name",
            "account_status",
            "access",
        ]
        read_only_fields = fields

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
