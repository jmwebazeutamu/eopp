"""Grievance admin.

The resolution fields are read-only: `services.resolve` refuses a resolution
with no description of what was done, and a resolution rate computed over status
changes nobody described is the kind of figure that survives until somebody asks
for an example.

Note that the admin does **not** apply the staff-conduct narrowing the API does.
Admin access is already the widest access the platform grants, and §9 attributes
every read to a named account; narrowing here would suggest a protection the
admin does not provide.

**Restricted records are the exception, and they are excluded outright.** The
API redacts them for anyone who is not a named focal point, and an admin list
that printed the summary in a column would make that redaction decorative. The
row is reachable in the admin by nobody: if a focal point needs it, she reads it
on the screen built for it, where the opening is logged.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Grievance, GrievanceAccess, SafeguardingFocalPoint


@admin.register(Grievance)
class GrievanceAdmin(SimpleHistoryAdmin):
    list_display = [
        "date_raised",
        "complaint_type",
        "raised_by",
        "woreda",
        "about_partner",
        "resolution_status",
        "assigned_staff",
    ]
    list_filter = ["resolution_status", "complaint_type", "raised_by", "referral_quality_feedback_flag", "woreda"]
    search_fields = ["summary", "complainant_name", "case__youth__full_name"]
    autocomplete_fields = ["case", "related_referral", "about_partner", "assigned_staff"]
    readonly_fields = ["resolution_status", "resolution_date", "resolution_notes", "referral_quality_feedback_flag"]
    date_hierarchy = "date_raised"

    def get_queryset(self, request):
        """Restricted records are not administered from here.

        See the module docstring: the redaction the API applies would be
        decorative if the same summary were one click away in a changelist.
        """
        return super().get_queryset(request).exclude(is_restricted=True)


@admin.register(SafeguardingFocalPoint)
class SafeguardingFocalPointAdmin(SimpleHistoryAdmin):
    """The named list. This is the one thing here that is meant to be edited.

    Kept in the admin rather than behind an API because it is configuration a
    named person maintains and §9 wants the change logged — the same reasoning
    that puts the referral taxonomy here.
    """

    list_display = ["woreda", "person", "from_date", "to_date", "is_lead"]
    list_filter = ["woreda", "is_lead"]
    search_fields = ["woreda", "person__full_name"]
    autocomplete_fields = ["person"]


@admin.register(GrievanceAccess)
class GrievanceAccessAdmin(admin.ModelAdmin):
    """Append-only, and read-only here for the same reason.

    A log a reader can tidy is not a log, so there is no add form, no change
    form and no delete action — only the list a safeguarding lead reads.
    """

    list_display = ["created_at", "reader", "role", "granted", "grievance"]
    list_filter = ["granted", "role"]
    readonly_fields = ["grievance", "reader", "role", "granted", "created_at"]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
