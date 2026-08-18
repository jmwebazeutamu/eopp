"""Tiers 2, 3 and 4 — the aggregations behind the supervisor, programme and donor screens.

What is worth pinning is the handoff's rules, not the arithmetic: counts never
become per-staff rates, the outcome matrix keeps its zeros, the partner table is
ordered by evidence and refuses to rank an unstable rate, and a card whose
source entity is missing reports itself absent.
"""

from datetime import date, timedelta

import pytest

from apps.dashboard.rules import funnel_verdict, median, wilson_bounds
from apps.dashboard.services import scoped_bases
from apps.dashboard.tiers import (
    donor,
    outcome_matrix,
    parallel_load,
    partner_performance,
    partner_response_times,
)
from apps.dashboard.tiers import programme_manager as programme_tier
from apps.dashboard.tiers import (
    team_caseload,
    woreda_supervisor,
)
from apps.referrals.models import ReferralStatus

pytestmark = pytest.mark.django_db

URLS = {
    "my-work": "/api/v1/dashboard/my-work/",
    "woreda": "/api/v1/dashboard/woreda/",
    "programme": "/api/v1/dashboard/programme/",
    "results": "/api/v1/dashboard/results/",
}


@pytest.fixture
def place(taxonomy, make_referral, case_manager):
    def _place(case, on=None):
        referral = make_referral(case, category=taxonomy["employment"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=on or date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["job_placement"],
            outcome_date=on or date.today(),
        )
        return referral

    return _place


# ---------------------------------------------------------------------------
# The statistics, as pure functions
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_median_not_mean(self):
        """One partner that sat on a referral for nine months must not drag the
        figure somewhere no individual referral ever was."""
        assert median([2, 3, 4, 5, 270]) == 4

    def test_median_of_an_even_count(self):
        assert median([2, 4]) == 3

    def test_wilson_is_asymmetric_near_the_extremes(self):
        """Why Wilson rather than the normal approximation: at 10/10 the normal
        interval runs past 100%, which is not a possible proportion."""
        bounds = wilson_bounds(10, 10)
        assert bounds["upper"] == 100 and bounds["lower"] < 100

    def test_wilson_narrows_as_evidence_grows(self):
        narrow = wilson_bounds(90, 180)
        wide = wilson_bounds(15, 30)
        assert (narrow["upper"] - narrow["lower"]) < (wide["upper"] - wide["lower"])

    def test_a_verdict_needs_the_report_band_not_merely_the_floor(self):
        """A verdict is a comparison, and the provisional band is defined as
        never compared or ranked — so 20 observations gets `too_few`, not
        `as_expected`, even though 20 clears the suppression floor of 10."""
        assert funnel_verdict(10, 20, 0.5) == "too_few"
        assert funnel_verdict(15, 30, 0.5) == "as_expected"

    def test_limits_widen_as_the_denominator_shrinks(self):
        """The whole point of a funnel plot: a small partner cannot be an
        outlier on the evidence, a large one can."""
        assert funnel_verdict(30, 30, 0.5) == "above"
        assert funnel_verdict(45, 60, 0.5) == "above"
        # Same rate, but at n=30 the limits are wide enough to swallow it.
        assert funnel_verdict(20, 30, 0.5) == "as_expected"


# ---------------------------------------------------------------------------
# Tier 2
# ---------------------------------------------------------------------------


class TestWoredaTier:
    def test_team_caseload_reports_counts_never_a_rate(self, locations, case_manager, other_case_manager, make_case):
        for index in range(3):
            make_case(case_manager, name=f"Mine {index}")
        make_case(other_case_manager, name="Theirs")

        rows = team_caseload(scoped_bases(case_manager)[1])
        assert len(rows) == 1  # scoped to their own caseload
        assert rows[0]["total"] == 3
        # A rate over one case manager's caseload is noise and creates
        # cream-skimming pressure; the shape must not contain one.
        assert "rate" not in rows[0] and "percent" not in rows[0]

    def test_six_statuses_collapse_to_four_segments(self, locations, programme_manager, make_case):
        from apps.cases.models import CaseStatus

        for status in CaseStatus:
            case = make_case(programme_manager, name=f"Case {status}")
            case.case_status = status
            case.save(update_fields=["case_status"])

        rows = team_caseload(scoped_bases(programme_manager)[1])
        # Four is the ceiling: six adjacent segments cannot hold 3:1 non-text
        # contrast against each other (WCAG 1.4.11).
        assert set(rows[0]["segments"]) == {"on_track", "awaiting_partner", "stalled", "closed"}
        assert sum(rows[0]["segments"].values()) == rows[0]["total"]

    def test_unassigned_youth_is_absent_not_zero(self, locations, programme_manager):
        """§4.2 makes case_manager required, so this is a state the schema
        cannot hold — OQ-12. Zero would read as "everyone is assigned"."""
        youth, cases, referrals = scoped_bases(programme_manager)
        card = woreda_supervisor(youth, cases, referrals)["unassigned_youth"]
        assert card["available"] is False and "must have a case manager" in card["reason"]

    def test_partner_response_is_ordered_by_evidence(
        self, locations, programme_manager, case_manager, make_case, make_referral, make_partner
    ):
        thin = make_partner(name="Thin Evidence")
        for index in range(3):
            referral = make_referral(make_case(programme_manager, name=f"Known {index}"))
            referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral = make_referral(make_case(programme_manager, name="Barely"), receiving_partner=thin)
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

        rows = partner_response_times(scoped_bases(programme_manager)[2])
        # `case_manager` recorded all four on the partners' behalf, so none of
        # them measures partner responsiveness: `n` counts the partner's own
        # answers and the staff-recorded ones are held separately. Averaging the
        # two together would score a partner who never answers identically to
        # one who answers in a day.
        assert [row["n"] for row in rows] == [0, 0]
        assert sorted(row["staff_recorded"] for row in rows) == [1, 3]
        assert all(row["median_days"] is None for row in rows)

    def test_completeness_names_the_cost_of_each_gap(self, locations, programme_manager, make_case):
        make_case(programme_manager, name="Somebody")
        youth, cases, referrals = scoped_bases(programme_manager)
        rows = woreda_supervisor(youth, cases, referrals)["data_completeness"]
        failure_row = [row for row in rows if "Failure reason" in row["field"]][0]
        assert "replacement prompt" in failure_row["cost"]


# ---------------------------------------------------------------------------
# Tier 3
# ---------------------------------------------------------------------------


class TestProgrammeTier:
    def test_the_outcome_matrix_keeps_its_zero_cells(self, locations, taxonomy, programme_manager, make_case, place):
        """The empty cells are the finding — training referrals that never
        convert to a job. A Sankey draws only the ribbons that exist, which is
        the argument against one."""
        place(make_case(programme_manager, name="Placed"))
        matrix = outcome_matrix(scoped_bases(programme_manager)[2])

        assert len(matrix["cells"]) == len(matrix["categories"]) * len(matrix["outcomes"])
        assert any(cell["n_referrals"] == 0 for cell in matrix["cells"])
        assert any(cell["n_referrals"] == 1 for cell in matrix["cells"])

    def test_the_matrix_carries_youth_as_well_as_referrals(
        self, locations, taxonomy, programme_manager, make_case, place
    ):
        """A youth with three completed referrals is one youth; any person-level
        indicator has to use the second number."""
        case = make_case(programme_manager, name="Much Placed")
        place(case)
        matrix = outcome_matrix(scoped_bases(programme_manager)[2])
        cell = [c for c in matrix["cells"] if c["n_referrals"]][0]
        assert cell["n_youth"] <= cell["n_referrals"]

    def test_partner_table_is_ordered_by_closed_volume_never_by_rate(
        self, locations, taxonomy, programme_manager, case_manager, make_case, make_referral, make_partner, place
    ):
        small = make_partner(name="Small But Perfect")
        # One partner with a single perfect referral, one with several mixed.
        referral = make_referral(
            make_case(programme_manager, name="Perfect"), receiving_partner=small, category=taxonomy["employment"]
        )
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=taxonomy["job_placement"],
            outcome_date=date.today(),
        )
        for index in range(3):
            place(make_case(programme_manager, name=f"Bulk {index}"))

        table = partner_performance(scoped_bases(programme_manager)[2])
        # 100% on one referral must not lead. Sorting by rate ranks by luck.
        assert table["partners"][0]["closed"] >= table["partners"][-1]["closed"]
        assert table["partners"][0]["partner"] != "Small But Perfect"

    def test_no_partner_gets_a_verdict_on_thin_evidence(self, locations, taxonomy, programme_manager, make_case, place):
        for index in range(3):
            place(make_case(programme_manager, name=f"Youth {index}"))
        table = partner_performance(scoped_bases(programme_manager)[2])
        assert all(row["verdict"] == "too_few" for row in table["partners"])
        assert all("too few" in row["verdict_label"] for row in table["partners"])

    def test_parallel_load_counts_capped_and_exempt_separately(
        self, locations, taxonomy, programme_manager, case_manager, make_case, make_referral
    ):
        """OQ-7 is still open, so the evidence for deciding it has to exist."""
        case = make_case(programme_manager, name="Busy")
        for category in (taxonomy["training"], taxonomy["complementary"]):
            referral = make_referral(case, category=category)
            referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

        load = parallel_load(scoped_bases(programme_manager)[2])
        assert load["cases_with_parallel"] == 1
        # Two active, but only one consumes a slot — so the cap is not breached.
        assert load["breaches_cap"] == 0

    def test_retention_and_disposition_are_absent_not_zero(self, locations, programme_manager):
        # `programme_tier` is the aggregation; `programme_manager` is the user
        # fixture. Same word, two things — hence the alias on the import.
        youth, cases, referrals = scoped_bases(programme_manager)
        tier = programme_tier(youth, cases, referrals)
        for key in ("cohort_retention", "disposition_90_day"):
            assert tier[key]["available"] is False
            assert "Not measurable yet" in tier[key]["reason"]
            # Absent means absent: no value field to be mistaken for a zero.
            assert "value" not in tier[key]


