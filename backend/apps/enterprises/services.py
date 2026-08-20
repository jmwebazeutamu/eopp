"""Enterprise operations — spec §4.8.

Two rules the rest of the platform relies on:

* **Disbursement is a transfer, not a decision.** `record_disbursement` needs an
  amount and a support type, and it is what moves the case to Placed — an
  approved plan with no money is not self-employment.
* **A milestone is missed, never deleted.** A plan whose missed milestones
  disappear reads as a plan that went well, and the whole point of §4.8's
  sub-table is that somebody can be asked about the ones that slipped.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import (
    BusinessPlanStatus,
    enterprise_referral_error,
    Enterprise,
    EnterpriseMilestone,
    MarketLinkageStatus,
    MilestoneStatus,
    SupportType,
)


class EnterpriseError(ValidationError):
    """A refused enterprise operation."""


@transaction.atomic
def open_enterprise(*, case, recorded_by, source_referral=None, **fields):
    """Start the self-employment record for a youth."""
    # §4.8 enterprise records come from a referral, and which referrals is a flag
    # on the category row. One predicate, shared with the serializer and `clean()`.
    problem = enterprise_referral_error(source_referral, case)
    if problem:
        raise EnterpriseError({"source_referral": problem})

    enterprise = Enterprise(case=case, recorded_by=recorded_by, source_referral=source_referral, **fields)
    enterprise.full_clean()
    enterprise.save()
    case.touch()
    return enterprise


@transaction.atomic
def set_plan_status(enterprise, *, status, note="", actor=None):
    """Move the business plan along.

    `REVISION_REQUESTED` is a first-class status and not a rejection: most first
    plans come back for revision, and filing that as a failure would report a
    coaching workload as a rejection rate.
    """
    enterprise.business_plan_status = status
    if note:
        enterprise.notes = f"{enterprise.notes}\n{note}".strip()
    enterprise.full_clean()
    enterprise.save()
    enterprise.case.touch()
    return enterprise


@transaction.atomic
def record_disbursement(enterprise, *, amount, support_type, disbursed_on=None, actor=None):
    """Money or goods actually reached the youth.

    Refused before the plan is approved: a disbursement against an unapproved
    plan is either a data error or a control failure, and both want catching at
    the moment somebody types it rather than in an audit.
    """
    if enterprise.business_plan_status not in BusinessPlanStatus.approved_statuses():
        raise EnterpriseError(_("Approve the business plan before recording a disbursement."))
    if support_type == SupportType.NONE:
        raise EnterpriseError({"support_type": _("Say whether this was a grant, a loan or in-kind support.")})
    if amount is None or amount <= 0:
        raise EnterpriseError({"grant_or_loan_amount": _("Record how much was disbursed.")})

    enterprise.support_type = support_type
    enterprise.grant_or_loan_amount = amount
    enterprise.disbursement_date = disbursed_on or date.today()
    enterprise.full_clean()
    enterprise.save()

    _mark_case_placed(enterprise)
    enterprise.case.touch()
    return enterprise


def _mark_case_placed(enterprise):
    """Self-employment is a placement outcome for the case (§4.2).

    One-way, exactly as the referral engine and the placement service do it:
    `PLACED` is also a judgement a case manager may set by hand, and a cascade
    that could clear it would lose a human decision.
    """
    from apps.cases.models import CaseStatus

    case = enterprise.case
    if case.case_status != CaseStatus.PLACED:
        case.case_status = CaseStatus.PLACED
        case.save(update_fields=["case_status", "last_activity_date", "updated_at"])


@transaction.atomic
def record_trading(enterprise, *, started_on=None, market_linkage_status=MarketLinkageStatus.TRADING, actor=None):
    """The business sold something.

    Deliberately its own date. A programme that treats the disbursement date as
    the start of trading reports its own transfer as the youth's result.
    """
    enterprise.started_trading_on = started_on or date.today()
    enterprise.market_linkage_status = market_linkage_status
    enterprise.full_clean()
    enterprise.save()
    enterprise.case.touch()
    return enterprise


@transaction.atomic
def add_milestone(enterprise, *, milestone_name, target_date, note=""):
    milestone = EnterpriseMilestone(
        enterprise=enterprise, milestone_name=milestone_name, target_date=target_date, note=note
    )
    milestone.full_clean()
    milestone.save()
    return milestone


@transaction.atomic
def achieve_milestone(milestone, *, completion_date=None, note="", actor=None):
    if milestone.status != MilestoneStatus.PENDING:
        raise EnterpriseError(_("This milestone has already been settled."))
    milestone.status = MilestoneStatus.ACHIEVED
    milestone.completion_date = completion_date or date.today()
    if note:
        milestone.note = note
    milestone.full_clean()
    milestone.save()
    milestone.enterprise.case.touch()
    return milestone


@transaction.atomic
def miss_milestone(milestone, *, reason, actor=None):
    """Record that a milestone was not met, with the reason.

    Not a deletion. The pattern is the same one the module uses everywhere: a
    record of what did not happen is what makes a programme explicable.
    """
    if milestone.status != MilestoneStatus.PENDING:
        raise EnterpriseError(_("This milestone has already been settled."))
    if not (reason or "").strip():
        raise EnterpriseError({"note": _("Say why the milestone was missed.")})
    milestone.status = MilestoneStatus.MISSED
    milestone.note = reason
    milestone.full_clean()
    milestone.save()
    return milestone


@transaction.atomic
def close_enterprise(enterprise, *, reason, closed_on=None, actor=None):
    """The business stopped."""
    if not (reason or "").strip():
        raise EnterpriseError({"closure_reason": _("Record why the business closed.")})
    if enterprise.closed_on is not None:
        raise EnterpriseError(_("This enterprise is already closed."))

    enterprise.closed_on = closed_on or date.today()
    enterprise.closure_reason = reason
    enterprise.full_clean()
    enterprise.save()
    enterprise.case.touch()
    return enterprise


def survival_inputs(enterprises, months=6, as_of=None):
    """`(surviving, mature)` — enterprises still open N months after disbursement.

    Two numbers rather than a rate, so the caller bands it. `mature` counts only
    the enterprises old enough to have reached the anchor: including a business
    disbursed last week would report it as a failure it has had no chance to be.
    """
    as_of = as_of or date.today()
    supported = enterprises.with_support_disbursed()
    mature = [enterprise for enterprise in supported if (as_of - enterprise.disbursement_date).days >= months * 30]
    surviving = [enterprise for enterprise in mature if enterprise.closed_on is None]
    return len(surviving), len(mature)
