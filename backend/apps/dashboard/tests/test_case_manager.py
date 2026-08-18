"""Tier 1 — the case manager dashboard.

`dashboard_handoff_youth_employment/django/CASE_MANAGER_DASHBOARD.md`, §4 tests
and §8 acceptance criteria. The RBAC block is the one the contract calls "the
tests that matter most in the whole handoff", and the shared-youth case is the
reason `scoped_referrals` exists at all.
"""

import ast
import pathlib
import re
from datetime import date, timedelta

import pytest
from django.conf import settings
from django.urls import reverse

from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.cases.models import CaseStatus
from apps.dashboard import queues
from apps.dashboard.scoping import scoped_cases, scoped_referrals
from apps.referrals.models import ReferralStatus

pytestmark = pytest.mark.django_db

DASHBOARD = "/dashboard/"


@pytest.fixture
def alert_for():
    def _make(case, assigned_to, alert_type=AlertType.STALL, days_ago=40, threshold=30):
        return Alert.objects.create(
            case=case,
            alert_type=alert_type,
            triggered_date=date.today() - timedelta(days=days_ago),
            threshold_days=threshold,
            assigned_to=assigned_to,
            status=AlertStatus.OPEN,
        )

    return _make


# ---------------------------------------------------------------------------
# §4 — the security boundary
# ---------------------------------------------------------------------------


def test_case_manager_sees_only_own_caseload(locations, case_manager, other_case_manager, make_case, alert_for):
    mine = make_case(case_manager, name="Mine")
    theirs = make_case(other_case_manager, name="Theirs")
    alert_for(mine, case_manager)
    alert_for(theirs, other_case_manager)

    assert list(scoped_cases(case_manager)) == [mine]
    assert [row.case_id for row in queues.needs_action(case_manager)] == [mine.pk]
    assert theirs not in scoped_cases(case_manager)


def test_partner_staff_sees_only_own_institution_referrals(
    locations, taxonomy, db, make_case, make_referral, make_partner, case_manager
):
    """The test `scoped_referrals()` exists for.

    One youth, two partners. Case-level scoping alone would hand Partner A the
    referral sent to Partner B, because the youth is in scope for both.
    """
    from apps.users.models import Role, User

    partner_a, partner_b = make_partner(name="Partner A"), make_partner(name="Partner B")
    staff_a = User.objects.create_user(
        "staff-a", "pw-Test-12345", full_name="Staff A", role=Role.PARTNER_STAFF, partner=partner_a
    )

    shared = make_case(case_manager, name="Shared Youth")
    to_a = make_referral(shared, receiving_partner=partner_a)
    to_b = make_referral(shared, receiving_partner=partner_b)

    visible = set(scoped_referrals(staff_a).values_list("pk", flat=True))
    assert to_a.pk in visible
    assert to_b.pk not in visible


def test_supervisor_scoped_to_woreda(locations, supervisor, case_manager, make_case):
    adama = make_case(case_manager, name="Adama Youth", woreda="Adama")
    bishoftu = make_case(case_manager, name="Bishoftu Youth", woreda="Bishoftu")

    visible = set(scoped_cases(supervisor).values_list("pk", flat=True))
    assert adama.pk in visible and bishoftu.pk not in visible


def test_linked_only_roles_are_not_given_a_woreda(locations, db, make_case, case_manager):
    """A trainer must not fall through to their woreda's whole caseload."""
    from apps.users.models import Role, User

    trainer = User.objects.create_user(
        "trainer-b", "pw-Test-12345", full_name="Trainer", role=Role.TRAINER, woreda_assignment=["Adama"]
    )
    make_case(case_manager, name="Not Theirs", woreda="Adama")
    assert not scoped_cases(trainer).exists()


def test_unknown_role_is_denied_not_allowed(locations, db, make_case, case_manager):
    """A role with no matrix entry must deny, never default to everything."""
    from apps.users.models import User

    make_case(case_manager, name="Somebody")
    stranger = User.objects.create_user("stranger", "pw-Test-12345", full_name="Stranger", role="NOT_A_ROLE")
    assert not scoped_cases(stranger).exists()


