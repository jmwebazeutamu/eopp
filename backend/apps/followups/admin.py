"""Follow-up admin — read-only.

A contact log is a record of attempts. One that can be edited afterwards is not
evidence of anything, including the "4+ failed attempts" CM-4 counts, and
`services.record_attempt` is the only writer.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import FollowUp


@admin.register(FollowUp)
class FollowUpAdmin(SimpleHistoryAdmin):
    list_display = [
        "case",
        "attempt_date",
        "contact_method",
        "contact_outcome",
        "related_referral",
        "pathway_revision_flag",
        "conducted_by",
    ]
    list_filter = ["contact_outcome", "contact_method", "pathway_revision_flag"]
    search_fields = ["case__youth__full_name", "notes"]
    date_hierarchy = "attempt_date"

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
