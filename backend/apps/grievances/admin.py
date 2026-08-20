"""Grievance admin.

The resolution fields are read-only: `services.resolve` refuses a resolution
with no description of what was done, and a resolution rate computed over status
changes nobody described is the kind of figure that survives until somebody asks
for an example.

Note that the admin does **not** apply the sensitive-type narrowing the API
does. Admin access is already the widest access the platform grants, and §9
attributes every read to a named account; narrowing here would suggest a
protection the admin does not provide.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Grievance


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
