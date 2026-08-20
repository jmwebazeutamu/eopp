"""Training enrolment admin.

The lifecycle fields are read-only here for the same reason they are read-only
in the serializer: completing a course sets a date, derives the onward-referral
trigger and stamps case activity, and `services.complete` is where all three
happen. An admin form that wrote the status directly would produce a completed
enrolment nobody is prompted to act on.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import TrainingEnrolment


@admin.register(TrainingEnrolment)
class TrainingEnrolmentAdmin(SimpleHistoryAdmin):
    list_display = [
        "case",
        "training_type",
        "training_provider",
        "start_date",
        "end_date",
        "completion_status",
        "attendance_rate",
    ]
    list_filter = ["completion_status", "training_type", "certificate_status", "training_provider"]
    search_fields = ["case__youth__full_name", "trade_or_skill_area", "training_provider__partner_name"]
    autocomplete_fields = ["case", "training_provider", "source_referral", "recorded_by"]
    readonly_fields = ["dropout_flag", "triggers_onward_referral", "onward_referral"]
    date_hierarchy = "enrolment_date"