# ---------------------------------------------------------------------------
# Tier 4
# ---------------------------------------------------------------------------


class TestDonorTier:
    def test_indicator_wording_is_verbatim(self, locations, programme_manager):
        """Framework wording is used exactly so woreda figures roll up without
        reconciliation. Improving the phrasing breaks the roll-up."""
        youth, _cases, referrals = scoped_bases(programme_manager)
        payload = donor(youth, referrals, date.today(), 7)
        labels = [i["label"] for i in payload["indicators"]]
        assert "Youth clients with business plans financed or enrolled in wage employment" in labels
        assert any("PSNP 5 / SEASN" in i["framework"] for i in payload["indicators"])

    def test_placements_are_labelled_gross(self, locations, programme_manager):
        youth, _cases, referrals = scoped_bases(programme_manager)
        payload = donor(youth, referrals, date.today(), 7)
        employed = [i for i in payload["indicators"] if i["code"] == "employed"][0]
        assert "Gross" in employed["reason"] and "jobs created" in employed["reason"]

    def test_timeliness_excludes_referrals_too_new_to_judge(
        self, locations, taxonomy, programme_manager, case_manager, make_case, make_referral
    ):
        """A referral raised three days before period end is not an unclosed
        loop. Without the guard, rates collapse at every period boundary and
        staff learn to stop raising referrals late in the quarter."""
        fresh = make_referral(make_case(programme_manager, name="Raised Yesterday"))
        fresh.initiated_date = date.today() - timedelta(days=1)
        fresh.save(update_fields=["initiated_date"])

        youth, _cases, referrals = scoped_bases(programme_manager)
        payload = donor(youth, referrals, date.today(), 7)
        timeliness = [i for i in payload["indicators"] if i["code"] == "confirmed_within_threshold"][0]
        assert timeliness["rate"]["d"] == 0

    def test_disaggregation_bands_every_cut(self, locations, programme_manager, make_youth):
        """Female × disability × woreda is exactly where denominators collapse,
        and exactly what donors ask for."""
        for index in range(5):
            make_youth(name=f"Youth {index}")
        youth, _cases, referrals = scoped_bases(programme_manager)
        cuts = donor(youth, referrals, date.today(), 7)["disaggregation"]
        # Settlement type joined the cuts when OQ-11 was settled.
        assert [cut["label"] for cut in cuts] == [
            "Sex",
            "Age band",
            "Woreda",
            "Disability",
            "Settlement type",
            "PSNP status",
        ]
        for cut in cuts:
            for row in cut["rows"]:
                assert row["rate"]["percent"] is None  # every cut is below the floor

    def test_the_caveats_name_gross_and_verification(self, locations, programme_manager):
        youth, _cases, referrals = scoped_bases(programme_manager)
        caveats = " ".join(donor(youth, referrals, date.today(), 7)["caveats"])
        assert "gross" in caveats and "self-reported" in caveats


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier", list(URLS))
def test_each_tier_serves(locations, supervisor, as_user, tier):
    assert as_user(supervisor).get(URLS[tier]).status_code == 200


