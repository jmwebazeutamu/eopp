"""Admin for location reference data — spec §10 Sprint 1 ("Django admin wired for
reference data") and §9 ("taxonomy governance ... the system administrator role
should own changes to these lists post go-live").
"""

from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "parent", "code", "is_active"]
    list_filter = ["level", "is_active"]
    search_fields = ["name", "code"]
    ordering = ["level", "name"]
    list_select_related = ["parent"]
    autocomplete_fields = ["parent"]

    # Deletion is blocked by the PROTECT FK on children anyway, but locations are
    # also referenced by name from Youth and Case text fields, where the database
    # cannot protect them. Deactivating is the supported way to retire one.
    def has_delete_permission(self, request, obj=None):
        return False
