"""The Sprint 6 figures — verification, enterprise survival, grievances.

Same shape and the same rules as `outcomes.py`: every rate goes through
`rules.rate` so the suppression bands apply, absent is never zero, and a
denominator that cannot be measured says so in words.

One figure here matters more than the others. **The verification gap** — the
distance between the placement rate the platform can compute and the one §8.3
says is reportable — has been quietly present since the dashboards were built.
Until Sprint 6 there was no follow-up to close it with, so it could not even be
counted. It can now, and a number nobody can act on has become a queue.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.enterprises.models import Enterprise
from apps.enterprises.services import survival_inputs
from apps.followups.models import ContactOutcome, FollowUp
from apps.followups.services import awaiting_follow_up, unverified_outcomes
from apps.grievances.models import Grievance
from apps.grievances.services import (
    median_days_to_resolution,
    partner_quality_feedback,
    resolution_inputs,
)
from apps.users.permissions import scope_queryset

from .rules import rate

NO_ENTERPRISES_YET = _("Not measurable yet: no enterprise has received support.")
NO_GRIEVANCES_YET = _("Not measurable yet: no grievance has been concluded.")
NO_OUTCOMES_YET = _("Not measurable yet: no referral has recorded an outcome.")

# OQ-adjacent: survival is measured six months after **disbursement**, which is
# the only anchor an enterprise record carries. It is deliberately not the
# retention anchor placements use — a business and a job fail in different ways
# and on different clocks — and the label says which one it is.
SURVIVAL_MONTHS = 6


def scoped_casework(user):
    """Enterprises, follow-ups and grievances, narrowed to §7.

    Grievances scope on their **own** woreda rather than through a case: §4.10
    makes the case optional, and a complaint from an employer names no youth.
    """
    enterprises = scope_queryset(
        Enterprise.objects.all(),
        user,
        scope_kind="case",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    )
    follow_ups = scope_queryset(
        FollowUp.objects.all(),
        user,
        scope_kind="case",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    )
    grievances = scope_queryset(
        Grievance.objects.all(),
        user,
        scope_kind="case",
        woreda_field="woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    ).visible_to(user)
    return enterprises, follow_ups, grievances


# ---------------------------------------------------------------------------
# Verification — the gap §8.3 has always implied
# ---------------------------------------------------------------------------


def verification_gap(referrals):
    """Recorded outcomes against the ones somebody stood behind.

    §8.3 makes the externally-verified subset the reportable headline. That
    subset was always computable; what was missing was any way to *move* an
    outcome into it, and therefore any point in reporting how many were outside.
    Sprint 6's follow-up is that route, so the gap is now a queue with a number
    on it rather than a permanent shortfall.
    """
    recorded = referrals.with_recorded_outcome().count()
    if not recorded:
        return {"available": False, "reason": str(NO_OUTCOMES_YET)}

    verified = referrals.externally_verified().count()
    return {
        "available": True,
        "rate": rate(verified, recorded),
        "recorded": recorded,
        "verified": verified,
        "unverified": unverified_outcomes(referrals).count(),
        "note": str(
            _(
                "Self-reported outcomes are not verified. A follow-up that reached the youth is what moves one "
                "into this figure."
            )
        ),
    }


def follow_up_pressure(referrals, follow_ups, threshold_days=None):
    """How much contact work is outstanding, and how well contact is going.

    The reach rate is banded like everything else: a reach rate over four
    attempts says nothing about whether a caseload is contactable.
    """
    threshold_days = threshold_days or settings.FOLLOW_UP_DUE_DAYS
    attempts = follow_ups.count()

    return {
        "due": awaiting_follow_up(referrals, threshold_days).count(),
        "threshold_days": threshold_days,
        "attempts": attempts,
        "reach_rate": rate(follow_ups.reached().count(), attempts) if attempts else None,
        "pathway_revisions_flagged": follow_ups.filter(pathway_revision_flag=True).count(),
        "unreachable_youth": follow_ups.filter(contact_outcome=ContactOutcome.UNREACHABLE)
        .values("case_id")
        .distinct()
        .count(),
    }


# ---------------------------------------------------------------------------
# Enterprise
# ---------------------------------------------------------------------------


def enterprise_panel(enterprises, today=None):
    """The self-employment pathway, with the two things it must not conflate.

    A grant disbursed is not a business trading, and a business trading is not a
    business that survived. All three are separate counts, and the survival rate
    is measured only over enterprises old enough to have reached the anchor.
    """
    supported = enterprises.with_support_disbursed()
    if not supported.exists():
        return {
            "available": False,
            "reason": str(NO_ENTERPRISES_YET),
            "plans_in_progress": enterprises.exclude(business_plan_status="NOT_STARTED").count(),
            "awaiting_disbursement": enterprises.awaiting_disbursement().count(),
        }

    surviving, mature = survival_inputs(enterprises, months=SURVIVAL_MONTHS, as_of=today)
    return {
        "available": True,
        "supported": supported.count(),
        "trading": enterprises.trading().count(),
        "registered": enterprises.registered().count(),
        "awaiting_disbursement": enterprises.awaiting_disbursement().count(),
        "survival": {
            "label": str(_("Still open %(months)s months after support") % {"months": SURVIVAL_MONTHS}),
            "rate": rate(surviving, mature) if mature else None,
            "mature": mature,
            "note": str(_("Measured only over enterprises supported long enough to reach the anchor.")),
        },
        "milestones_overdue": sum(enterprise.milestones_overdue for enterprise in enterprises),
    }


# ---------------------------------------------------------------------------
# Grievances
# ---------------------------------------------------------------------------


def grievance_panel(grievances, today=None):
    """Whether the complaints channel actually works.

    Two numbers do the work: how many are open past the standard, and how long
    a complaint takes to conclude. A resolution *rate* alone reads well for a
    channel that closes everything unresolved, which is why `resolved` and
    `closed` are counted apart — as §4.10 keeps them apart.
    """
    total = grievances.count()
    if not total:
        return {"available": False, "reason": str(NO_GRIEVANCES_YET), "open": 0}

    resolved, concluded = resolution_inputs(grievances)
    overdue = grievances.overdue(settings.GRIEVANCE_RESPONSE_DAYS, as_of=today)

    return {
        "available": concluded > 0,
        "reason": "" if concluded else str(NO_GRIEVANCES_YET),
        "total": total,
        "open": grievances.open().count(),
        "overdue": overdue.count(),
        "threshold_days": settings.GRIEVANCE_RESPONSE_DAYS,
        "resolution_rate": rate(resolved, concluded) if concluded else None,
        "closed_unresolved": concluded - resolved,
        "median_days_to_resolution": median_days_to_resolution(grievances),
        "about_referral_quality": grievances.about_referral_quality().count(),
    }


def partner_feedback_rows(user):
    """Referral-quality complaints by partner — §4.11's qualitative counterpart.

    Unscoped by design and stated as such: a partner operates across woredas,
    and a complaint count filtered to one woreda would understate a partner's
    record everywhere else. Only roles that can already read programme-wide
    figures reach this panel.
    """
    return partner_quality_feedback()


def casework_panel(user, referrals, today=None):
    """Everything Sprint 6 adds to a dashboard, in one call."""
    enterprises, follow_ups, grievances = scoped_casework(user)
    return {
        "verification": verification_gap(referrals),
        "follow_up": follow_up_pressure(referrals, follow_ups),
        "enterprise": enterprise_panel(enterprises, today=today),
        "grievances": grievance_panel(grievances, today=today),
    }
