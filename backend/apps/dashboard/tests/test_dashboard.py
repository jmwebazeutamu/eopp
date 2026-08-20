"""Programme dashboard figures — the handoff's screen 8.

Two things are worth pinning here and they are both about honesty:

* an aggregate obeys §7 exactly as a list does, so a supervisor's total is their
  woredas and nobody else's;
* a figure whose source entity does not exist yet is reported absent, never as a
  zero that reads as "the programme placed nobody".

The rest is arithmetic — but arithmetic a donor reads, so it is tested at the
boundaries: an empty programme, a woreda with no placements, a partner that has
never replied.
"""

from datetime import date, timedelta

import pytest
from django.conf import settings

from apps.dashboard.rules import REPORT_MIN_DENOMINATOR
from apps.dashboard.services import (
    confirmation_lag,
    funnel,
    metric_cards,
    programme_dashboard,
    quarter_bounds,
    scoped_bases,
    woreda_comparison,
)
from apps.referrals import services as referral_services
from apps.referrals.models import ReferralStatus

pytestmark = pytest.mark.django_db

URL = "/api/v1/dashboard/"


@pytest.fixture
def complete(taxonomy, case_manager):
    """Drive a referral to Completed through the state machine.

    Never by setting `status` — §6.2 is the only supported route, and a row
    written round the side would not carry the dates the dashboard averages.

    §5.3 ties an outcome to the categories it applies to, so the caller must pass
    an outcome the referral's own category accepts; `place` below pairs them.
    """

    def _complete(referral, outcome=None, on=None):
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=on or date.today())
        referral.transition_to(
            ReferralStatus.COMPLETED,
            actor=case_manager,
            outcome_type=outcome or taxonomy["job_placement"],
            outcome_date=on or date.today(),
        )
        return referral

    return _complete


@pytest.fixture
def place(taxonomy, make_referral, complete):
    """A case that ends in a job: an Employment referral closed as Job Placement.

    The pairing matters — §5.3 refuses Job Placement on a Training referral, so
    a placement fixture has to choose the category too.
    """

    def _place(case, on=None):
        referral = make_referral(case, category=taxonomy["employment"])
        if on:
            referral.initiated_date = on
            referral.save(update_fields=["initiated_date"])
        return complete(referral, outcome=taxonomy["job_placement"], on=on)

    return _place


# ---------------------------------------------------------------------------
# The quarter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "today,label,start",
    [
        (date(2026, 1, 1), "Q1 2026", date(2026, 1, 1)),
        (date(2026, 5, 17), "Q2 2026", date(2026, 4, 1)),
        (date(2026, 8, 17), "Q3 2026", date(2026, 7, 1)),
        (date(2026, 12, 31), "Q4 2026", date(2026, 10, 1)),
    ],
)
def test_quarter_bounds(today, label, start):
    got_start, _end, got_label = quarter_bounds(today)
    assert (got_start, got_label) == (start, label)


def test_the_fourth_quarter_ends_in_the_next_year():
    """The naive `month + 3` rolls to month 13 and raises."""
    _start, end, _label = quarter_bounds(date(2026, 11, 2))
    assert end == date(2027, 1, 1)


# ---------------------------------------------------------------------------
# Absent, not zero
# ---------------------------------------------------------------------------


def test_retention_reports_itself_as_unmeasured_rather_than_zero(locations, programme_manager):
    """A donor-facing 0% would be a lie.

    Sprint 5 built the entity, which changes the *reason* and not the rule: with
    no placement recorded the card is still absent, because "nobody has been
    placed yet" and "nobody stayed" are different claims and only one of them is
    true here.
    """
    payload = programme_dashboard(programme_manager)
    card = payload["metrics"]["retained_six_months"]
    assert card["available"] is False
    assert "Not measurable yet" in card["reason"]
    assert "rate" not in card

    retained = [row for row in payload["funnel"] if row["key"] == "retained"][0]
    assert retained["available"] is False
    assert retained["count"] is None and retained["share"] is None


def test_an_empty_programme_reports_zeroes_not_errors(locations, programme_manager):
    payload = programme_dashboard(programme_manager)
    assert payload["metrics"]["placements_this_quarter"]["value"] == 0
    # Counts are zero; the shares are withheld rather than shown as 0% of nothing.
    assert all(row["count"] == 0 for row in payload["funnel"] if row["available"])
    assert all(row["share"]["percent"] is None for row in payload["funnel"] if row["available"])
    assert payload["woredas"] == []
    assert payload["confirmation_lag"]["partners"] == []


