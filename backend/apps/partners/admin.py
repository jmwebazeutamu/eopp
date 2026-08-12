from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Partner


@admin.register(Partner)
class PartnerAdmin(SimpleHistoryAdmin):
    list_display = ["partner_name", "partner_type", "mou_status", "active_status", "contact_name", "phone"]
    list_filter = ["partner_type", "active_status", "mou_status"]
    search_fields = ["partner_name", "contact_name", "email", "phone"]
    ordering = ["partner_name"]

    fieldsets = (
        ("Organisation", {"fields": ("partner_name", "partner_type", "active_status")}),
        ("Coverage", {"fields": ("woreda_coverage",)}),
        ("Contact", {"fields": ("contact_name", "phone", "email")}),
        ("Agreement", {"fields": ("mou_status", "mou_date")}),
        ("Performance", {"fields": ("performance_notes",)}),
    )

    def has_delete_permission(self, request, obj=None):
        return False
