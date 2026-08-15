"""Case entity tests — spec §4.2, with the §7 scoping boundaries enforced for real."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.cases.models import Case, CaseStatus

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Model rules
# ---------------------------------------------------------------------------


def test_case_manager_must_hold_the_case_manager_role(make_youth, supervisor):
    """§7 gives only the Youth case manager role a caseload."""
    case = Case(youth=make_youth(), case_manager=supervisor, woreda="Adama")
    with pytest.raises(ValidationError) as exc:
        case.clean()
    assert "case_manager" in exc.value.message_dict


def test_woreda_is_denormalised_from_the_youth_record(make_youth, case_manager):
    """§4.2: woreda is copied from Youth for caseload filtering."""
    youth = make_youth(woreda="Bishoftu")
    case = Case.objects.create(youth=youth, case_manager=case_manager, woreda="WRONG")
    assert case.woreda == "Bishoftu"


def test_woreda_resyncs_when_the_youth_moves(make_case, make_youth, case_manager):
    case = make_case(case_manager)
    case.youth.woreda = "Bishoftu"
    case.youth.save()
    case.save()
    assert case.woreda == "Bishoftu"


def test_exited_case_requires_closed_date_and_reason(make_case, case_manager):
    case = make_case(case_manager)
    case.case_status = CaseStatus.EXITED
    with pytest.raises(ValidationError) as exc:
        case.clean()
    assert "closed_date" in exc.value.message_dict
    assert "exit_reason" in exc.value.message_dict


def test_only_an_exited_case_may_carry_a_closed_date(make_case, case_manager):
    case = make_case(case_manager)
    case.closed_date = date.today()
    with pytest.raises(ValidationError) as exc:
        case.clean()
    assert "closed_date" in exc.value.message_dict


def test_case_cannot_close_before_it_opened(make_case, case_manager):
    case = make_case(case_manager, opened_date=date.today())
    case.case_status = CaseStatus.EXITED
    case.closed_date = date.today() - timedelta(days=5)
    case.exit_reason = "Relocated"
    with pytest.raises(ValidationError) as exc:
        case.clean()
    assert "closed_date" in exc.value.message_dict


# ---------------------------------------------------------------------------
# last_activity_date and the stall threshold — spec §6, §8
# ---------------------------------------------------------------------------


def test_touch_moves_last_activity_date(make_case, case_manager):
    case = make_case(case_manager, last_activity_date=date.today() - timedelta(days=40))
    case.touch()
    case.refresh_from_db()
    assert case.last_activity_date == date.today()


def test_stalled_query_respects_the_configured_threshold(make_case, case_manager, settings):
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    fresh = make_case(case_manager, name="Fresh", last_activity_date=date.today() - timedelta(days=5))
    stale = make_case(case_manager, name="Stale", last_activity_date=date.today() - timedelta(days=45))

    stalled = set(Case.objects.stalled_beyond_threshold().values_list("pk", flat=True))
    assert stale.pk in stalled
    assert fresh.pk not in stalled


def test_closed_cases_never_count_as_stalled(make_case, case_manager, settings):
    """An exited case stops accruing inactivity — it is finished, not neglected."""
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    case = make_case(
        case_manager,
        name="Exited",
        last_activity_date=date.today() - timedelta(days=200),
        case_status=CaseStatus.EXITED,
        closed_date=date.today() - timedelta(days=200),
        exit_reason="Placed and retained",
    )
    assert case.pk not in set(Case.objects.stalled_beyond_threshold().values_list("pk", flat=True))


# ---------------------------------------------------------------------------
# API scoping — spec §7, enforced against real rows
# ---------------------------------------------------------------------------


def test_case_manager_sees_only_their_own_caseload(make_case, case_manager, other_case_manager, as_user):
    mine = make_case(case_manager, name="Mine")
    make_case(other_case_manager, name="Theirs")

    response = as_user(case_manager).get("/api/v1/cases/")
    assert response.status_code == 200
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [str(mine.pk)]


def test_supervisor_sees_the_whole_woreda_but_not_beyond(make_case, case_manager, supervisor, as_user):
    in_woreda = make_case(case_manager, name="In Adama", woreda="Adama")
    make_case(case_manager, name="In Bishoftu", woreda="Bishoftu")

    response = as_user(supervisor).get("/api/v1/cases/")
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [str(in_woreda.pk)]


def test_programme_manager_sees_every_woreda(make_case, case_manager, programme_manager, as_user):
    make_case(case_manager, name="In Adama", woreda="Adama")
    make_case(case_manager, name="In Bishoftu", woreda="Bishoftu")

    response = as_user(programme_manager).get("/api/v1/cases/")
    assert response.data["count"] == 2


def test_system_admin_sees_no_case_content(make_case, case_manager, system_admin, as_user):
    """§7: 'Configuration only, no case content by default'."""
    make_case(case_manager)
    assert as_user(system_admin).get("/api/v1/cases/").status_code == 403


def test_supervisor_cannot_write(make_case, case_manager, supervisor, as_user):
    case = make_case(case_manager)
    response = as_user(supervisor).patch(f"/api/v1/cases/{case.pk}/", {"next_action": "Follow up"}, format="json")
    assert response.status_code == 403


def test_case_manager_cannot_reach_another_managers_case_by_id(make_case, case_manager, other_case_manager, as_user):
    """Scoping must apply to detail routes, not only the list."""
    theirs = make_case(other_case_manager, name="Theirs")
    assert as_user(case_manager).get(f"/api/v1/cases/{theirs.pk}/").status_code == 404


def test_assigning_to_a_non_case_manager_is_rejected(make_case, case_manager, supervisor, as_user):
    case = make_case(case_manager)
    response = as_user(case_manager).post(
        f"/api/v1/cases/{case.pk}/assign/", {"case_manager": str(supervisor.pk)}, format="json"
    )
    assert response.status_code == 400
    assert "case_manager" in response.data


def test_assignment_moves_the_case_and_records_activity(make_case, case_manager, other_case_manager, as_user):
    case = make_case(case_manager, last_activity_date=date.today() - timedelta(days=10))
    response = as_user(case_manager).post(
        f"/api/v1/cases/{case.pk}/assign/",
        {"case_manager": str(other_case_manager.pk), "reason": "Caseload rebalancing"},
        format="json",
    )
    assert response.status_code == 200, response.data
    case.refresh_from_db()
    assert case.case_manager == other_case_manager
    assert case.last_activity_date == date.today()


def test_cases_cannot_be_deleted(make_case, case_manager, as_user):
    case = make_case(case_manager)
    assert as_user(case_manager).delete(f"/api/v1/cases/{case.pk}/").status_code == 405


def test_my_caseload_excludes_closed_cases(make_case, case_manager, as_user):
    open_case = make_case(case_manager, name="Open")
    make_case(
        case_manager,
        name="Closed",
        case_status=CaseStatus.EXITED,
        closed_date=date.today(),
        exit_reason="Placed",
    )
    response = as_user(case_manager).get("/api/v1/cases/my-caseload/")
    ids = [row["id"] for row in response.data["results"]]
    assert ids == [str(open_case.pk)]


def test_caseload_summary_flags_managers_over_the_ceiling(
    make_case, case_manager, programme_manager, as_user, settings
):
    settings.CASELOAD_CEILING = 1
    make_case(case_manager, name="One")
    make_case(case_manager, name="Two")

    response = as_user(programme_manager).get("/api/v1/cases/caseload-summary/")
    assert response.status_code == 200
    row = next(r for r in response.data["case_managers"] if r["full_name"] == "Manager A")
    assert row["open_cases"] == 2
    assert row["over_ceiling"] is True


@pytest.mark.parametrize("days_idle", [0, 29, 30, 31, 60])
def test_stall_property_and_queryset_agree_at_every_boundary(make_case, case_manager, settings, days_idle):
    """The computed property and the queryset that feeds the alert job must
    never disagree. They were off by one at exactly `threshold_days`, which made
    a case read as stalled on screen while the detection job skipped it.
    """
    settings.STALL_ALERT_THRESHOLD_DAYS = 30
    case = make_case(case_manager, last_activity_date=date.today() - timedelta(days=days_idle))

    in_queryset = Case.objects.stalled_beyond_threshold().filter(pk=case.pk).exists()
    assert case.is_stalled_by_threshold == in_queryset
