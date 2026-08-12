from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Youth


@admin.register(Youth)
class YouthAdmin(SimpleHistoryAdmin):
    list_display = ["full_name", "sex", "age", "woreda", "psnp_status", "consent_given", "registration_date"]
    list_filter = ["sex", "woreda", "psnp_status", "disability_status", "consent_given"]
    search_fields = ["full_name", "phone_number", "national_or_kebele_id", "household_id"]
    ordering = ["full_name"]
    list_select_related = ["registering_worker"]
    readonly_fields = ["registration_date", "created_at", "updated_at", "age"]

    fieldsets = (
        ("Identity", {"fields": ("full_name", "sex", "date_of_birth", "age")}),
        ("Contact", {"fields": ("phone_number", "national_or_kebele_id")}),
        ("Location", {"fields": ("region", "zone", "woreda", "kebele")}),
        ("Programme linkage", {"fields": ("household_id", "psnp_status")}),
        ("Profile", {"fields": ("education_level", "disability_status")}),
        ("Consent (spec §9)", {"fields": ("consent_given", "consent_date")}),
        ("Registration", {"fields": ("registering_worker", "registration_date", "created_at", "updated_at")}),
    )

    @admin.display(description="Age")
    def age(self, obj):
        return obj.age if obj.pk else "-"

    def has_delete_permission(self, request, obj=None):
        return False
