from rest_framework import serializers

from .models import Location


class LocationSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    full_path = serializers.CharField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    # Emit the parent's `code`, not its primary key. `code` is unique but NOT the
    # primary key, so the default PrimaryKeyRelatedField rendered an integer here
    # while every other identifier in this API — including the viewset's own
    # `lookup_field` — is the code. Clients cascading a hierarchy compared
    # `child.parent` against `parent.code` and got a silent, permanent mismatch.
    parent = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = Location
        fields = ["code", "name", "level", "level_display", "parent", "parent_name", "full_path", "is_active"]
        read_only_fields = fields
