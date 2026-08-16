"""Tests for `manage.py seed_demo_referrals`.

The seeder exists to make the §6.4 timeline demonstrable, so what matters is
that it produces the shapes the timeline has to draw — a parallel group, a
replacement chain, an onward chain — and that it does so through the real
domain services rather than by writing statuses straight into the table.
"""

from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cases.models import Case
from apps.partners.models import Partner, PartnerType
from apps.referrals.management.commands.seed_demo_referrals import demo_id
from apps.referrals.models import Referral, ReferralStatus, ReferralTrigger

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo_partners(db, locations):
    """The seeder looks partners up by name, so the fixtures have to match."""
    names = [
        "Adama Health Centre",
        "Adama Polytechnic College",
        "Adama Skills Hub",
        "Bishoftu Automotive Plc",
        "Oromia Credit and Savings",
        "Rift Valley Enterprise Agency",
    ]
    return [
        Partner.objects.create(
            partner_name=name,
            partner_type=PartnerType.TVET_INSTITUTION,
            woreda_coverage=["Adama"],
            contact_name="Contact",
            phone=f"+2519110{index:05d}",
            email=f"p{index}@example.et",
        )
        for index, name in enumerate(names)
    ]


@pytest.fixture
def seeded(db, taxonomy, demo_partners, case_manager, outreach_worker):
    call_command("seed_demo_referrals", force=True, verbosity=0)


def case_for(slug):
    return Case.objects.get(id=demo_id("case", slug))


def referrals_for(slug):
    return Referral.objects.filter(case_id=demo_id("case", slug)).order_by("initiated_date")


# ---------------------------------------------------------------------------
# Guard
# ---------------------------------------------------------------------------


def test_refuses_to_write_case_data_without_debug_or_the_flag(taxonomy, demo_partners, case_manager, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError, match="not-production"):
        call_command("seed_demo_referrals", verbosity=0)
    assert not Case.objects.filter(id=demo_id("case", "sequential")).exists()


def test_runs_without_the_flag_when_debug_is_on(taxonomy, demo_partners, case_manager, outreach_worker, settings):
    settings.DEBUG = True
    call_command("seed_demo_referrals", verbosity=0)
    assert Case.objects.filter(id=demo_id("case", "sequential")).exists()


def test_needs_partners_to_refer_to(taxonomy, case_manager, settings):
    settings.DEBUG = True
    with pytest.raises(CommandError, match="three active partners"):
        call_command("seed_demo_referrals", verbosity=0)


# ---------------------------------------------------------------------------
# The shapes the timeline has to draw
# ---------------------------------------------------------------------------


def test_creates_one_case_per_scenario(seeded):
    for slug in ["sequential", "parallel", "replacement", "onward3", "mixed", "empty"]:
        assert Case.objects.filter(id=demo_id("case", slug)).exists(), slug


def test_the_empty_case_has_no_referrals(seeded):
    assert referrals_for("empty").count() == 0


def test_the_parallel_pair_shares_a_group(seeded):
    training, finance, complementary = referrals_for("parallel")
    assert training.parallel_group_id is not None
    assert training.parallel_group_id == finance.parallel_group_id
    assert training.is_parallel and finance.is_parallel


def test_the_exempt_referral_runs_alongside_without_joining_the_group(seeded):
    """§6.3's Complementary Service exemption — a third stream, not a third slot."""
    complementary = referrals_for("parallel")[2]
    assert complementary.referral_category.code == "COMPLEMENTARY_SERVICE"
    assert complementary.status == ReferralStatus.ACTIVE
    assert complementary.parallel_group_id is None
    assert not complementary.counts_toward_parallel_cap


def test_the_replacement_chain_is_linked_in_both_directions(seeded):
    failed, replacement = referrals_for("replacement")
    assert failed.status == ReferralStatus.REPLACED
    assert failed.replacement_referral_id == replacement.id
    assert replacement.parent_referral_id == failed.id
    assert replacement.referral_trigger == ReferralTrigger.REPLACEMENT
    assert failed.failure_reason_code is not None


def test_the_onward_chain_is_three_hops_deep(seeded):
    first, second, third = referrals_for("onward3")
    assert second.parent_referral_id == first.id
    assert third.parent_referral_id == second.id
    assert [r.referral_trigger for r in (second, third)] == [ReferralTrigger.ONWARD, ReferralTrigger.ONWARD]
    assert third.status == ReferralStatus.ACTIVE


def test_the_quiet_statuses_are_represented(seeded):
    cancelled, pending = referrals_for("mixed")
    assert cancelled.status == ReferralStatus.CANCELLED
    assert pending.status == ReferralStatus.PENDING_CONFIRMATION


# ---------------------------------------------------------------------------
# Backdating — the whole point
# ---------------------------------------------------------------------------


def test_referrals_span_months_rather_than_all_landing_today(seeded):
    dates = [r.initiated_date for r in Referral.objects.filter(notes__startswith="Demo data")]
    # The oldest referral is over six months back, and none of them is today's —
    # which is the state that made the timeline pointless on hand-made data.
    assert (date.today() - min(dates)).days > 180
    assert all(d < date.today() for d in dates)


def test_outcomes_are_backdated_too_so_bars_have_width(seeded):
    completed = referrals_for("onward3")[0]
    assert completed.status == ReferralStatus.COMPLETED
    assert completed.outcome_date is not None
    assert completed.outcome_date > completed.initiated_date
    assert completed.outcome_date < date.today()


def test_a_cancelled_referral_is_closed_at_a_backdated_updated_at(seeded):
    """The timeline reads updated_at for Cancelled, since §6.2 stamps no date."""
    cancelled = referrals_for("mixed")[0]
    assert cancelled.updated_at.date() < date.today()
    assert cancelled.updated_at.date() > cancelled.initiated_date


def test_case_activity_is_left_as_old_as_the_case(seeded):
    """Otherwise every demo case reads as touched this morning and never stalls."""
    assert case_for("onward3").last_activity_date < date.today()


# ---------------------------------------------------------------------------
# Re-running
# ---------------------------------------------------------------------------


def test_a_second_run_changes_nothing(seeded):
    before = Referral.objects.count()
    call_command("seed_demo_referrals", force=True, verbosity=0)
    assert Referral.objects.count() == before


def test_refresh_rebuilds_with_the_same_case_ids(seeded):
    original = referrals_for("parallel").count()
    call_command("seed_demo_referrals", force=True, refresh=True, verbosity=0)
    assert case_for("parallel")  # same id, so bookmarked URLs still work
    assert referrals_for("parallel").count() == original


def test_reset_removes_the_demo_records(seeded):
    call_command("seed_demo_referrals", force=True, reset=True, verbosity=0)
    assert not Case.objects.filter(id=demo_id("case", "parallel")).exists()
    assert Referral.objects.count() == 0
