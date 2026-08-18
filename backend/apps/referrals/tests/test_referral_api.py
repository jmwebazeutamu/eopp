"""Referral API tests — endpoints, scoping (§7), and the taxonomy lookups (§5)."""

from datetime import date, timedelta

import pytest

from apps.referrals.models import Referral, ReferralStatus
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(make_case, case_manager):
    return make_case(case_manager)


@pytest.fixture
def partner_staff(partner):
    return User.objects.create_user(
        "partner-staff", "pw-Test-12345", full_name="Partner Staff", role=Role.PARTNER_STAFF, partner=partner
    )


# ---------------------------------------------------------------------------
# Taxonomy endpoints — spec §5
# ---------------------------------------------------------------------------


def test_categories_are_served_from_the_lookup_table(taxonomy, case_manager, as_user):
    response = as_user(case_manager).get("/api/v1/referrals/categories/")
    assert response.status_code == 200
    codes = {row["code"] for row in response.data}
    assert {"TRAINING", "EMPLOYMENT", "COMPLEMENTARY_SERVICE", "OTHER"} <= codes


def test_complementary_service_is_flagged_exempt(taxonomy, case_manager, as_user):
    """§6.3 working default, exposed so the UI can explain the cap."""
    response = as_user(case_manager).get("/api/v1/referrals/categories/")
    row = next(r for r in response.data if r["code"] == "COMPLEMENTARY_SERVICE")
    assert row["exempt_from_parallel_cap"] is True


def test_retired_terms_disappear_from_the_lookup(taxonomy, case_manager, as_user):
    """Deactivated terms stay on historical referrals but leave the picker."""
    taxonomy["training"].is_active = False
    taxonomy["training"].save()

    response = as_user(case_manager).get("/api/v1/referrals/categories/")
    assert "TRAINING" not in {row["code"] for row in response.data}


def test_outcome_types_can_be_filtered_by_category(taxonomy, case_manager, as_user):
    """§5.3: each outcome applies to specific categories; Other applies to all."""
    response = as_user(case_manager).get("/api/v1/referrals/outcome-types/?category=EMPLOYMENT")
    codes = {row["code"] for row in response.data}
    assert "JOB_PLACEMENT" in codes
    assert "OTHER" in codes  # unrestricted
    # Finishing a course is not an outcome of an employment referral.
    assert "TRAINING_COMPLETION" not in codes

    # Widened by G-1: a training referral can end in a job, and the picker has
    # to offer it or the crossover can never be recorded.
    training = as_user(case_manager).get("/api/v1/referrals/outcome-types/?category=TRAINING")
    assert "JOB_PLACEMENT" in {row["code"] for row in training.data}


# ---------------------------------------------------------------------------
# Initiate and transition endpoints — spec §6.2
# ---------------------------------------------------------------------------


