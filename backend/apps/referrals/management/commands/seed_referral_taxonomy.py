"""Seed the referral taxonomy from spec §5.

These are the spec's starter lists, not final vocabulary. §5.4 says the failure
codes "need local validation with frontline staff during Phase 1. They are a
starting point, not a final list", and §9 puts the lists under the system
administrator's control. Re-running is safe: existing rows are updated in place
and nothing is deleted, so terms added through the admin survive.

    python manage.py seed_referral_taxonomy
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.referrals.taxonomy import FailureReasonCode, OutcomeType, ReferralCategory

# (code, label, description, exempt_from_parallel_cap, requires_note) — spec §5.1
CATEGORIES = [
    ("TRAINING", "Training", "Referral into Life Skills/Employability or TVET training.", False, False),
    ("EMPLOYMENT", "Employment / Placement", "Referral toward a wage job.", False, False),
    ("APPRENTICESHIP", "Apprenticeship", "Referral toward an apprenticeship placement.", False, False),
    ("ENTERPRISE", "Enterprise", "Referral toward enterprise start-up support.", False, False),
    (
        "FINANCE_ACCESS",
        "Finance Access",
        "Referral to a savings group, microfinance, or credit provider.",
        False,
        False,
    ),
    ("MARKET_LINKAGE", "Market Linkage", "Connects a youth-run enterprise to buyers or supply chains.", False, False),
    (
        "COMPLEMENTARY_SERVICE",
        "Complementary Service",
        "Health, psychosocial support, legal aid, nutrition, or social assistance top-up.",
        # §6.3 working default: runs as a third stream, outside the two-referral
        # cap. Pending Phase 1 sign-off (§11) — flip this flag in the admin if
        # the workshops decide it should count.
        True,
        False,
    ),
    ("COACHING", "Coaching", "Referral to a coaching or mentoring service.", False, False),
    ("OTHER", "Other", "Catch-all; requires a free-text note.", False, True),
]

# (code, label, applies_to_category_codes, requires_note, counts_as_placement) — spec §5.3
#
# `counts_as_placement` is what the programme dashboard's placement figures sum.
# The three that carry it are the outcomes that put a young person into paid work
# or into their own enterprise. Training Completion does not: finishing a TVET
# course closes the referral successfully without anyone being placed, and
# counting it would inflate the headline number the donor reads.
# `applies_to` widened 2026-08-18, closing punch-list G-1.
#
# Each category previously admitted exactly one specific outcome plus "Other",
# which made the outcome matrix a restatement of this table: every completed
# referral landed on the diagonal because nothing else was permitted. The card
# exists to expose the onward-referral gap — a training referral that completes
# and never becomes a job — and that crossover was unrepresentable.
#
# Widened only where the path is real: a training or apprenticeship placement
# can end in a job, and any referral can end in the youth taking up a service.
# Still a list the system administrator owns (§9); this is the starter set.
OUTCOME_TYPES = [
    (
        "SERVICE_UPTAKE",
        "Service Uptake",
        ["COMPLEMENTARY_SERVICE", "COACHING", "TRAINING", "APPRENTICESHIP", "ENTERPRISE", "FINANCE_ACCESS"],
        False,
        False,
    ),
    ("TRAINING_COMPLETION", "Training Completion", ["TRAINING", "APPRENTICESHIP"], False, False),
    # The crossover PM-3 exists to measure: training and apprenticeship
    # referrals that end in actual employment.
    ("JOB_PLACEMENT", "Job Placement", ["EMPLOYMENT", "TRAINING", "APPRENTICESHIP"], False, True),
    ("APPRENTICESHIP_START", "Apprenticeship Start", ["APPRENTICESHIP", "TRAINING"], False, True),
    ("ENTERPRISE_ENROLMENT", "Enterprise Enrolment", ["ENTERPRISE", "FINANCE_ACCESS", "TRAINING"], False, True),
    ("FINANCE_ACCESS", "Finance Access", ["FINANCE_ACCESS", "ENTERPRISE"], False, False),
    ("MARKET_LINKAGE_ESTABLISHED", "Market Linkage Established", ["MARKET_LINKAGE", "ENTERPRISE"], False, False),
    # Empty applies_to means "any category" — §5.3's Other row.
    ("OTHER", "Other", [], True, False),
]

# (code, label, description, requires_note) — spec §5.4
FAILURE_REASONS = [
    ("YOUTH_NO_SHOW", "Youth no-show", "Youth did not present to the receiving partner.", False),
    (
        "PARTNER_CAPACITY",
        "Partner capacity",
        "Receiving partner had no capacity (training slot, job vacancy, loan fund) at the time.",
        False,
    ),
    (
        "ELIGIBILITY_MISMATCH",
        "Eligibility mismatch",
        "Youth did not meet the receiving partner's eligibility criteria.",
        False,
    ),
    ("CONSENT_WITHDRAWN", "Consent withdrawn", "Youth withdrew consent or declined the referral.", False),
    (
        "PARTNER_NON_RESPONSIVE",
        "Partner non-responsive",
        "Receiving partner did not confirm or respond within the expected window.",
        False,
    ),
    (
        "DOCUMENTATION_INCOMPLETE",
        "Documentation incomplete",
        "Required documentation was missing or incomplete.",
        False,
    ),
    ("OTHER", "Other", "Requires a free-text note.", True),
]


class Command(BaseCommand):
    help = "Seed the spec §5 referral taxonomy. Idempotent; never deletes administrator-added terms."

    @transaction.atomic
    def handle(self, *args, **options):
        for order, (code, label, description, exempt, requires_note) in enumerate(CATEGORIES):
            ReferralCategory.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description,
                    "exempt_from_parallel_cap": exempt,
                    "requires_note": requires_note,
                    "sort_order": order * 10,
                    "is_active": True,
                },
            )
        self.stdout.write(f"  categories: {len(CATEGORIES)}")

        for order, (code, label, category_codes, requires_note, is_placement) in enumerate(OUTCOME_TYPES):
            outcome, _created = OutcomeType.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "requires_note": requires_note,
                    "counts_as_placement": is_placement,
                    "sort_order": order * 10,
                    "is_active": True,
                },
            )
            outcome.applies_to.set(ReferralCategory.objects.filter(code__in=category_codes))
        self.stdout.write(f"  outcome types: {len(OUTCOME_TYPES)}")

        for order, (code, label, description, requires_note) in enumerate(FAILURE_REASONS):
            FailureReasonCode.objects.update_or_create(
                code=code,
                defaults={
                    "label": label,
                    "description": description,
                    "requires_note": requires_note,
                    "sort_order": order * 10,
                    "is_active": True,
                },
            )
        self.stdout.write(f"  failure reasons: {len(FAILURE_REASONS)}")

        self.stdout.write(
            self.style.SUCCESS(
                "Referral taxonomy seeded. These are spec §5 starter lists — "
                "validate the failure codes with frontline staff during Phase 1 (§5.4)."
            )
        )
