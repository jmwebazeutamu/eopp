"""Scheduled jobs — handoff README §8 ("compute nightly"), backlog S6.2.

Every job here **observes**; none of them decides. Dormancy is set because the
clock says so and is reversible by holding a meeting; at-risk is raised and
cleared automatically because it is a description of the data. What no job does
is graduate a group, promote one, or fail a linkage that a person has not looked
at — those are governance decisions with an approver on the record, and a job
that took them would make the approval a formality.

The one job that changes a status without a person is `lapse_stale_approvals`,
and it is a status the counterparty caused: an approved linkage the bank never
opened.
"""

from celery import shared_task
from django.utils import timezone

from .models import Group, GroupStatus, RiskFlag, RiskReason
from .services import formation as formation_service
from .services import indicators as indicator_service
from .services import linkage as linkage_service
from .services import structure as structure_service
from .services.ledger import clear_risk_flag, raise_risk_flag


@shared_task
def refresh_group_indicators():
    """Recompute at-risk and dormancy for every operating group.

    Also runs on write — a meeting close recomputes that group immediately,
    because the readiness card changing the moment the till balances is most of
    what makes the card worth having. This is the nightly backstop for the
    conditions that change with the calendar rather than with a write: a group
    that has simply stopped meeting produces no event to react to.
    """
    today = timezone.localdate()
    touched = 0

    for group in Group.objects.operating().select_related("kebele"):
        figures = indicator_service.compute(group, as_of=today)
        current = set(figures.risk_reasons)

        for reason in current:
            raise_risk_flag(group, reason, detail={"as_of": today.isoformat()})

        # An unbalanced till is raised by the close attempt and cleared by a
        # successful one. It is not recomputable from indicators, so a sweep
        # that cleared everything not currently in `risk_reasons` would clear it
        # the same night it was raised.
        recomputable = set(RiskReason.values) - {RiskReason.UNBALANCED_TILL}
        for reason in recomputable - current:
            clear_risk_flag(group, reason)

        dormant = figures.is_dormant
        if dormant and group.status == GroupStatus.ACTIVE:
            group.status = GroupStatus.DORMANT
            group.save(update_fields=["status", "updated_at"])
        elif not dormant and group.status == GroupStatus.DORMANT:
            group.status = GroupStatus.ACTIVE
            group.save(update_fields=["status", "updated_at"])
        elif group.status == GroupStatus.ACTIVE and current:
            group.status = GroupStatus.AT_RISK
            group.save(update_fields=["status", "updated_at"])
        elif group.status == GroupStatus.AT_RISK and not current and not dormant:
            group.status = GroupStatus.ACTIVE
            group.save(update_fields=["status", "updated_at"])

        touched += 1

    return {"groups": touched, "open_flags": RiskFlag.objects.open().count()}


@shared_task
def expire_formations():
    """Drafts, constitutions and formation events nobody finished.

    All retained, never deleted. Three abandoned constitutions in one kebele is
    a mobilisation problem, and it is invisible if only successes are stored.
    """
    return {
        "groups": formation_service.expire_stale_drafts(),
        "formation_events": structure_service.expire_stale_events(),
    }


@shared_task
def lapse_linkages():
    """Approved linkages the counterparty never activated."""
    return {"lapsed": linkage_service.lapse_stale_approvals()}


@shared_task
def review_blacklisted_providers():
    """Flag open linkages with a blacklisted provider. Never close them.

    The obligation still exists — the group's money is still in that account —
    so an automatic closure would misstate the group's position and lose the
    thread needed to recover it.
    """
    return {"flagged": len(linkage_service.flag_blacklisted_providers())}


@shared_task
def refresh_reporting_views():
    """Rebuild the WLT materialized views."""
    from .reporting import refresh

    return refresh()