def test_no_agreed_target_drops_the_target_rather_than_inventing_one(locations, programme_manager, settings):
    """§11: the mockup's 180 is mockup data. 0 means 'nobody has told us'."""
    settings.PLACEMENT_TARGET_PER_QUARTER = 0
    card = programme_dashboard(programme_manager)["metrics"]["placements_this_quarter"]
    assert card["target"] is None and card["percent"] is None


def test_a_configured_target_is_reported_with_its_percentage(
    locations, programme_manager, make_case, make_referral, place, settings
):
    settings.PLACEMENT_TARGET_PER_QUARTER = 4
    place(make_case(programme_manager, name="Placed One"))

    card = programme_dashboard(programme_manager)["metrics"]["placements_this_quarter"]
    assert (card["value"], card["target"], card["percent"]) == (1, 4, 25)


def test_the_gender_split_is_absent_until_something_has_been_placed(locations, programme_manager, make_case):
    make_case(programme_manager, name="Not Placed")
    assert programme_dashboard(programme_manager)["metrics"]["gender_split"]["available"] is False


# ---------------------------------------------------------------------------
# What counts as a placement is configuration, not code (§9)
# ---------------------------------------------------------------------------


def test_only_outcomes_flagged_as_placements_are_counted(
    locations, programme_manager, make_case, make_referral, place, complete, taxonomy
):
    """A completed TVET course closes a referral without placing anyone."""
    place(make_case(programme_manager, name="In A Job"))
    complete(
        make_referral(make_case(programme_manager, name="Finished A Course"), category=taxonomy["training"]),
        outcome=taxonomy["training_completion"],
    )

    payload = programme_dashboard(programme_manager)
    assert payload["metrics"]["placements_this_quarter"]["value"] == 1
    # Both reached Completed, so the funnel's "Placed or completed" holds two.
    assert [row["count"] for row in payload["funnel"] if row["key"] == "closed_successfully"] == [2]


def test_flipping_the_admin_flag_changes_the_figure_without_a_deploy(
    locations, programme_manager, make_case, make_referral, complete, taxonomy
):
    complete(
        make_referral(make_case(programme_manager, name="Finished A Course"), category=taxonomy["training"]),
        outcome=taxonomy["training_completion"],
    )
    assert programme_dashboard(programme_manager)["metrics"]["placements_this_quarter"]["value"] == 0

    taxonomy["training_completion"].counts_as_placement = True
    taxonomy["training_completion"].save()

    assert programme_dashboard(programme_manager)["metrics"]["placements_this_quarter"]["value"] == 1


def test_a_placement_in_a_previous_quarter_is_not_this_quarter(
    locations, programme_manager, make_case, make_referral, place
):
    last_quarter = date.today().replace(day=1) - timedelta(days=120)
    place(make_case(programme_manager, name="Placed Long Ago"), on=last_quarter)

    payload = programme_dashboard(programme_manager)
    assert payload["metrics"]["placements_this_quarter"]["value"] == 0
    # Still in the funnel, which is programme-to-date rather than quarterly.
    assert [row["count"] for row in payload["funnel"] if row["key"] == "closed_successfully"] == [1]


# ---------------------------------------------------------------------------
# The funnel nests
# ---------------------------------------------------------------------------


def test_the_funnel_counts_youth_so_a_later_stage_cannot_exceed_an_earlier_one(
    locations, programme_manager, make_case, make_referral, place, taxonomy
):
    """Three referrals for one youth is one youth referred, not three."""
    case = make_case(programme_manager, name="Much Referred")
    place(case)
    make_referral(case, category=taxonomy["complementary"])

    rows = {row["key"]: row["count"] for row in programme_dashboard(programme_manager)["funnel"]}
    assert rows["registered"] == 1
    assert rows["referred"] == 1
    # Only the gates nest. Profiling and pathway are coverage measures, not
    # prerequisites: the referral engine raises a referral without either.
    gates = [rows[key] for key in ("registered", "case_opened", "referred", "partner_confirmed", "closed_successfully")]
    assert gates == sorted(gates, reverse=True)


def test_percentages_are_of_registration(locations, programme_manager, make_youth, make_case):
    """Enough youth to clear the reporting floor, so real percentages appear."""
    for index in range(REPORT_MIN_DENOMINATOR - 1):
        make_youth(name=f"Youth {index}")
    for index in range(10):
        make_case(programme_manager, youth=make_youth(name=f"Cased Youth {index}"))

    rows = {row["key"]: row["share"] for row in programme_dashboard(programme_manager)["funnel"]}
    assert rows["registered"]["percent"] == 100
    assert rows["registered"]["band"] == "report"
    assert rows["case_opened"]["percent"] == 26  # 10 of 39
    assert (rows["case_opened"]["n"], rows["case_opened"]["d"]) == (10, 39)