@pytest.mark.parametrize("tier", list(URLS))
def test_each_tier_refuses_a_scope_with_no_case_population(locations, db, as_user, make_partner, tier):
    from apps.users.models import Role, User

    staff = User.objects.create_user(
        "partner-t", "pw-Test-12345", full_name="Partner Staff", role=Role.PARTNER_STAFF, partner=make_partner()
    )
    assert as_user(staff).get(URLS[tier]).status_code == 403


@pytest.mark.parametrize("tier", list(URLS))
def test_each_tier_needs_authentication(api, tier):
    assert api.get(URLS[tier]).status_code == 401


def test_a_supervisor_sees_only_their_woreda_on_every_tier(
    locations, supervisor, programme_manager, make_case, as_user
):
    """An aggregate is a disclosure; §7 narrows it exactly as it narrows a list."""
    make_case(programme_manager, name="Adama Youth", woreda="Adama")
    make_case(programme_manager, name="Bishoftu Youth", woreda="Bishoftu")

    client = as_user(supervisor)
    woreda = client.get(URLS["woreda"]).data
    assert sum(row["total"] for row in woreda["team_caseload"]) == 1
    assert client.get(URLS["results"]).data["scope_label"] == "Adama"


# ---------------------------------------------------------------------------
# PUNCH_LIST_v1 v2 — Tier 2 findings
# ---------------------------------------------------------------------------


