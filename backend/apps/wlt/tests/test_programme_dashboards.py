"""Tiers 2 to 4 of the WLT dashboard handoff.

What is worth asserting is the four rules that make these numbers safe to
publish, not the shape of the payload: the maturation guard, the suppression
bands, never ranking by rate, and protection referrals never reaching a
group-subject card.
"""

import pytest

from apps.wlt.services import programme

pytestmark = pytest.mark.django_db


def test_the_maturation_guard_never_reports_a_young_cohort_as_a_failure(woreda_officer, wlt_group):
    """The P2 gate needs 52 weeks since P1 entry, so in pilot month six no group
    can pass it. Reporting "31 of 250" instead of "31 of 88 eligible" is the
    single most likely way to publish a false negative about this pilot.
    """
    maturity = programme.tier("results", woreda_officer)["group_maturity"]

    assert "not_yet_eligible" in maturity
    assert "eligible" in maturity
    # The rate's denominator is the eligible groups, never every group.
    assert maturity["rate"]["d"] == maturity["eligible"]


def test_a_rate_over_too_few_groups_is_suppressed_not_printed(woreda_officer, wlt_group):
    """Three of five regions sit near or below 30 groups. The handoff is
    explicit that this is the machinery working, not a defect to solve by
    dropping the bands."""
    maturity = programme.tier("results", woreda_officer)["group_maturity"]
    if maturity["eligible"] < 30:
        assert maturity["rate"]["band"] in ("suppressed", "provisional")
        assert maturity["rate"]["percent"] is None or maturity["rate"]["band"] == "provisional"


def test_the_portfolio_table_sorts_by_exposure_and_never_by_par(woreda_officer, wlt_group):
    """Ranking by PAR at these denominators sorts by luck and is politically
    irreversible once published."""
    table = programme.tier("programme", woreda_officer)["portfolio_quality"]

    amounts = [float(row["outstanding_etb"]) for row in table["rows"]]
    assert amounts == sorted(amounts, reverse=True)
    assert "never by PAR" in table["note"]


def test_fund_adequacy_stays_in_weeks_and_separates_the_unmeasured(woreda_officer, wlt_group):
    """Restating it in birr reintroduces the inflation and comparability problem
    the definition was written to remove. A group with no bylaw has no week
    figure, and counting it in the lowest band would report it as the
    programme's worst rather than as unmeasured."""
    card = programme.tier("programme", woreda_officer)["fund_adequacy"]

    assert card["unit"] == "weeks_of_contribution"
    assert "not_measured" in card
    # Binned at the gate: the count under twelve weeks is what P2 is holding.
    assert card["bins"][0]["band"] == "0–12"


def test_the_coaching_card_says_its_rows_do_not_sum_to_a_group_count(woreda_officer, wlt_group):
    """A group appears under every condition it fails, and most failing groups
    fail more than one."""
    card = programme.tier("woreda", woreda_officer)["blocking_p2"]
    assert "do not sum to a group count" in card["note"]


def test_the_approval_queue_carries_the_oldest_items_age(woreda_officer, wlt_group):
    """Age, not just count. A phase transition sitting eighteen days is the
    finding, and an average of four days hides it."""
    for row in programme.tier("woreda", woreda_officer)["approval_queue"]:
        assert "oldest_days" in row
        if row["count"]:
            assert row["oldest_days"] is not None


def test_at_risk_counts_as_surviving(woreda_officer, wlt_group):
    """`DEFINITIONS.md` says at-risk is an early warning that does not by itself
    move a group backwards. The materialised view puts it in `faltering`, which
    understates survival by the whole at-risk population."""
    from apps.wlt.models import Group, GroupStatus

    Group.objects.filter(pk=wlt_group.pk).update(status=GroupStatus.AT_RISK)
    cohorts = programme.tier("programme", woreda_officer)["cohort_survival"]
    row = next(row for row in cohorts if row["size"])

    assert row["surviving"] >= 1


def test_a_protection_referral_never_reaches_a_group_card(woreda_officer, wlt_group):
    """The database constraint stops a disclosure landing on a group record; it
    does not stop a card aggregating one into a view somebody can drill into."""
    funnel = programme.tier("programme", woreda_officer)["linkage_funnel"]

    codes = {row.get("type_code") for row in funnel["stages"]} | {
        row.get("type_code") for row in funnel["block_reasons"]
    }
    assert "protection_referral" not in codes


def test_the_blocked_cards_say_so_rather_than_reporting_zero(woreda_officer, wlt_group):
    """CLA formation is schema and gates only until stage 9, and ME-1 needs
    results-framework wording nobody has supplied. A zero would be a claim."""
    assert programme.tier("woreda", woreda_officer)["cla_readiness"]["available"] is False
    assert programme.tier("results", woreda_officer)["results_framework"]["available"] is False


def test_every_tier_says_how_stale_it_is(woreda_officer, wlt_group):
    for name in ("woreda", "programme", "results"):
        assert programme.tier(name, woreda_officer)["as_of"]
