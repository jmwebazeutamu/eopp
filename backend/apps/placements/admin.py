"""Placement admin.

The exit fields are read-only: recording an exit through `services.record_exit`
also closes the outstanding retention checkpoints, and an admin edit that set
the date alone would leave three checks pending against a job that has ended —
which is a phone call to somebody about a placement she left months ago.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Placement, RetentionCheck


class RetentionCheckInline(admin.TabularInline):
    model = RetentionCheck
    extra = 0
    readonly_fields = ["checkpoint", "due_date", "status", "checked_on", "checked_by", "note"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        # The three checks are opened with the placement. Adding a fourth here
        # would create a checkpoint no reminder knows about.
        return False


@admin.register(Placement)
class PlacementAdmin(SimpleHistoryAdmin):
    list_display = [
        "case",
        "employer_name",
        "sector",
        "placement_type",
        "placement_date",
        "is_subsidised",
        "exit_date",
        "exit_reason",
    ]
    list_filter = ["placement_type", "is_subsidised", "contract_type", "exit_reason"]
    search_fields = ["case__youth__full_name", "employer_name", "sector"]
    autocomplete_fields = ["case", "source_referral", "recorded_by"]
    readonly_fields = ["exit_date", "exit_reason", "exit_note"]
    date_hierarchy = "placement_date"
    inlines = [RetentionCheckInline]


@admin.register(RetentionCheck)
class RetentionCheckAdmin(admin.ModelAdmin):
    list_display = ["placement", "checkpoint", "due_date", "status", "checked_on", "checked_by"]
    list_filter = ["status", "checkpoint"]
    search_fields = ["placement__case__youth__full_name", "placement__employer_name"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Answered through `services.record_check`, which stamps the actor §9
        # requires. A form that wrote the status without one would produce a
        # retention figure nobody stands behind.
        return False