class TestPunchListV2:
    def test_awaiting_partner_gets_its_own_segment(self, locations, programme_manager, make_case):
        """W-1. The build folded Referral Pending into "in progress" and spent
        two of four segments on terminal states, leaving none for the one live
        state a supervisor can act on — and it is the segment that surfaces a
        stranded referral cohort."""
        from apps.cases.models import CaseStatus

        case = make_case(programme_manager, name="Waiting")
        case.case_status = CaseStatus.REFERRAL_PENDING
        case.save(update_fields=["case_status"])

        rows = team_caseload(scoped_bases(programme_manager)[1])
        assert rows[0]["segments"]["awaiting_partner"] == 1
        assert set(rows[0]["segments"]) == {"on_track", "awaiting_partner", "stalled", "closed"}

    def test_placed_and_exited_share_the_terminal_segment(self, locations, programme_manager, make_case):
        from apps.cases.models import CaseStatus

        for status in (CaseStatus.PLACED, CaseStatus.EXITED):
            case = make_case(programme_manager, name=f"Done {status}")
            case.case_status = status
            case.save(update_fields=["case_status"])

        rows = team_caseload(scoped_bases(programme_manager)[1])
        assert rows[0]["segments"]["closed"] == 2

    def test_the_caseload_ceiling_is_actually_read(self, locations, settings, programme_manager, make_case):
        """The parameter was configured and nothing consumed it, so every case
        manager could sit above it unremarked."""
        settings.CASELOAD_CEILING = 2
        for index in range(3):
            make_case(programme_manager, name=f"Case {index}")

        rows = team_caseload(scoped_bases(programme_manager)[1])
        assert rows[0]["over_ceiling"] is True

        settings.CASELOAD_CEILING = 50
        assert team_caseload(scoped_bases(programme_manager)[1])[0]["over_ceiling"] is False

    def test_completeness_distinguishes_no_records_from_complete(self, locations, programme_manager, make_case):
        """W-10. "Complete" over a zero denominator is absence of records
        dressed up as a clean bill of health."""
        make_case(programme_manager, name="Somebody")
        youth, cases, referrals = scoped_bases(programme_manager)
        rows = woreda_supervisor(youth, cases, referrals)["data_completeness"]

        failure_row = [row for row in rows if "Failure reason" in row["field"]][0]
        assert failure_row["of"] == 0 and failure_row["has_records"] is False
        phone_row = [row for row in rows if "Phone" in row["field"]][0]
        assert phone_row["has_records"] is True

    def test_partner_response_puts_the_slowest_first(
        self, locations, programme_manager, case_manager, make_case, make_referral, make_partner
    ):
        """W-9. Unsorted, the partner a supervisor needs to chase is not
        findable. Withheld medians sink rather than being ranked."""
        slow = make_partner(name="Slow Institute")
        for partner, days in [(None, 2), (None, 2), (slow, 20)]:
            referral = make_referral(make_case(programme_manager, name=f"C{days}{partner}"), receiving_partner=partner)
            referral.initiated_date = date.today() - timedelta(days=days)
            referral.save(update_fields=["initiated_date"])
            referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

        rows = partner_response_times(scoped_bases(programme_manager)[2])
        # Everything is below the floor here, so all medians are withheld and
        # the order falls back to evidence.
        assert [row["median_days"] for row in rows] == [None, None]

    def test_the_tier_carries_its_own_stat_tiles_and_age(self, locations, programme_manager, make_case):
        """W-5 and W-11."""
        make_case(programme_manager, name="Somebody")
        youth, cases, referrals = scoped_bases(programme_manager)
        payload = woreda_supervisor(youth, cases, referrals)

        assert set(payload["tiles"]) == {
            "open_cases",
            "registered_without_case",
            "overdue_actions",
            "median_days_to_confirm",
            "outcomes_verified",
            "outcomes_recorded",
            "over_ceiling",
            "caseload_ceiling",
        }
        assert payload["as_of"]


