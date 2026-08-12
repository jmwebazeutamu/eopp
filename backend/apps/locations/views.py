"""Read-only location lookups.

Reference data, not case content: any authenticated user may read it, because
every client needs it to render a location dropdown. Editing happens in the
admin, which spec §9 assigns to the system administrator.
"""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Location
from .serializers import LocationSerializer


@extend_schema(tags=["locations"])
class LocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Location.objects.active().select_related("parent")
    serializer_class = LocationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "code"
    lookup_value_regex = "[^/]+"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["level", "parent"]
    search_fields = ["name", "code"]
    ordering_fields = ["name", "level"]
    ordering = ["name"]
    pagination_class = None  # the whole hierarchy is small and clients cache it