def test_the_system_administrator_follows_the_matrix_not_the_handoff(locations, system_admin, make_case, case_manager):
    """The contract restates §7's "no case content"; ACCESS_MATRIX was widened
    on 2026-08-16 at the programme's request. Scoping follows the matrix, so the
    widening cannot be reverted by a handoff nobody signed off."""
    make_case(case_manager, name="Somebody")
    assert scoped_cases(system_admin).exists()


def test_no_queue_bypasses_scoping():
    """AST walk over queues.py — §4 and §8.

    A grep cannot do this: the reference implementations legitimately name
    `Alert.objects` *with* scoping applied in the same statement, so a substring
    ban would reject correct code.
    """
    source = pathlib.Path(queues.__file__).read_text()
    tree = ast.parse(source)

    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Return, ast.Assign, ast.Expr)):
            continue
        statement = ast.dump(node)
        uses_manager = ".objects" in ast.unparse(node)
        if not uses_manager:
            continue
        if "scoped_cases" not in statement and "scoped_referrals" not in statement:
            offenders.append(ast.unparse(node)[:90])

    assert offenders == [], f"queryset built without scoping: {offenders}"


# ---------------------------------------------------------------------------
# §5 — the six cards
# ---------------------------------------------------------------------------


def test_needs_action_sorts_by_days_overdue_and_uses_each_alerts_own_threshold(
    locations, case_manager, make_case, alert_for
):
    """An alert raised under a 30-day rule stays judged at 30 (§4.13)."""
    slightly = make_case(case_manager, name="Slightly Late")
    very = make_case(case_manager, name="Very Late")
    alert_for(slightly, case_manager, days_ago=32, threshold=30)  # 2 days over
    alert_for(very, case_manager, days_ago=60, threshold=30)  # 30 days over

    rows = list(queues.needs_action(case_manager))
    assert [row.days_overdue for row in rows] == [30, 2]


def test_an_alert_inside_its_threshold_is_not_yet_action(locations, case_manager, make_case, alert_for):
    case = make_case(case_manager, name="Not Yet")
    alert_for(case, case_manager, days_ago=5, threshold=30)
    assert not queues.needs_action(case_manager).exists()


def test_an_alert_assigned_to_someone_else_is_not_mine(
    locations, case_manager, other_case_manager, make_case, alert_for
):
    case = make_case(case_manager, name="Mine")
    alert_for(case, other_case_manager)
    assert not queues.needs_action(case_manager).exists()


def test_awaiting_partner_sorts_by_age_and_counts_no_referrals_sent(
    locations, taxonomy, case_manager, make_case, make_referral
):
    old = make_referral(make_case(case_manager, name="Waited Long"))
    old.initiated_date = date.today() - timedelta(days=19)
    old.save(update_fields=["initiated_date"])
    make_referral(make_case(case_manager, name="Waited Little"))

    rows = list(queues.awaiting_partner(case_manager))
    assert [row.days_waiting for row in rows] == [19, 0]


def test_a_confirmed_referral_is_no_longer_awaiting(locations, taxonomy, case_manager, make_case, make_referral):
    referral = make_referral(make_case(case_manager, name="Confirmed"))
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
    assert not queues.awaiting_partner(case_manager).exists()


def test_caseload_by_status_is_workflow_ordered_and_keeps_empty_rows(locations, case_manager, make_case):
    make_case(case_manager, name="Active One")
    rows = queues.caseload_by_status(case_manager)

    assert [row["status"] for row in rows] == [
        CaseStatus.ACTIVE,
        CaseStatus.REFERRAL_PENDING,
        CaseStatus.STALLED,
        CaseStatus.PLACED,
        CaseStatus.EXITED,
    ]
    # A status nobody is in still gets a row: the order must not shift over time.
    assert [row["n"] for row in rows] == [1, 0, 0, 0, 0]


