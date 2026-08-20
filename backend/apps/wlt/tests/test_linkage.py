"""Service linkage lifecycle — backlog stage 7, README §6.5.

The five rules of §6.5, each with the failure it prevents:

1. Gates at screening **and again at approval** — a subject drifting below
   threshold while the paperwork moves.
2. An evidence snapshot on every transition — an approval nobody can reconstruct.
3. `BLOCKED` as a first-class state — a facilitator who knows she failed but not
   what she needs.
4. An override escalates the chain — a waved condition approved by the same
   level that waved it.
5. Distress cascades — a group showing green while the federation it guaranteed
   is in default.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.partners.models import Standing
from apps.wlt.models import (
    CLA,
    ChildType,
    Group,
    LinkageStatus,
    ParentType,
    Phase,
    RiskReason,
    ServiceLinkage,
    StructuralMembership,
)
from apps.wlt.services import linkage as linkage_service
from apps.wlt.services.linkage import LinkageError

pytestmark = pytest.mark.django_db


@pytest.fixture
def bank(make_partner):
    from apps.partners.models import PartnerType

    return make_partner(
        name="Amhara Rural Bank",
        partner_type=PartnerType.BANK if hasattr(PartnerType, "BANK") else None,
        woredas=["Dessie Zuria"],
    )


@pytest.fixture
def p2_group(wlt_group):
    Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)
    wlt_group.refresh_from_db()
    return wlt_group


def test_a_savings_account_screens_clean_for_a_p2_group(p2_group, bank, facilitator):
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    assert linkage.status == LinkageStatus.SCREENED
    assert linkage.block_reasons == []


def test_a_p1_group_is_blocked_and_told_exactly_what_it_needs(wlt_group, bank, facilitator):
    """Rule 3. The most behaviour-changing screen in the module is the one that
    says "Phase reached: Phase 1 (need Phase 2)" rather than showing a red dot."""
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=wlt_group, provider=bank, actor=facilitator
    )
    assert linkage.status == LinkageStatus.BLOCKED
    assert linkage.block_reasons
    reasons = " ".join(linkage.block_reasons)
    assert "Phase" in reasons and "need" in reasons


def test_a_blocked_linkage_is_rescreened_rather_than_raised_again(wlt_group, bank, facilitator):
    """The block history stays on one record, so the funnel can say how long a
    group waited and what moved."""
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=wlt_group, provider=bank, actor=facilitator
    )
    Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)

    linkage_service.screen(linkage, actor=facilitator)
    assert linkage.status == LinkageStatus.SCREENED
    assert linkage.events.count() == 2
    assert ServiceLinkage.objects.count() == 1


def test_every_transition_records_its_evidence(p2_group, bank, facilitator):
    """Rule 2. The snapshot carries the conditions, not a verdict."""
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    event = linkage.events.first()
    assert event.gate_snapshot["conditions"]
    assert "threshold" in event.gate_snapshot["conditions"][0]
    assert event.gate_snapshot["policy_version_id"]


def test_gates_are_evaluated_again_at_approval(p2_group, bank, facilitator, woreda_officer):
    """Rule 1, and the reason it exists: the group that was screened at P2 is not
    the group being approved if it has since fallen back."""
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    assert linkage.status == LinkageStatus.PENDING_APPROVAL

    Group.objects.filter(pk=p2_group.pk).update(current_phase=Phase.P1)

    linkage_service.approve(linkage, actor=woreda_officer)
    assert linkage.status == LinkageStatus.BLOCKED
    assert linkage.block_reasons


def test_the_proposer_cannot_approve_her_own_linkage(p2_group, bank, facilitator):
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    with pytest.raises(LinkageError):
        linkage_service.approve(linkage, actor=facilitator)


def test_a_blocked_linkage_needs_an_override_reason_to_be_submitted(wlt_group, bank, facilitator):
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=wlt_group, provider=bank, actor=facilitator
    )
    with pytest.raises(LinkageError):
        linkage_service.submit_for_approval(linkage, actor=facilitator)


def test_an_override_escalates_the_chain_by_one_level(wlt_group, bank, facilitator):
    """Rule 4. Whoever waves a condition is not the person who then approves alone."""
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=wlt_group, provider=bank, actor=facilitator
    )
    before = linkage.approvals.count()

    linkage_service.submit_for_approval(
        linkage, actor=facilitator, override_reason="Bank branch closing; the account must open now."
    )

    assert linkage.approvals.count() == before + 1
    assert linkage.approvals.filter(is_escalation=True).exists()
    assert linkage.status == LinkageStatus.PENDING_APPROVAL


def test_a_two_level_chain_needs_both_levels(p2_group, bank, facilitator, woreda_officer, region_officer):
    Group.objects.filter(pk=p2_group.pk).update(current_phase=Phase.P3)
    p2_group.refresh_from_db()

    linkage = linkage_service.propose(
        linkage_type="cooperative_membership", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)

    linkage_service.approve(linkage, actor=woreda_officer)
    assert linkage.status == LinkageStatus.PENDING_APPROVAL

    linkage_service.approve(linkage, actor=region_officer)
    assert linkage.status == LinkageStatus.APPROVED


def test_one_person_cannot_approve_two_levels_of_the_same_chain(
    p2_group, bank, facilitator, woreda_officer, region_officer
):
    """No self-approval, at every level rather than only the last.

    A thin office where one person holds two roles is exactly the case the
    approval chain exists for.
    """
    from apps.users.models import Role

    Group.objects.filter(pk=p2_group.pk).update(current_phase=Phase.P3)
    p2_group.refresh_from_db()
    linkage = linkage_service.propose(
        linkage_type="cooperative_membership", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    linkage_service.approve(linkage, actor=woreda_officer)

    woreda_officer.role = Role.WLT_REGION_OFFICER
    woreda_officer.save(update_fields=["role"])
    with pytest.raises(LinkageError):
        linkage_service.approve(linkage, actor=woreda_officer)


def test_activation_opens_the_bank_side_of_the_ledger(p2_group, bank, facilitator, woreda_officer):
    """W4: activating a savings account turns one balance into two, and a
    deposit before that is refused."""
    from apps.wlt.services import ledger as ledger_service
    from apps.wlt.services.ledger import LedgerError

    with pytest.raises(LedgerError):
        ledger_service.deposit_to_bank(p2_group, amount_etb=500, actor=facilitator)

    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    linkage_service.approve(linkage, actor=woreda_officer)
    linkage_service.activate(linkage, actor=facilitator)

    entry = ledger_service.deposit_to_bank(p2_group, amount_etb=500, actor=facilitator)
    assert entry.amount_etb == Decimal("500.00")


def test_an_approved_linkage_the_counterparty_never_opened_lapses(p2_group, bank, facilitator, woreda_officer):
    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    linkage_service.approve(linkage, actor=woreda_officer)

    linkage.approved_on = date.today() - timedelta(days=200)
    linkage.save(update_fields=["approved_on"])

    assert linkage_service.lapse_stale_approvals() == 1
    linkage.refresh_from_db()
    assert linkage.status == LinkageStatus.LAPSED


def test_blacklisting_a_provider_flags_open_linkages_and_does_not_close_them(
    p2_group, bank, facilitator, woreda_officer
):
    """The obligation still exists — the group's money is still in that account."""
    from apps.wlt.models import RiskFlag

    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    linkage_service.submit_for_approval(linkage, actor=facilitator)
    linkage_service.approve(linkage, actor=woreda_officer)
    linkage_service.activate(linkage, actor=facilitator)

    bank.standing = Standing.BLACKLISTED
    bank.save()

    flagged = linkage_service.flag_blacklisted_providers()
    linkage.refresh_from_db()

    assert len(flagged) == 1
    assert linkage.status == LinkageStatus.ACTIVE
    assert RiskFlag.objects.open().for_group(p2_group).filter(reason_code=RiskReason.EXTERNAL_DISTRESS).exists()