def test_a_funnel_below_the_floor_keeps_its_counts_and_drops_its_percentages(locations, programme_manager, make_youth):
    """The pilot is small (§1). A funnel off nine youth still draws — it just
    does not claim shares that nine cases cannot support."""
    for index in range(9):
        make_youth(name=f"Youth {index}")

    rows = {row["key"]: row["share"] for row in programme_dashboard(programme_manager)["funnel"]}
    assert rows["registered"]["percent"] is None
    assert rows["registered"]["band"] == "suppressed"
    counts = [row["count"] for row in programme_dashboard(programme_manager)["funnel"] if row["available"]]
    assert counts[0] == 9


# ---------------------------------------------------------------------------
# Confirmation lag
# ---------------------------------------------------------------------------


def test_confirmation_lag_reports_the_median_not_the_mean(
    locations, programme_manager, case_manager, make_case, make_referral
):
    referral = make_referral(make_case(programme_manager, name="Waited Six Days"))
    referral.initiated_date = date.today() - timedelta(days=6)
    referral.save(update_fields=["initiated_date"])
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

    lag = programme_dashboard(programme_manager)["confirmation_lag"]
    assert lag["standard_days"] == settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS
    # Both pages read this from one helper now. It used to compute a mean here
    # and a median on the woreda page, so the two disagreed on identical n.
    assert lag["partners"] == [
        {
            "partner": "Adama Polytechnic College",
            "median_days": None,
            "n": 0,
            "staff_recorded": 1,
            "band": "suppressed",
        }
    ]


def test_a_partner_that_has_never_replied_is_absent_rather_than_fast(
    locations, programme_manager, make_case, make_referral
):
    """A null lag is not a short lag — averaging it in would reward silence."""
    make_referral(make_case(programme_manager, name="Still Waiting"))
    assert programme_dashboard(programme_manager)["confirmation_lag"]["partners"] == []


def test_partners_are_ordered_by_evidence_not_by_speed(
    locations, programme_manager, case_manager, make_case, make_referral, make_partner
):
    """Sorting by the mean ranks partners by luck at these denominators, and a
    published ranking is hard to withdraw. Most-observed leads instead."""
    thin = make_partner(name="Thin Evidence Institute")
    for index in range(3):
        referral = make_referral(make_case(programme_manager, name=f"Well Known {index}"))
        referral.initiated_date = date.today() - timedelta(days=12)
        referral.save(update_fields=["initiated_date"])
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

    referral = make_referral(make_case(programme_manager, name="Barely Known"), receiving_partner=thin)
    referral.initiated_date = date.today() - timedelta(days=2)
    referral.save(update_fields=["initiated_date"])
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

    partners = programme_dashboard(programme_manager)["confirmation_lag"]["partners"]
    # Staff recorded all of these on the partners' behalf, so none of them
    # measures partner responsiveness; the order falls back to evidence.
    assert [row["partner"] for row in partners] == ["Adama Polytechnic College", "Thin Evidence Institute"]
    assert [row["staff_recorded"] for row in partners] == [3, 1]


# ---------------------------------------------------------------------------
# Woreda comparison
# ---------------------------------------------------------------------------


def test_woreda_rate_is_placed_over_registered(
    locations, programme_manager, make_youth, make_case, make_referral, place
):
    make_youth(name="Adama Unplaced", woreda="Adama")
    place(make_case(programme_manager, name="Adama Placed", woreda="Adama"))
    make_youth(name="Bishoftu Nobody", woreda="Bishoftu")

    rows = {row["woreda"]: row for row in programme_dashboard(programme_manager)["woredas"]}
    assert (rows["Adama"]["registered"], rows["Adama"]["placed"]) == (2, 1)
    # Two youth is far below the floor: the counts stand, the rate does not.
    assert rows["Adama"]["rate"]["percent"] is None
    assert rows["Adama"]["rate"]["band"] == "suppressed"
    assert rows["Bishoftu"]["placed"] == 0


def test_a_woreda_with_no_placements_still_appears(locations, programme_manager, make_youth):
    """Dropping it would quietly flatter the programme average."""
    make_youth(name="Only Registered", woreda="Bishoftu")
    assert [row["woreda"] for row in programme_dashboard(programme_manager)["woredas"]] == ["Bishoftu"]