def test_at_risk_lists_the_quiet_cases_worst_first(locations, settings, case_manager, make_case):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    quiet = make_case(case_manager, name="Very Quiet")
    quiet.last_activity_date = date.today() - timedelta(days=45)
    quiet.save(update_fields=["last_activity_date"])
    less = make_case(case_manager, name="Less Quiet")
    less.last_activity_date = date.today() - timedelta(days=31)
    less.save(update_fields=["last_activity_date"])
    make_case(case_manager, name="Busy")

    items = queues.to_risk_items(queues.at_risk(case_manager))
    assert [item.youth_name for item in items] == ["Very Quiet", "Less Quiet"]
    assert items[0].badge == "45d"


def test_at_risk_deduplicates_keeping_the_highest_severity():
    """The contract's rule, tested on the mapper rather than through the ORM —
    with one condition implemented there is nothing yet that can collide."""
    from uuid import uuid4

    case_id = uuid4()

    class Row:
        def __init__(self, days):
            self.pk = case_id
            self.quiet_days = days
            self.youth = type("Y", (), {"full_name": "Twice Listed"})()

    items = queues.to_risk_items([Row(20), Row(60)])
    assert len(items) == 1 and items[0].severity == 60


def test_week_counts_is_one_aggregate(locations, case_manager, make_case, django_assert_num_queries):
    make_case(case_manager, name="Opened This Week")
    with django_assert_num_queries(1):
        counts = queues.week_counts(case_manager)
    assert counts["opened"] == 1


def test_outcomes_verified_counts_only_verified_completions(
    locations, taxonomy, case_manager, make_case, make_referral
):
    referral = make_referral(make_case(case_manager, name="Verified"), category=taxonomy["employment"])
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())
    referral.transition_to(
        ReferralStatus.COMPLETED,
        actor=case_manager,
        outcome_type=taxonomy["job_placement"],
        outcome_date=date.today(),
    )
    assert queues.outcomes_verified(case_manager) == 1

    # Strip the verifier and it drops out: §8.3 makes the verified subset the
    # reportable one, and a self-reported outcome is an aspiration.
    referral.outcome_verified_by = None
    referral.save(update_fields=["outcome_verified_by"])
    assert queues.outcomes_verified(case_manager) == 0


# ---------------------------------------------------------------------------
# §8 — acceptance criteria
# ---------------------------------------------------------------------------


def test_the_dashboard_renders_for_a_case_manager(locations, case_manager, make_case, as_user, client, alert_for):
    case = make_case(case_manager, name="Abebe Bekele")
    alert_for(case, case_manager)

    client.force_login(case_manager)
    response = client.get(DASHBOARD)
    assert response.status_code == 200
    assert b"Abebe Bekele" in response.content


def test_no_percentage_appears_on_the_rendered_page(locations, case_manager, make_case, client, alert_for):
    """§8 guard rail. A rate is not an action, and a caseload is far below the
    n = 30 stability floor once disaggregated."""
    alert_for(make_case(case_manager, name="Abebe Bekele"), case_manager)
    client.force_login(case_manager)
    body = response_body_without_styles(client.get(DASHBOARD).content.decode())
    assert "%" not in body


def response_body_without_styles(html):
    """The rendered text, with CSS removed — widths are legitimately percentages."""
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S)
    return re.sub(r'style="[^"]*"', "", html)


def test_the_dashboard_stays_inside_its_query_budget(
    locations, case_manager, make_case, alert_for, client, django_assert_max_num_queries
):
    for index in range(20):
        alert_for(make_case(case_manager, name=f"Youth {index}"), case_manager)

    client.force_login(case_manager)
    # §8: 12 total. The budget is what forces the counts to be separate cheap
    # queries rather than len() over a fetched list.
    with django_assert_max_num_queries(12):
        assert client.get(DASHBOARD).status_code == 200


def test_the_page_does_not_grow_with_the_caseload(locations, case_manager, make_case, alert_for, client):
    """§8: under 100 KB at 200 cases. Each card shows six rows and links onward."""
    for index in range(60):
        alert_for(make_case(case_manager, name=f"Youth {index}"), case_manager)

    client.force_login(case_manager)
    assert len(client.get(DASHBOARD).content) < 100_000


