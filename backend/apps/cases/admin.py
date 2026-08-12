from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Case, PathwayAssignment, ProfilingRecord


@admin.register(Case)
class CaseAdmin(SimpleHistoryAdmin):
    list_display = ["youth", "case_status", "case_manager", "woreda", "last_activity_date", "days_since_activity"]
    list_filter = ["case_status", "woreda"]
    search_fields = ["youth__full_name", "youth__phone_number"]
    ordering = ["-last_activity_date"]
    list_select_related = ["youth", "case_manager"]
    autocomplete_fields = ["youth", "case_manager", "next_action_owner"]
    readonly_fields = ["woreda", "last_activity_date", "created_at", "updated_at"]

    fieldsets = (
        ("Case", {"fields": ("youth", "case_status", "case_manager", "woreda")}),
        ("Timeline", {"fields": ("opened_date", "last_activity_date", "closed_date", "exit_reason")}),
        ("Next action", {"fields": ("next_action", "next_action_owner")}),
        ("Record", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Days since activity")
    def days_since_activity(self, obj):
        return obj.days_since_activity

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProfilingRecord)
class ProfilingRecordAdmin(SimpleHistoryAdmin):
    list_display = ["case", "assessed_date", "priority_flag", "vulnerability_index_score", "assessor"]
    list_filter = ["priority_flag", "assessed_date"]
    search_fields = ["case__youth__full_name"]
    ordering = ["-assessed_date"]
    list_select_related = ["case", "case__youth", "assessor"]
    autocomplete_fields = ["case", "assessor"]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PathwayAssignment)
class PathwayAssignmentAdmin(SimpleHistoryAdmin):
    list_display = ["case", "selected_pathway", "is_current", "assessment_date", "assessor"]
    list_filter = ["selected_pathway", "is_current"]
    search_fields = ["case__youth__full_name"]
    ordering = ["-assessment_date"]
    list_select_related = ["case", "case__youth", "assessor"]
    autocomplete_fields = ["case", "assessor", "superseded_by"]
    # is_current and superseded_by are maintained together by revise(); editing
    # either by hand can breach the one-current-pathway-per-case constraint.
    readonly_fields = ["is_current", "superseded_by"]

    def has_delete_permission(self, request, obj=None):
        return False
