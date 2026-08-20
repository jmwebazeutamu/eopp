"""Enterprise admin.

Disbursement, trading and closure are read-only: each moves more than a field.
`services.record_disbursement` refuses money against an unapproved plan and
moves the case to Placed; an admin edit that set the date alone would produce a
disbursement no control saw and a case status nobody derived.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Enterprise, EnterpriseMilestone


class MilestoneInline(admin.TabularInline):
    model = EnterpriseMilestone
    extra = 0
    readonly_fields = ["status", "completion_date"]


@admin.register(Enterprise)
class EnterpriseAdmin(SimpleHistoryAdmin):
    list_display = [
        "case",
        "business_name",
        "sector",
        "business_plan_status",
        "support_type",
        "grant_or_loan_amount",
        "disbursement_date",
        "market_linkage_status",
    ]
    list_filter = ["business_plan_status", "support_type", "market_linkage_status", "business_registration_status"]
    search_fields = ["case__youth__full_name", "business_name", "sector"]
    autocomplete_fields = ["case", "source_referral", "recorded_by"]
    readonly_fields = [
        "business_plan_status",
        "support_type",
        "grant_or_loan_amount",
        "disbursement_date",
        "started_trading_on",
        "closed_on",
        "closure_reason",
    ]
    inlines = [MilestoneInline]


@admin.register(EnterpriseMilestone)
class EnterpriseMilestoneAdmin(admin.ModelAdmin):
    list_display = ["enterprise", "milestone_name", "target_date", "status", "completion_date"]
    list_filter = ["status"]
    search_fields = ["milestone_name", "enterprise__business_name"]
