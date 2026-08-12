"""Admin for the referral engine.

The taxonomy models are the point of this screen: §9 makes the system
administrator the owner of the category, outcome and failure-code lists, and
§10.1 requires new terms to be entered here rather than hardcoded. Every model
uses SimpleHistoryAdmin so those changes are logged for audit, as §9 asks.
"""

from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Referral
from .taxonomy import FailureReasonCode, OutcomeType, ReferralCategory


class _TaxonomyAdmin(SimpleHistoryAdmin):
    list_display = ["label", "code", "is_active", "sort_order"]
    list_filter = ["is_active"]
    search_fields = ["code", "label"]
    ordering = ["sort_order", "label"]

    def has_delete_permission(self, request, obj=None):
        # Deactivate instead: historical referrals still point at the term, and
        # the §8 dashboards group by it.
        return False


@admin.register(ReferralCategory)
class ReferralCategoryAdmin(_TaxonomyAdmin):
    list_display = ["label", "code", "exempt_from_parallel_cap", "requires_note", "is_active", "sort_order"]
    list_filter = ["is_active", "exempt_from_parallel_cap"]
    fieldsets = (
        (None, {"fields": ("code", "label", "description", "sort_order", "is_active")}),
        (
            "Behaviour",
            {
                "fields": ("exempt_from_parallel_cap", "requires_note"),
                "description": (
                    "Exempt categories run alongside the two-referral parallel cap rather than counting "
                    "toward it (spec §6.3). This is a working default pending Phase 1 sign-off."
                ),
            },
        ),
    )


@admin.register(OutcomeType)
class OutcomeTypeAdmin(_TaxonomyAdmin):
    filter_horizontal = ["applies_to"]
    fieldsets = (
        (None, {"fields": ("code", "label", "description", "sort_order", "is_active")}),
        (
            "Applicability",
            {
                "fields": ("applies_to", "requires_note"),
                "description": "Leave 'applies to' empty to allow this outcome for any referral category (spec §5.3).",
            },
        ),
    )


@admin.register(FailureReasonCode)
class FailureReasonCodeAdmin(_TaxonomyAdmin):
    list_display = ["label", "code", "requires_note", "is_active", "sort_order"]


@admin.register(Referral)
class ReferralAdmin(SimpleHistoryAdmin):
    list_display = [
        "case",
        "referral_category",
        "status",
        "referral_trigger",
        "receiving_partner",
        "initiated_date",
        "is_parallel",
    ]
    list_filter = ["status", "referral_trigger", "referral_category", "is_parallel"]
    search_fields = ["case__youth__full_name", "receiving_partner__partner_name"]
    ordering = ["-initiated_date"]
    list_select_related = ["case", "case__youth", "referral_category", "receiving_partner"]
    autocomplete_fields = ["case", "receiving_partner", "initiated_by"]

    # The state machine (§6.2) owns these. Editing them here would bypass the
    # transition table, the required-field rules and the parallel bookkeeping.
    readonly_fields = [
        "status",
        "referral_trigger",
        "is_parallel",
        "parallel_group_id",
        "parent_referral",
        "replacement_referral",
        "confirmation_status",
        "confirmed_date",
        "outcome_date",
        "failure_date",
    ]

    def has_delete_permission(self, request, obj=None):
        return False
