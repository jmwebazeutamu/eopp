from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(SimpleHistoryAdmin):
    list_display = ["case", "alert_type", "status", "triggered_date", "assigned_to", "age_days"]
    list_filter = ["alert_type", "status", "triggered_date"]
    search_fields = ["case__youth__full_name", "summary"]
    ordering = ["-triggered_date"]
    list_select_related = ["case", "case__youth", "assigned_to"]
    autocomplete_fields = ["case", "assigned_to", "actioned_by"]

    # §4.13 alerts are raised by the detection jobs, not by hand. Editing the
    # trigger data would decouple the alert from the condition it represents.
    readonly_fields = ["case", "referral", "alert_type", "triggered_date", "threshold_days", "summary"]

    @admin.display(description="Age (days)")
    def age_days(self, obj):
        return obj.age_days

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
