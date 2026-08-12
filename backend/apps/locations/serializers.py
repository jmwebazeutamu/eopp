from rest_framework import serializers

from .models import Location


class LocationSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    full_path = serializers.CharField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)

    class Meta:
        model = Location
        fields = ["code", "name", "level", "level_display", "parent", "parent_name", "full_path", "is_active"]
        read_only_fields = fields
