"""The deadline, and the case file.

What is worth asserting is not that the arithmetic runs but that it is
defensible to the person it is said about: a complaint taken on Friday and
answered on Monday took one working day, a deadline never lands on Meskel, and
a resolved case stops counting.
"""

from datetime import date, timedelta

import pytest

from apps.grievances import clock, services, timeline
from apps.grievances.models import ComplaintType, RaisedBy, Severity

pytestmark = pytest.mark.django_db


def _conclude(grievance, actor):
    """Walk a complaint all the way to Closed.

    Four steps rather than one, which is the workflow's whole point: the
    complainant is told it arrived, somebody works it, a decision is recorded,
    and only then — having been told the answer — is the file shut.
    """
    from apps.grievances.models import GrievanceStatus, Outcome

    if grievance.status == GrievanceStatus.RECEIVED:
        services.acknowledge(grievance, method="By phone", actor=actor)
    services.start_review(grievance, actor=actor)
    services.decide(grievance, outcome=Outcome.UPHELD, reason="The stipend was reissued.", actor=actor)
    return services.record_feedback_and_close(grievance, method="In person", actor=actor)


# ---------------------------------------------------------------------------
# Working days
# ---------------------------------------------------------------------------


def test_sunday_is_not_a_working_day():
    assert clock.is_working_day(date(2026, 8, 23)) is False  # Sunday
    assert clock.is_working_day(date(2026, 8, 22)) is True  # Saturday, worked here


def test_a_public_holiday_is_not_a_working_day():
    """A deadline that lands on Meskel and is marked breached destroys trust in
    the metric faster than having no metric."""
    assert clock.is_working_day(date(2026, 9, 27)) is False  # Meskel
    assert clock.is_working_day(date(2026, 9, 28)) is True


def test_a_deadline_skips_the_rest_day():
    # Friday 21 Aug 2026 + 1 working day is Saturday, + 2 is Monday.
    assert clock.add_working_days(date(2026, 8, 21), 1) == date(2026, 8, 22)
    assert clock.add_working_days(date(2026, 8, 21), 2) == date(2026, 8, 24)


def test_a_deadline_never_lands_on_a_holiday():
    for days in range(1, 40):
        assert clock.is_working_day(clock.add_working_days(date(2026, 9, 1), days))


def test_the_gap_is_signed_so_one_figure_carries_both_sentences():
    """ "Due in 2 days" and "3 days late" are the same number with a sign, which
    is what stops the screen branching."""
    # Mon 31 Aug to Wed 2 Sep 2026, a window with no holiday in it.
    assert clock.working_days_between(date(2026, 8, 31), date(2026, 9, 2)) == 2
    assert clock.working_days_between(date(2026, 9, 2), date(2026, 8, 31)) == -2
    assert clock.working_days_between(date(2026, 8, 31), date(2026, 8, 31)) == 0


def test_a_holiday_inside_the_window_does_not_count_against_anybody():
    """This test was written across 25 August, which is Mawlid, and failed —
    which is the holiday table doing its job. The same two calendar days are
    two working days in an ordinary week and one across a holiday."""
    assert clock.working_days_between(date(2026, 8, 24), date(2026, 8, 26)) == 1


def test_severity_overrides_the_default_deadline(settings):
    settings.GRIEVANCE_CRITICAL_RESPONSE_DAYS = 3
    settings.GRIEVANCE_RESPONSE_DAYS = 21
    assert clock.response_days(severity=Severity.CRITICAL) == 3
    assert clock.response_days(severity=Severity.ROUTINE) == 21


# ---------------------------------------------------------------------------
# The record
# ---------------------------------------------------------------------------


def test_a_complaint_gets_a_deadline_when_it_is_raised(raise_grievance):
    grievance = raise_grievance()
    assert grievance.due_on == clock.due_on(raised_on=grievance.date_raised, severity=Severity.ROUTINE)


def test_raising_the_severity_moves_the_deadline(raise_grievance):
    """A critical case sitting against a routine clock is the case that matters."""
    grievance = raise_grievance()
    routine = grievance.due_on

    grievance.severity = Severity.CRITICAL
    grievance.save()

    assert grievance.due_on < routine