def test_initiate_creates_a_pending_referral(case, taxonomy, partner, case_manager, as_user):
    response = as_user(case_manager).post(
        "/api/v1/referrals/initiate/",
        {"case": str(case.pk), "referral_category": "TRAINING", "receiving_partner": str(partner.pk)},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["status"] == ReferralStatus.PENDING_CONFIRMATION
    assert response.data["trigger_display"] == "Manual"


def test_cannot_initiate_on_another_managers_case(
    make_case, other_case_manager, taxonomy, partner, case_manager, as_user
):
    """Passing a case id must not bypass §7 caseload scoping."""
    theirs = make_case(other_case_manager, name="Theirs")
    response = as_user(case_manager).post(
        "/api/v1/referrals/initiate/",
        {"case": str(theirs.pk), "referral_category": "TRAINING", "receiving_partner": str(partner.pk)},
        format="json",
    )
    assert response.status_code == 404


def test_direct_post_is_refused_in_favour_of_initiate(case, case_manager, as_user, taxonomy):
    response = as_user(case_manager).post("/api/v1/referrals/", {}, format="json")
    assert response.status_code == 405


def test_status_cannot_be_changed_by_patch(case, make_referral, case_manager, as_user):
    """§6.2 is the only route between statuses."""
    referral = make_referral(case)
    response = as_user(case_manager).patch(f"/api/v1/referrals/{referral.pk}/", {"status": "ACTIVE"}, format="json")
    referral.refresh_from_db()
    assert referral.status == ReferralStatus.PENDING_CONFIRMATION
    assert response.status_code in (200, 400)  # field is read-only, so silently ignored or rejected


def test_confirm_then_complete_through_the_api(case, make_referral, taxonomy, case_manager, as_user):
    referral = make_referral(case)
    client = as_user(case_manager)

    confirmed = client.post(
        f"/api/v1/referrals/{referral.pk}/confirm/", {"confirmed_by": "Tigist Bekele"}, format="json"
    )
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["status"] == ReferralStatus.ACTIVE

    completed = client.post(
        f"/api/v1/referrals/{referral.pk}/complete/",
        {"outcome_type": "TRAINING_COMPLETION", "outcome_verification_method": "Home visit"},
        format="json",
    )
    assert completed.status_code == 200, completed.data
    assert completed.data["status"] == ReferralStatus.COMPLETED


def test_decline_requires_a_failure_reason_via_api(case, make_referral, case_manager, as_user, taxonomy):
    referral = make_referral(case)
    response = as_user(case_manager).post(f"/api/v1/referrals/{referral.pk}/decline/", {}, format="json")
    assert response.status_code == 400
    assert "failure_reason_code" in response.data


def test_completing_a_pending_referral_is_refused(case, make_referral, case_manager, as_user, taxonomy):
    """Active -> Completed exists in §6.2; Pending -> Completed does not."""
    referral = make_referral(case)
    response = as_user(case_manager).post(
        f"/api/v1/referrals/{referral.pk}/complete/", {"outcome_type": "TRAINING_COMPLETION"}, format="json"
    )
    assert response.status_code == 400


def test_transitions_endpoint_lists_only_legal_moves(case, make_referral, case_manager, as_user):
    referral = make_referral(case)
    response = as_user(case_manager).get(f"/api/v1/referrals/{referral.pk}/transitions/")
    assert {row["to_status"] for row in response.data} == {"ACTIVE", "FAILED", "CANCELLED"}


def test_parallel_cap_is_reported_as_a_field_error(case, make_referral, taxonomy, case_manager, as_user):
    client = as_user(case_manager)
    for category in (taxonomy["training"], taxonomy["employment"]):
        ref = make_referral(case, category=category)
        client.post(f"/api/v1/referrals/{ref.pk}/confirm/", {"confirmed_by": "X"}, format="json")

    third = make_referral(case, category=taxonomy["enterprise"])
    response = client.post(f"/api/v1/referrals/{third.pk}/confirm/", {"confirmed_by": "X"}, format="json")
    assert response.status_code == 400
    assert "status" in response.data


# ---------------------------------------------------------------------------
# Prompts and stack — spec §6.2, §6.4
# ---------------------------------------------------------------------------


def test_prompts_endpoint_surfaces_onward_and_replacement(case, make_referral, taxonomy, case_manager, as_user):
    client = as_user(case_manager)

    completed = make_referral(case, category=taxonomy["training"])
    completed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    completed.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    failed = make_referral(case, category=taxonomy["employment"])
    failed.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["capacity"])

    response = client.get("/api/v1/referrals/prompts/")
    assert [r["id"] for r in response.data["onward"]] == [str(completed.pk)]
    assert [r["id"] for r in response.data["replacement"]] == [str(failed.pk)]