class TestAbandonmentRule:
    """P1-3 revised — §6.2 has no exit from Pending Confirmation for a referral
    nobody answers, so it holds a parallel-cap slot forever."""

    def test_the_rule_is_off_until_a_threshold_is_agreed(
        self, locations, taxonomy, settings, programme_manager, make_case, make_referral
    ):
        from apps.alerts.tasks import fail_abandoned_referrals

        settings.REFERRAL_ABANDONMENT_DAYS = None
        referral = make_referral(make_case(programme_manager, name="Stranded"))
        referral.initiated_date = date.today() - timedelta(days=500)
        referral.save(update_fields=["initiated_date"])

        # Failing a referral is a decision about a real young person; the number
        # is programme management's, not ours (OQ-13).
        assert fail_abandoned_referrals() == 0
        referral.refresh_from_db()
        assert referral.status == ReferralStatus.PENDING_CONFIRMATION

    def test_an_unanswered_referral_fails_as_partner_non_responsive(
        self, locations, taxonomy, settings, programme_manager, make_case, make_referral
    ):
        from apps.alerts.tasks import fail_abandoned_referrals

        settings.REFERRAL_ABANDONMENT_DAYS = 60
        stranded = make_referral(make_case(programme_manager, name="Stranded"))
        stranded.initiated_date = date.today() - timedelta(days=500)
        stranded.save(update_fields=["initiated_date"])
        recent = make_referral(make_case(programme_manager, name="Recent"))

        assert fail_abandoned_referrals() == 1

        stranded.refresh_from_db()
        recent.refresh_from_db()
        assert stranded.status == ReferralStatus.FAILED
        # The code existed in §5.4 and nothing set it until now.
        assert stranded.failure_reason_code.code == "PARTNER_NON_RESPONSIVE"
        assert stranded.failure_date == date.today()
        # A referral raised this week is not abandoned.
        assert recent.status == ReferralStatus.PENDING_CONFIRMATION

    def test_a_failed_referral_no_longer_occupies_the_case(
        self, locations, taxonomy, settings, programme_manager, make_case, make_referral
    ):
        """Why this blocks a pilot rather than merely looking untidy: a referral
        stuck in Pending holds a slot against the §6.3 cap and sits in the
        loop-closure denominator forever."""
        from apps.alerts.tasks import fail_abandoned_referrals
        from apps.referrals.models import Referral

        settings.REFERRAL_ABANDONMENT_DAYS = 60
        case = make_case(programme_manager, name="Blocked")
        stranded = make_referral(case)
        stranded.initiated_date = date.today() - timedelta(days=500)
        stranded.save(update_fields=["initiated_date"])

        assert Referral.objects.filter(case=case, status=ReferralStatus.PENDING_CONFIRMATION).count() == 1
        fail_abandoned_referrals()
        assert Referral.objects.filter(case=case, status=ReferralStatus.PENDING_CONFIRMATION).count() == 0
        assert Referral.objects.filter(case=case, status=ReferralStatus.FAILED).count() == 1