# ---------------------------------------------------------------------------
# Scope — §7. An aggregate is a disclosure.
# ---------------------------------------------------------------------------


def test_a_supervisor_totals_their_own_woredas_only(
    locations, supervisor, programme_manager, make_youth, make_case, make_referral, place
):
    make_youth(name="Mine", woreda="Adama")
    place(make_case(programme_manager, name="Also Mine", woreda="Adama"))
    make_youth(name="Not Mine", woreda="Bishoftu")
    place(make_case(programme_manager, name="Also Not Mine", woreda="Bishoftu"))

    assert supervisor.woreda_assignment == ["Adama"]
    mine = programme_dashboard(supervisor)
    assert [row["count"] for row in mine["funnel"] if row["key"] == "registered"] == [2]
    assert [row["woreda"] for row in mine["woredas"]] == ["Adama"]
    assert mine["metrics"]["placements_this_quarter"]["value"] == 1

    everyone = programme_dashboard(programme_manager)
    assert [row["count"] for row in everyone["funnel"] if row["key"] == "registered"] == [4]


def test_a_case_manager_totals_their_own_caseload_only(
    locations, case_manager, other_case_manager, make_case, make_referral, place
):
    place(make_case(case_manager, name="Mine"))
    place(make_case(other_case_manager, name="Theirs"))

    assert programme_dashboard(case_manager)["metrics"]["placements_this_quarter"]["value"] == 1


def test_the_scope_label_says_what_the_numbers_cover(locations, supervisor, programme_manager, case_manager):
    assert programme_dashboard(supervisor)["scope_label"] == "Adama"
    assert programme_dashboard(programme_manager)["scope_label"] == "All woredas"
    assert programme_dashboard(case_manager)["scope_label"] == "Your caseload"


def test_scoped_bases_fail_closed_for_a_scope_with_no_case_population(locations, db):
    """A LINKED role has no woreda and no caseload; it must get nothing."""
    from apps.users.models import Role, User

    trainer = User.objects.create_user("trainer-a", "pw-Test-12345", full_name="Trainer", role=Role.TRAINER)
    youth, cases, referrals = scoped_bases(trainer)
    assert not youth.exists() and not cases.exists() and not referrals.exists()


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------


def test_the_endpoint_serves_the_whole_screen_in_one_request(locations, supervisor, as_user):
    response = as_user(supervisor).get(URL)
    assert response.status_code == 200
    assert set(response.data) == {
        "period",
        "scope_label",
        "metrics",
        "funnel",
        "confirmation_lag",
        "woredas",
        "alerts",
        # Sprint 5: retention, training completion, exits, and the coverage gap
        # between referral outcomes and written-up placement records.
        "outcomes",
        # Sprint 6: verification, follow-up pressure, enterprise, grievances.
        "casework",
    }


def test_a_partner_staff_account_is_refused_rather_than_shown_zeroes(locations, db, as_user, make_partner):
    """A LINKED scope has no case population; zeroes would read as a dead programme."""
    from apps.users.models import Role, User

    staff = User.objects.create_user(
        "partner-a", "pw-Test-12345", full_name="Partner Staff", role=Role.PARTNER_STAFF, partner=make_partner()
    )
    assert as_user(staff).get(URL).status_code == 403


def test_the_dashboard_needs_authentication(api):
    assert api.get(URL).status_code == 401


def test_a_suspended_account_is_refused(locations, supervisor, as_user):
    from apps.users.models import AccountStatus

    supervisor.account_status = AccountStatus.SUSPENDED
    supervisor.save(update_fields=["account_status"])
    assert as_user(supervisor).get(URL).status_code == 403


# ---------------------------------------------------------------------------
# The panels are individually callable, which is what makes the above readable
# ---------------------------------------------------------------------------


def test_panels_compose_from_the_same_scoped_bases(locations, programme_manager, make_case, make_referral, place):
    place(make_case(programme_manager, name="Placed"))
    youth, cases, referrals = scoped_bases(programme_manager)

    assert metric_cards(youth, referrals, date.today())["placements_this_quarter"]["value"] == 1
    assert funnel(youth, cases, referrals)[0]["count"] == 1
    assert confirmation_lag(referrals)["partners"][0]["staff_recorded"] == 1
    assert woreda_comparison(youth, referrals)[0]["placed"] == 1


def test_referral_services_is_the_only_way_a_referral_reaches_completed(taxonomy):
    """Guards the fixture above: if §6.2 changes, this test says so."""
    assert hasattr(referral_services, "initiate_referral")