def test_a_role_with_no_caseload_is_refused_rather_than_shown_empty_cards(locations, db, make_partner, client):
    from apps.users.models import Role, User

    staff = User.objects.create_user(
        "partner-c", "pw-Test-12345", full_name="Partner Staff", role=Role.PARTNER_STAFF, partner=make_partner()
    )
    client.force_login(staff)
    assert client.get(DASHBOARD).status_code == 403


def test_the_dashboard_needs_a_login(client):
    response = client.get(DASHBOARD)
    assert response.status_code in (302, 403)


def test_every_card_links_to_a_list_of_named_youth(locations, case_manager, make_case, alert_for, client):
    """§2: a number that cannot be clicked to produce a list should be deleted."""
    alert_for(make_case(case_manager, name="Abebe Bekele"), case_manager)
    client.force_login(case_manager)

    for slug in ["needs-action", "at-risk", "active"]:
        response = client.get(reverse("dashboard:queue", kwargs={"queue_slug": slug}))
        assert response.status_code == 200, slug


def test_a_queue_drilldown_is_scoped_too(locations, case_manager, other_case_manager, make_case, client):
    """The drill-down is a second door onto the same rows; it gets the same lock."""
    make_case(other_case_manager, name="Not Yours")
    client.force_login(case_manager)
    response = client.get(reverse("dashboard:queue", kwargs={"queue_slug": "active"}))
    assert b"Not Yours" not in response.content


# ---------------------------------------------------------------------------
# PUNCH_LIST_v1 — the P2 items on the "My work" tab
# ---------------------------------------------------------------------------


def test_the_awaiting_tile_counts_what_is_past_the_threshold(
    locations, taxonomy, settings, case_manager, make_case, make_referral
):
    """P2-1. The tile printed "No referral is waiting on a partner" above a
    count of 117 — the empty-state string was being used as the subtitle. The
    number it should carry is computed from the configured threshold, so moving
    the setting moves the number."""
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 7
    for days in (1, 3, 9, 40):
        referral = make_referral(make_case(case_manager, name=f"Waited {days}"))
        referral.initiated_date = date.today() - timedelta(days=days)
        referral.save(update_fields=["initiated_date"])

    assert queues.awaiting_partner(case_manager).count() == 4
    assert queues.awaiting_over_threshold(case_manager) == 2  # 9 and 40 days

    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 30
    assert queues.awaiting_over_threshold(case_manager) == 1


def test_active_referrals_reports_referrals_and_the_youth_they_cover(
    locations, taxonomy, case_manager, make_case, make_referral
):
    """P2-2. The fifth tile was missing. Two numbers, because "79 referrals
    across 62 youth" says something one count does not."""
    case = make_case(case_manager, name="Two Referrals")
    for category in (taxonomy["training"], taxonomy["complementary"]):
        referral = make_referral(case, category=category)
        referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_date=date.today())

    assert queues.active_referrals(case_manager) == {"referrals": 2, "youth": 1}


def test_the_my_work_payload_carries_what_the_header_needs(locations, case_manager, make_case, as_user):
    """P2-7 and P2-8: a freshness stamp, and the woreda context that was
    rendering as an em dash."""
    make_case(case_manager, name="Somebody")
    payload = as_user(case_manager).get("/api/v1/dashboard/my-work/").data

    assert payload["woredas"] == case_manager.woreda_assignment
    assert payload["generated_at"]
    # P2-3 / P2-4: the badge and the footnote read the configured threshold
    # rather than a literal 7.
    assert payload["confirmation_threshold"] == settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS


def test_every_list_is_sliced_so_the_page_does_not_grow_with_the_caseload(
    locations, case_manager, make_case, alert_for, as_user
):
    """P2-6. The counts are separate from the rows: the screen shows six and
    links to the rest, rather than fetching 117 rows to display 6."""
    for index in range(20):
        alert_for(make_case(case_manager, name=f"Youth {index}"), case_manager)

    payload = as_user(case_manager).get("/api/v1/dashboard/my-work/").data
    assert len(payload["needs_action"]) == 6
    assert payload["needs_action_count"] == 20
