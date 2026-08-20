"""WLT admin.

Definition of Done §10.1(4): new configuration data is entered through the admin,
not hardcoded. For this module that means three tables — `PolicyParameter`,
`EnrolmentAllocation` and `ServiceLinkageType` — and they are the reason decision
D6 exists: FSCO will revise a threshold mid-pilot and the alternative is a deploy
per revision.

Everything else here is registered **read-only**. The ledger is append-only and
phase decisions are immutable, both enforced by trigger, so an admin form that
offered to edit them would present a save button the database refuses. A group's
lifecycle moves through `services`, which runs the gates and writes the evidence;
an admin that could set `status = ACTIVE` would skip all of it.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    CLA,
    BeneficiaryProfile,
    BylawVersion,
    Delegate,
    EnrolmentAllocation,
    Federation,
    FormationEvent,
    Group,
    GroupMembership,
    ImportMatchCandidate,
    LedgerEntry,
    Loan,
    Meeting,
    MobilisationEvent,
    OfficeHolder,
    PhaseEvent,
    PolicyParameter,
    PolicyVersion,
    RiskFlag,
    ServiceLinkage,
    ServiceLinkageType,
    StructuralMembership,
    SyncConflict,
    ValidationOverride,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Visible, searchable, and not editable here.

    These records are written by the service layer, which runs the gates and
    leaves the evidence. A form that wrote them directly would produce rows the
    rest of the module cannot explain.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Configuration — the tables an administrator owns (§10.1(4))
# ---------------------------------------------------------------------------


@admin.register(PolicyParameter)
class PolicyParameterAdmin(SimpleHistoryAdmin):
    list_display = ["key", "value", "scope_location", "effective_from", "effective_to", "note"]
    list_filter = ["key", "effective_from"]
    search_fields = ["key", "note"]
    autocomplete_fields = ["scope_location"]
    fieldsets = (
        (None, {"fields": ("key", "value", "note")}),
        (
            _("Where and when it applies"),
            {
                "fields": ("scope_location", "effective_from", "effective_to"),
                "description": _(
                    "Leave the place empty for the global value. A more specific place overrides a less "
                    "specific one. To supersede a value, set its end date and add a new row — never edit "
                    "one in place, or decisions taken under the old rule become unexplainable."
                ),
            },
        ),
    )


@admin.register(EnrolmentAllocation)
class EnrolmentAllocationAdmin(SimpleHistoryAdmin):
    list_display = ["location", "phase_label", "target_members", "target_groups", "effective_from"]
    list_filter = ["phase_label"]
    autocomplete_fields = ["location"]


@admin.register(ServiceLinkageType)
class ServiceLinkageTypeAdmin(SimpleHistoryAdmin):
    list_display = ["label", "code", "min_phase", "restricted", "is_active", "sort_order"]
    list_filter = ["is_active", "restricted"]
    search_fields = ["code", "label"]
    fieldsets = (
        (None, {"fields": ("code", "label", "description", "is_active", "sort_order")}),
        (
            _("What it may be raised against"),
            {
                "fields": ("allowed_subject_types", "min_phase", "gate_set"),
                "description": _(
                    "Subject types are GROUP, CLA and FEDERATION. Removing a type from this list stops new "
                    "linkages of that shape immediately; existing ones are unaffected."
                ),
            },
        ),
        (
            _("Approval"),
            {
                "fields": ("approval_chain", "lapse_days", "restricted"),
                "description": _("Roles in order. An override of a blocked gate adds one more level."),
            },
        ),
    )


@admin.register(PolicyVersion)
class PolicyVersionAdmin(ReadOnlyAdmin):
    list_display = ["label", "created_at"]


# ---------------------------------------------------------------------------
# Registry and formation
# ---------------------------------------------------------------------------


@admin.register(BeneficiaryProfile)
class BeneficiaryProfileAdmin(SimpleHistoryAdmin):
    list_display = ["person", "psnp_client_id", "enrolment_route", "verification_status", "verified_on"]
    list_filter = ["verification_status", "enrolment_route", "literacy_level", "has_device"]
    search_fields = ["person__full_name", "psnp_client_id"]
    autocomplete_fields = ["person", "psnp_woreda", "psnp_kebele", "verified_by"]


@admin.register(Group)
class GroupAdmin(SimpleHistoryAdmin):
    list_display = ["name", "kebele", "status", "current_phase", "activated_on", "facilitator"]
    list_filter = ["status", "current_phase", "kebele"]
    search_fields = ["name"]
    autocomplete_fields = ["kebele", "facilitator", "mobilisation_event"]
    # Lifecycle fields move through `services.formation` and `services.phase`,
    # which run the gates and write the evidence snapshot.
    readonly_fields = ["status", "current_phase", "constituted_on", "activated_on", "phase_entered_on"]


@admin.register(MobilisationEvent)
class MobilisationEventAdmin(SimpleHistoryAdmin):
    list_display = ["kebele", "held_on", "endorsement_obtained", "facilitator"]
    list_filter = ["endorsement_obtained", "kebele"]
    search_fields = ["kebele__name", "endorsement_note"]
    autocomplete_fields = ["kebele", "facilitator"]


@admin.register(BylawVersion)
class BylawVersionAdmin(ReadOnlyAdmin):
    list_display = ["group", "version_no", "effective_from", "effective_to", "contribution_etb", "meeting_cadence"]
    list_filter = ["meeting_cadence", "service_charge_basis"]
    search_fields = ["group__name"]


@admin.register(GroupMembership)
class GroupMembershipAdmin(ReadOnlyAdmin):
    list_display = ["person", "group", "joined_on", "exited_on", "exit_reason"]
    search_fields = ["person__full_name", "group__name"]


@admin.register(OfficeHolder)
class OfficeHolderAdmin(ReadOnlyAdmin):
    list_display = ["group", "role", "person", "from_date", "to_date"]
    list_filter = ["role"]


@admin.register(ValidationOverride)
class ValidationOverrideAdmin(ReadOnlyAdmin):
    """Reviewed at woreda level — and a rule overridden everywhere is a rule
    that does not describe the programme."""

    list_display = ["group", "rule_code", "overridden_by", "created_at"]
    list_filter = ["rule_code"]


# ---------------------------------------------------------------------------
# Ledger — read-only, and the database enforces it too
# ---------------------------------------------------------------------------


@admin.register(Meeting)
class MeetingAdmin(ReadOnlyAdmin):
    list_display = ["group", "meeting_no", "held_on", "status", "counted_cash_etb", "device_id"]
    list_filter = ["status"]
    search_fields = ["group__name"]


@admin.register(LedgerEntry)
class LedgerEntryAdmin(ReadOnlyAdmin):
    list_display = ["group", "entry_type", "amount_etb", "account", "person", "created_at"]
    list_filter = ["entry_type", "account"]
    search_fields = ["group__name", "person__full_name"]


@admin.register(Loan)
class LoanAdmin(ReadOnlyAdmin):
    list_display = ["person", "group", "principal_etb", "status", "disbursed_on", "due_on"]
    list_filter = ["status", "purpose", "charge_basis"]
    search_fields = ["person__full_name", "group__name"]


@admin.register(PhaseEvent)
class PhaseEventAdmin(ReadOnlyAdmin):
    list_display = ["group", "from_phase", "to_phase", "direction", "submitted_by", "decided_by", "decided_at"]
    list_filter = ["direction", "to_phase"]
    search_fields = ["group__name"]


@admin.register(RiskFlag)
class RiskFlagAdmin(ReadOnlyAdmin):
    list_display = ["subject_type", "subject_id", "reason_code", "raised_on", "cleared_on"]
    list_filter = ["reason_code", "subject_type"]


@admin.register(SyncConflict)
class SyncConflictAdmin(ReadOnlyAdmin):
    list_display = ["group", "entity", "natural_key", "device_id", "created_at", "resolved_at"]
    list_filter = ["entity"]


@admin.register(ImportMatchCandidate)
class ImportMatchCandidateAdmin(ReadOnlyAdmin):
    """Never auto-merged. A woreda officer decides, with both rows in view."""

    list_display = ["import_batch", "matched_person", "confidence", "resolution", "resolved_by"]
    list_filter = ["resolution", "import_batch"]


# ---------------------------------------------------------------------------
# Linkage and structure
# ---------------------------------------------------------------------------


@admin.register(ServiceLinkage)
class ServiceLinkageAdmin(ReadOnlyAdmin):
    list_display = ["linkage_type", "subject_type", "provider", "status", "opened_on", "activated_on"]
    list_filter = ["status", "linkage_type", "subject_type"]


@admin.register(CLA)
class CLAAdmin(SimpleHistoryAdmin):
    list_display = ["name", "kebele", "formed_on", "status"]
    list_filter = ["status"]
    search_fields = ["name"]
    autocomplete_fields = ["kebele"]


@admin.register(Federation)
class FederationAdmin(SimpleHistoryAdmin):
    list_display = ["name", "woreda", "formed_on", "status", "legal_status"]
    list_filter = ["status", "legal_status"]
    search_fields = ["name"]
    autocomplete_fields = ["woreda"]


@admin.register(FormationEvent)
class FormationEventAdmin(ReadOnlyAdmin):
    list_display = ["target_type", "geography", "status", "opened_on", "expires_on", "decided_at"]
    list_filter = ["status", "target_type"]


@admin.register(StructuralMembership)
class StructuralMembershipAdmin(ReadOnlyAdmin):
    list_display = ["parent_type", "parent_id", "child_type", "child_id", "joined_on", "exited_on"]
    list_filter = ["parent_type", "child_type"]


@admin.register(Delegate)
class DelegateAdmin(ReadOnlyAdmin):
    list_display = ["person", "group", "cla", "from_date", "to_date"]
    search_fields = ["person__full_name", "group__name"]