def test_a_blacklisted_provider_cannot_take_a_new_linkage(p2_group, bank, facilitator):
    bank.standing = Standing.BLACKLISTED
    bank.save()
    with pytest.raises(LinkageError):
        linkage_service.propose(linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator)


def test_a_provider_is_only_proposable_where_it_operates(p2_group, make_partner, facilitator):
    """A bank present in Amhara is often absent in Afar."""
    from apps.wlt.models import ServiceLinkageType

    here = make_partner(name="Dessie Branch Bank", woredas=["Dessie Zuria"])
    elsewhere = make_partner(name="Afar Only Bank", woredas=["Chifra"])

    proposable = linkage_service.proposable_providers(ServiceLinkageType.objects.get(code="savings_account"), p2_group)
    names = set(proposable.values_list("partner_name", flat=True))
    assert here.partner_name in names
    assert elsewhere.partner_name not in names


def test_distress_on_a_cla_cascades_to_its_member_groups(p2_group, bank, facilitator, woreda_officer, wlt_locations):
    """Rule 5. A group cannot honestly show green while the body it belongs to
    is in default."""
    from apps.wlt.models import RiskFlag

    cla = CLA.objects.create(name="Dessie CLA", kebele=wlt_locations["kebele"], formed_on=date(2027, 2, 1))
    StructuralMembership.objects.create(
        parent_type=ParentType.CLA,
        parent_id=cla.pk,
        child_type=ChildType.GROUP,
        child_id=p2_group.pk,
        joined_on=date(2027, 2, 1),
    )

    linkage = ServiceLinkage.objects.create(
        linkage_type_id="market_offtake",
        provider=bank,
        subject_cla=cla,
        status=LinkageStatus.ACTIVE,
        opened_on=date(2027, 3, 1),
        activated_on=date(2027, 3, 1),
    )
    linkage_service.mark_distressed(linkage, reason="Two deliveries missed.")

    assert RiskFlag.objects.open().for_group(p2_group).filter(reason_code=RiskReason.EXTERNAL_DISTRESS).exists()


def test_a_lifecycle_move_the_machine_does_not_have_is_refused(p2_group, bank, facilitator):
    from apps.wlt.models import LinkageTransitionError

    linkage = linkage_service.propose(
        linkage_type="savings_account", subject=p2_group, provider=bank, actor=facilitator
    )
    with pytest.raises(LinkageTransitionError):
        linkage.transition_to(LinkageStatus.ACTIVE, actor=facilitator)