def test_the_clock_stops_when_the_file_is_concluded(raise_grievance, supervisor):
    """The Age column kept counting after resolution, so a closed case read
    "30 day(s) open"."""
    grievance = raise_grievance(date_raised=date.today() - timedelta(days=40))
    _conclude(grievance, supervisor)

    standing = clock.standing(grievance)
    assert standing["state"] == "closed"
    # Working days between raising and resolving, not days since it was raised.
    assert standing["days"] < 40


def test_an_open_case_past_its_deadline_reads_late(raise_grievance):
    grievance = raise_grievance(date_raised=date.today() - timedelta(days=120))
    standing = clock.standing(grievance)
    assert standing["state"] == "late"
    assert standing["days"] < 0


def test_the_queue_counts_what_needs_somebody_today(raise_grievance):
    from apps.grievances.models import Grievance

    raise_grievance(date_raised=date.today() - timedelta(days=120))
    raise_grievance()

    counts = services.queue_counts(Grievance.objects.all())
    assert counts["late"] == 1
    assert counts["awaiting_acknowledgement"] == 2


# ---------------------------------------------------------------------------
# Acknowledgement
# ---------------------------------------------------------------------------


def test_acknowledging_needs_a_method(raise_grievance, supervisor):
    """ "Acknowledged" with no record of how is a tick somebody applies from a
    desk. The field exists to describe something that happened in the world."""
    grievance = raise_grievance()
    with pytest.raises(services.GrievanceError):
        services.acknowledge(grievance, method="  ", actor=supervisor)


def test_acknowledging_twice_is_refused(raise_grievance, supervisor):
    grievance = raise_grievance()
    services.acknowledge(grievance, method="By phone", actor=supervisor)
    with pytest.raises(services.GrievanceError):
        services.acknowledge(grievance, method="In person", actor=supervisor)


def test_an_acknowledged_complaint_leaves_that_queue(raise_grievance, supervisor):
    from apps.grievances.models import Grievance

    grievance = raise_grievance()
    assert Grievance.objects.awaiting_acknowledgement().count() == 1

    services.acknowledge(grievance, method="By phone", actor=supervisor)
    assert Grievance.objects.awaiting_acknowledgement().count() == 0


# ---------------------------------------------------------------------------
# The case file
# ---------------------------------------------------------------------------


def test_the_statement_is_always_first(raise_grievance, supervisor):
    grievance = raise_grievance()
    services.add_note(grievance, body="Payment roll checked.", author=supervisor)

    events = timeline.build(grievance)
    assert events[0]["type"] == timeline.STATEMENT
    assert events[0]["body"] == grievance.summary


def test_the_file_carries_every_kind_of_event(raise_grievance, supervisor):
    grievance = raise_grievance()
    services.acknowledge(grievance, method="By phone", actor=supervisor)
    services.add_note(grievance, body="Payment roll checked.", author=supervisor)
    _conclude(grievance, supervisor)

    kinds = {event["type"] for event in timeline.build(grievance)}
    assert timeline.STATEMENT in kinds
    assert timeline.ACKNOWLEDGEMENT in kinds
    assert timeline.NOTE in kinds
    assert timeline.OUTCOME in kinds


def test_a_note_is_never_edited(raise_grievance, supervisor, as_user):
    """Append-only over the API. A note that can be edited afterwards is not
    evidence of anything."""
    grievance = raise_grievance()
    note = services.add_note(grievance, body="First reading.", author=supervisor)

    client = as_user(supervisor)
    assert client.patch(f"/api/v1/grievances/{grievance.pk}/notes/", {"body": "x"}, format="json").status_code == 405
    assert client.delete(f"/api/v1/grievances/{grievance.pk}/notes/").status_code == 405
    note.refresh_from_db()
    assert note.body == "First reading."


def test_the_timeline_route_refuses_a_disclosure_and_logs_the_attempt(as_user, system_admin, supervisor, db):
    from apps.grievances.models import GrievanceAccess

    disclosure = services.raise_grievance(
        complaint_type=ComplaintType.SAFEGUARDING,
        raised_by=RaisedBy.YOUTH,
        summary="A matter I will only discuss with the focal point.",
        assigned_staff=supervisor,
        woreda="Adama",
    )
    response = as_user(system_admin).get(f"/api/v1/grievances/{disclosure.pk}/timeline/")

    assert response.status_code == 403
    assert GrievanceAccess.objects.get(grievance=disclosure).granted is False