def test_stack_endpoint_returns_the_nested_chain(case, make_referral, taxonomy, partner, case_manager, as_user):
    from apps.referrals import services

    first = make_referral(case, category=taxonomy["training"])
    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    first.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])
    services.create_onward_referral(
        parent=first,
        referral_category=taxonomy["employment"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )

    response = as_user(case_manager).get(f"/api/v1/referrals/stack/{case.pk}/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert len(response.data[0]["children"]) == 1


# ---------------------------------------------------------------------------
# Scoping — spec §7
# ---------------------------------------------------------------------------


def test_partner_staff_see_only_their_own_institutions_referrals(
    case, make_referral, make_partner, partner, partner_staff, as_user, taxonomy
):
    """§7: "View/update, own institution's referrals only"."""
    other_partner = make_partner(name="Bishoftu Automotive")
    mine = make_referral(case, category=taxonomy["training"], receiving_partner=partner)
    make_referral(case, category=taxonomy["employment"], receiving_partner=other_partner)

    response = as_user(partner_staff).get("/api/v1/referrals/")
    assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]


def test_partner_staff_may_confirm_their_own_referral(case, make_referral, partner_staff, as_user, taxonomy):
    """§7 gives partner staff "Referral receipt confirmation"."""
    referral = make_referral(case)
    response = as_user(partner_staff).post(
        f"/api/v1/referrals/{referral.pk}/confirm/", {"confirmed_by": "Tigist"}, format="json"
    )
    assert response.status_code == 200, response.data


def test_partner_staff_cannot_reach_another_institutions_referral(
    case, make_referral, make_partner, partner_staff, as_user, taxonomy
):
    other_partner = make_partner(name="Somewhere Else")
    theirs = make_referral(case, receiving_partner=other_partner)
    assert as_user(partner_staff).get(f"/api/v1/referrals/{theirs.pk}/").status_code == 404


def test_supervisor_sees_woreda_referrals_but_cannot_act(case, make_referral, supervisor, as_user, taxonomy):
    referral = make_referral(case)
    client = as_user(supervisor)
    assert client.get("/api/v1/referrals/").data["count"] == 1
    response = client.post(f"/api/v1/referrals/{referral.pk}/confirm/", {"confirmed_by": "X"}, format="json")
    assert response.status_code == 403


def test_system_admin_sees_and_may_act_on_every_referral(case, make_referral, system_admin, as_user, taxonomy):
    """Deviation from §7, decided 2026-08-16 — see the ACCESS_MATRIX comment.

    §7 gives this role no case content. The programme asked for full access, so
    the administrator now sees every referral and can drive the §6.2 machine.
    """
    referral = make_referral(case)
    client = as_user(system_admin)

    listing = client.get("/api/v1/referrals/")
    assert listing.status_code == 200
    assert listing.data["count"] == 1

    confirmed = client.post(
        f"/api/v1/referrals/{referral.pk}/confirm/", {"confirmed_by": "Tigist Bekele"}, format="json"
    )
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["status"] == ReferralStatus.ACTIVE


def test_case_manager_cannot_see_another_caseloads_referrals(
    make_case, make_referral, case_manager, other_case_manager, as_user, taxonomy
):
    theirs = make_case(other_case_manager, name="Theirs")
    make_referral(theirs, initiated_by=other_case_manager)
    assert as_user(case_manager).get("/api/v1/referrals/").data["count"] == 0


def test_list_carries_the_woreda_for_the_cross_case_queue(case, make_referral, case_manager, as_user, taxonomy):
    """The referral queue lists referrals without their case in hand.

    It needs the woreda for the location column and to narrow the partner picker
    when a referral is followed on, so the serializer carries the value Case
    already denormalises (§4.2) rather than making the client fetch each case.
    """
    make_referral(case)
    response = as_user(case_manager).get("/api/v1/referrals/")
    assert response.data["results"][0]["woreda"] == case.woreda


def test_partner_staff_get_a_woreda_without_case_access(case, make_referral, partner, partner_staff, as_user, taxonomy):
    """The queue is the only referral surface partner staff can reach.

    §7 scopes their case access to LINKED, which resolves to nothing, so the
    case screen is unavailable to them — everything the queue shows has to come
    off the referral serializer itself.
    """
    make_referral(case, receiving_partner=partner)
    response = as_user(partner_staff).get("/api/v1/referrals/")
    assert response.data["results"][0]["woreda"] == case.woreda
    assert as_user(partner_staff).get(f"/api/v1/cases/{case.pk}/").status_code == 404


def test_referrals_cannot_be_deleted(case, make_referral, case_manager, as_user, taxonomy):
    referral = make_referral(case)
    assert as_user(case_manager).delete(f"/api/v1/referrals/{referral.pk}/").status_code == 405


def test_referral_count_matches_the_case(case, make_referral, taxonomy, case_manager, as_user):
    make_referral(case, category=taxonomy["training"])
    make_referral(case, category=taxonomy["employment"])
    response = as_user(case_manager).get(f"/api/v1/referrals/?case={case.pk}")
    assert response.data["count"] == 2
    assert Referral.objects.filter(case=case).count() == 2


# ---------------------------------------------------------------------------
# Programme rules (§6.3)
# ---------------------------------------------------------------------------


def test_rules_endpoint_serves_the_parallel_cap(case_manager, as_user, settings):
    """The case screen states the cap out loud, so it must not guess at it.

    §6.3's limit is a programme decision. A client that hardcoded 2 would keep
    claiming it after the setting changed, and the screen's "2 of 2 in use" chip
    and blocked button would both be lying.
    """
    settings.MAX_PARALLEL_ACTIVE_REFERRALS = 3
    response = as_user(case_manager).get("/api/v1/referrals/rules/")
    assert response.status_code == 200
    assert response.data["parallel_limit"] == 3


def test_rules_endpoint_serves_the_thresholds_the_ui_shows(case_manager, as_user):
    response = as_user(case_manager).get("/api/v1/referrals/rules/")
    assert set(response.data) == {
        "parallel_limit",
        "stall_alert_threshold_days",
        "referral_confirmation_overdue_days",
        "complementary_service_exempt",
    }


def test_rules_endpoint_needs_authentication(api):
    assert api.get("/api/v1/referrals/rules/").status_code == 401


# ---------------------------------------------------------------------------
# Queue conditions — what the referrals screen groups and paginates by
# ---------------------------------------------------------------------------


def _age(referral, days):
    """Backdate a referral without going through the state machine."""
    Referral.objects.filter(pk=referral.pk).update(initiated_date=date.today() - timedelta(days=days))


def test_confirmation_overdue_uses_the_same_boundary_as_the_alert_job(case, make_referral, settings):
    """Strictly beyond the threshold, matching alerts.tasks and rules.

    Those two disagreed on this boundary once, and one referral read as overdue
    on one screen and on time on another. A referral waiting exactly the
    threshold has not breached it.
    """
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    on_the_day = make_referral(case)
    _age(on_the_day, 14)
    beyond = make_referral(case)
    _age(beyond, 15)

    overdue = set(Referral.objects.confirmation_overdue().values_list("pk", flat=True))
    assert beyond.pk in overdue
    assert on_the_day.pk not in overdue


def test_the_pending_split_is_exhaustive(case, make_referral, settings):
    """Overdue plus on-time accounts for every pending referral, once.

    The queue draws these as two groups; a referral in neither, or in both,
    would be invisible or double-counted.
    """
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    _age(make_referral(case), 30)
    _age(make_referral(case), 2)

    pending = Referral.objects.filter(status=ReferralStatus.PENDING_CONFIRMATION)
    overdue = set(Referral.objects.confirmation_overdue().values_list("pk", flat=True))
    on_time = set(Referral.objects.awaiting_confirmation_on_time().values_list("pk", flat=True))

    assert overdue | on_time == set(pending.values_list("pk", flat=True))
    assert overdue & on_time == set()


def test_needs_decision_is_the_union_of_the_three_conditions(case, make_referral, case_manager, taxonomy, settings):
    """§6.2's three prompts, as one queryset.

    The referrals screen used to assemble this in the browser from the pending
    list plus the prompts endpoint, which put the definition in the client and
    made the screen impossible to paginate.
    """
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    stale = make_referral(case)
    _age(stale, 40)

    completed = make_referral(case)
    completed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    completed.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["job_placement"])

    failed = make_referral(case)
    failed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    failed.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])

    fresh = make_referral(case)

    needs = set(Referral.objects.needs_decision().values_list("pk", flat=True))
    assert {stale.pk, completed.pk, failed.pk} <= needs
    # Still inside the window and nobody is waiting on the case manager.
    assert fresh.pk not in needs


