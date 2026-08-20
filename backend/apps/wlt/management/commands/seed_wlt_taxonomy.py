"""Seed the linkage taxonomy — the handoff's §6.4 table, as configuration.

Two tables get rows, and the split is the module's central design decision:

* **`wlt.ServiceLinkageType`** — the gated pathways. Savings account, market
  offtake, cooperative membership and registration, credit facility. Each
  carries the subjects it permits, the phase it opens at, and its approval
  chain. All three are data, so FSCO can widen or narrow a pathway without a
  deployment.

* **`referrals.ReferralCategory`** — the two that ride the existing referral
  engine unchanged. A service referral may name a person or a group; a
  protection referral may name **a person only**, which is how handbook §3.6's
  confidentiality norm becomes a database constraint rather than a convention. A
  GBV disclosure can never land on a group timeline.

Idempotent. Existing rows are left alone: once a programme has edited a
threshold or widened a subject list, re-running a seed must not undo it.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.referrals.taxonomy import ReferralCategory
from apps.wlt.models import ServiceLinkageType

# code, label, subjects, earliest phase, approval chain, gate set, lapse days
LINKAGE_TYPES = [
    (
        "savings_account",
        "Group savings account",
        ["GROUP", "CLA", "FEDERATION"],
        "P2",
        ["WLT_WOREDA_OFFICER"],
        "savings_account",
        90,
        "Low risk, and it should happen early. Activating it turns the ledger into two balances.",
    ),
    (
        "market_offtake",
        "Market or offtake agreement",
        ["GROUP", "CLA", "FEDERATION"],
        "P2",
        ["WLT_WOREDA_OFFICER"],
        "market_offtake",
        90,
        "Lower ceremony, higher volume. Visible income benefit early, and no debt risk.",
    ),
    (
        "cooperative_membership",
        "Cooperative membership",
        ["GROUP", "CLA"],
        "P3",
        ["WLT_WOREDA_OFFICER", "WLT_REGION_OFFICER"],
        "cooperative_membership",
        180,
        "",
    ),
    (
        "cooperative_registration",
        "Cooperative registration",
        ["FEDERATION"],
        "P4",
        ["WLT_REGION_OFFICER", "WLT_FEDERAL_OFFICER"],
        "cooperative_registration",
        365,
        "A federation's legal registration is a linkage with its own lifecycle, not an attribute: "
        "it can fail and it can lapse.",
    ),
    (
        "credit_facility",
        "External credit facility",
        # No GROUP. Early linkage of savings groups to microfinance is the
        # clearest negative finding in the Ethiopian evidence base, so the
        # restriction is in the taxonomy as well as in `gate.credit.allow_group_subject`.
        ["CLA", "FEDERATION"],
        "P4",
        ["WLT_WOREDA_OFFICER", "WLT_REGION_OFFICER", "WLT_FEDERAL_OFFICER"],
        "credit_facility",
        90,
        "High risk. The friction is the point: six gates and four approval levels.",
    ),
]

# code, label, allowed subjects, description
REFERRAL_CATEGORIES = [
    (
        "wlt-service-referral",
        "WLT service referral",
        ["YOUTH", "GROUP"],
        "A woman or a savings group referred to an external service. The thinnest workflow in the "
        "group module, and the one that reuses the referral engine unchanged.",
    ),
    (
        "wlt-protection-referral",
        "Protection / GBV referral",
        # Person only, and it stays that way. Widening this list would put a
        # disclosure on a group timeline.
        ["YOUTH", "CASE"],
        "Confidential. Permitted for a person only — never for a group, a CLA or a federation.",
    ),
]


class Command(BaseCommand):
    help = "Seed the WLT linkage taxonomy and the two WLT referral categories. Idempotent."

    @transaction.atomic
    def handle(self, *args, **options):
        linkages = 0
        for code, label, subjects, phase, chain, gate_set, lapse, description in LINKAGE_TYPES:
            _row, created = ServiceLinkageType.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description,
                    "allowed_subject_types": subjects,
                    "min_phase": phase,
                    "approval_chain": chain,
                    "gate_set": gate_set,
                    "lapse_days": lapse,
                    "sort_order": 10 * (linkages + 1),
                },
            )
            linkages += int(created)

        categories = 0
        for code, label, subjects, description in REFERRAL_CATEGORIES:
            _row, created = ReferralCategory.objects.get_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description,
                    "allowed_subject_types": subjects,
                    "sort_order": 200,
                },
            )
            categories += int(created)

        self.stdout.write(
            self.style.SUCCESS(f"WLT taxonomy seeded: {linkages} linkage type(s), {categories} referral categor(ies).")
        )
