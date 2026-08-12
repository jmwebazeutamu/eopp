"""Serializers for Youth (spec §4.1)."""

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.locations.models import Location

from .models import Youth


class YouthSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    is_age_eligible = serializers.BooleanField(read_only=True)
    sex_display = serializers.CharField(source="get_sex_display", read_only=True)
    registering_worker_name = serializers.CharField(source="registering_worker.full_name", read_only=True)

    class Meta:
        model = Youth
        fields = [
            "id",
            "full_name",
            "sex",
            "sex_display",
            "date_of_birth",
            "age",
            "is_age_eligible",
            "phone_number",
            "national_or_kebele_id",
            "region",
            "zone",
            "woreda",
            "kebele",
            "household_id",
            "psnp_status",
            "education_level",
            "disability_status",
            "consent_given",
            "consent_date",
            "registration_date",
            "registering_worker",
            "registering_worker_name",
            "created_at",
            "updated_at",
        ]
        # registering_worker is taken from the authenticated user in `create` —
        # §4.1 makes it an accountability record, so a client must not choose it.
        read_only_fields = ["id", "registration_date", "registering_worker", "created_at", "updated_at"]

    def validate_woreda(self, value):
        """Keep the free-text location fields inside the controlled vocabulary.

        Spec §4.1 types these as text, so the database cannot enforce it. Without
        this check a typo silently removes the youth from their case manager's
        woreda-scoped queryset — the record exists but nobody can see it.
        """
        if not Location.objects.active().woredas().filter(name=value).exists():
            raise serializers.ValidationError(
                f"'{value}' is not a known active woreda. Choose one from /api/v1/locations/?level=WOREDA."
            )
        return value

    def validate_region(self, value):
        if not Location.objects.active().regions().filter(name=value).exists():
            raise serializers.ValidationError(f"'{value}' is not a known active region.")
        return value

    def validate(self, attrs):
        instance = self.instance
        woreda = attrs.get("woreda", getattr(instance, "woreda", None))
        zone = attrs.get("zone", getattr(instance, "zone", None))
        region = attrs.get("region", getattr(instance, "region", None))

        # A valid woreda under the wrong zone is still wrong. Check the chain.
        if woreda and zone:
            match = (
                Location.objects.active()
                .woredas()
                .filter(name=woreda, parent__name=zone, parent__parent__name=region)
                .exists()
            )
            if not match:
                raise serializers.ValidationError(
                    {"woreda": f"'{woreda}' does not sit under zone '{zone}' in region '{region}'."}
                )

        return attrs

    def create(self, validated_data):
        # §4.1: the registering worker is whoever is logged in.
        request = self.context.get("request")
        if not validated_data.get("registering_worker"):
            if not (request and request.user and request.user.is_authenticated):
                raise serializers.ValidationError(
                    {"registering_worker": "Cannot register a youth without an authenticated worker."}
                )
            validated_data["registering_worker"] = request.user
        return super().create(validated_data)

    def run_validation(self, data=serializers.empty):
        """Surface the model's `clean` errors as field errors, not a 500.

        Youth.clean carries the consent rules from §9. ModelSerializer does not
        call full_clean, so without this a consent violation would only fail at
        the database or not at all.

        On a partial update the incoming data holds only the changed fields, so
        the candidate is built from the stored instance first — otherwise every
        PATCH would re-run the consent check against an unset default and fail.
        """
        validated = super().run_validation(data)

        model_fields = {f.name for f in Youth._meta.get_fields() if hasattr(f, "attname")}
        candidate = Youth()
        if self.instance is not None:
            for field in model_fields:
                setattr(candidate, field, getattr(self.instance, field, None))
        for key, value in validated.items():
            if key in model_fields:
                setattr(candidate, key, value)

        try:
            candidate.clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return validated


class YouthSummarySerializer(serializers.ModelSerializer):
    """Compact form embedded in case listings."""

    age = serializers.IntegerField(read_only=True)

    class Meta:
        model = Youth
        fields = ["id", "full_name", "sex", "date_of_birth", "age", "phone_number", "woreda", "kebele"]
        read_only_fields = fields


class YouthIntakeSerializer(YouthSerializer):
    """Registration payload. Warns when the youth falls outside the age band."""

    age_band_warning = serializers.SerializerMethodField()

    class Meta(YouthSerializer.Meta):
        fields = YouthSerializer.Meta.fields + ["age_band_warning"]

    def get_age_band_warning(self, obj):
        # Deliberately a warning rather than a validation error: the programme
        # may knowingly register someone just outside the band, and blocking it
        # would push staff to falsify a date of birth. Surfaced so supervisors
        # can see it. Revisit once §11 confirms the band.
        if not obj.is_age_eligible:
            return (
                f"Age {obj.age} is outside the {settings.YOUTH_AGE_MIN}-{settings.YOUTH_AGE_MAX} "
                "youth band. Eligibility needs confirmation."
            )
        return None