def test_needs_decision_counts_each_referral_once(case, make_referral, settings):
    """The union is distinct. Without it a row could satisfy two conditions and
    be paginated as two, so a page of 25 would show fewer than 25 rows."""
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    _age(make_referral(case), 40)
    ids = list(Referral.objects.needs_decision().values_list("pk", flat=True))
    assert len(ids) == len(set(ids))


def test_queue_filters_are_reachable_over_the_api(case, make_referral, as_user, case_manager, settings):
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    _age(make_referral(case), 40)
    make_referral(case)

    client = as_user(case_manager)
    assert client.get("/api/v1/referrals/", {"needs_decision": "true"}).data["count"] == 1
    assert (
        client.get(
            "/api/v1/referrals/", {"status": ReferralStatus.PENDING_CONFIRMATION, "confirmation_overdue": "false"}
        ).data["count"]
        == 1
    )


def test_the_queue_paginates_rather_than_capping(case, make_referral, as_user, case_manager, settings):
    """The screen asked for the first 100 of each queue and said nothing about
    the rest; with 266 active referrals most of the queue was invisible."""
    settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS = 14
    for _ in range(30):
        _age(make_referral(case), 40)

    body = as_user(case_manager).get("/api/v1/referrals/", {"needs_decision": "true", "page_size": 25}).data
    assert body["count"] == 30
    assert len(body["results"]) == 25
    assert body["next"] is not None
