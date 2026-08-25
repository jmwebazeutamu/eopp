"""The workflow — eight states, two tiers, and the gates between them.

Every edge is asserted, and so is every edge that must *not* exist. The point of
a state machine in application code is that an unlisted move fails loudly rather
than silently putting a case in a state nothing knows how to handle, and that
property is only real if something tries.

Three gates carry most of the weight and each has its own test: a file cannot be
shut until the complainant has been told the answer, a decision cannot be
recorded without saying why, and a pause cannot exist without a reason and a
date to come back.
"""

from datetime import date, timedelta

import pytest

from apps.grievances import services
from apps.grievances.models import GrievanceStatus, Outcome, Tier, TransitionError

pytestmark = pytest.mark.django_db


@pytest.fixture
def acknowledged(raise_grievance, supervisor):
    grievance = raise_grievance()
    services.acknowledge(grievance, method="By phone", actor=supervisor)
    return grievance


@pytest.fixture
def under_review(acknowledged, supervisor):
    return services.start_review(acknowledged, actor=supervisor)


@pytest.fixture
def decided(under_review, supervisor):
    return services.decide(
        under_review, outcome=Outcome.NOT_UPHELD, reason="The August payroll shows the stipend paid.", actor=supervisor
    )


# ---------------------------------------------------------------------------
# The edges
# ---------------------------------------------------------------------------


def test_a_new_complaint_is_received(raise_grievance):
    assert raise_grievance().status == GrievanceStatus.RECEIVED


def test_it_cannot_be_worked_before_the_complainant_is_told_it_arrived(raise_grievance, supervisor):
    """The acknowledgement is a promise, and a promise made after the fact is
    not one. This ordering is refused on purpose."""
    with pytest.raises(TransitionError):
        services.start_review(raise_grievance(), actor=supervisor)


def test_acknowledging_moves_it_on(acknowledged):
    assert acknowledged.status == GrievanceStatus.ACKNOWLEDGED


def test_a_decision_needs_a_reason(under_review, supervisor):
    """Written as if the complainant will hear it read back, because they will."""
    with pytest.raises(TransitionError):
        services.decide(under_review, outcome=Outcome.UPHELD, reason="   ", actor=supervisor)


def test_a_decision_is_not_a_closed_file(decided):
    """`DECIDED` exists as its own state because a decision the complainant has
    not heard is not a conclusion. The old ladder had no way to say it."""
    assert decided.status == GrievanceStatus.DECIDED
    assert decided.is_open is True


def test_a_file_cannot_be_shut_until_the_complainant_is_told(decided, supervisor):
    """The gate the whole rebuild turns on. It was possible to close a case
    having told nobody anything."""
    with pytest.raises(TransitionError):
        services.record_feedback_and_close(decided, method="", actor=supervisor)


def test_closing_records_how_they_were_told(decided, supervisor):
    closed = services.record_feedback_and_close(decided, method="In person", satisfied=False, actor=supervisor)

    assert closed.status == GrievanceStatus.CLOSED
    assert closed.feedback_given_at is not None
    assert closed.complainant_satisfied is False


def test_told_and_did_not_say_is_not_satisfied(decided, supervisor):
    """A real and common answer. Recording it as dissatisfaction would be as
    wrong as recording it as agreement."""
    closed = services.record_feedback_and_close(decided, method="By phone", actor=supervisor)
    assert closed.complainant_satisfied is None


def test_the_database_refuses_a_close_with_no_feedback(decided):
    from django.db import IntegrityError, transaction

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            decided.status = GrievanceStatus.CLOSED
            decided.feedback_given_at = None
            decided.save()


# ---------------------------------------------------------------------------
# The pause
# ---------------------------------------------------------------------------


def test_a_pause_needs_a_reason_and_a_date_to_come_back(under_review, supervisor):
    """A pause with no reason is a hiding place; a pause with no end is a case
    nobody comes back to."""
    with pytest.raises(TransitionError):
        services.pause_for_complainant(under_review, reason="", chase_date=date.today(), actor=supervisor)
    with pytest.raises(TransitionError):
        services.pause_for_complainant(under_review, reason="Her bank details", chase_date=None, actor=supervisor)


def test_the_deadline_moves_by_however_long_the_wait_lasted(under_review, supervisor):
    """Leaving the deadline where it was would charge the programme for time it
    spent waiting on somebody else, which teaches people not to pause."""
    original = under_review.due_on
    services.pause_for_complainant(
        under_review, reason="Her bank details", chase_date=date.today() + timedelta(days=7), actor=supervisor
    )
    under_review.paused_on = date.today() - timedelta(days=10)
    under_review.save(update_fields=["paused_on"])

    services.resume(under_review, actor=supervisor)

    assert under_review.status == GrievanceStatus.UNDER_REVIEW
    assert under_review.due_on > original
    assert under_review.pause_reason == ""


# ---------------------------------------------------------------------------
# The appeal ladder
# ---------------------------------------------------------------------------


def test_an_appeal_creates_a_child_at_the_next_tier(decided, supervisor):
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    child = services.appeal(closed, ground="The payroll they checked was the wrong month.", actor=supervisor)

    assert child.parent_grievance_id == closed.pk
    assert child.tier == Tier.WOREDA
    assert child.status == GrievanceStatus.RECEIVED
    closed.refresh_from_db()
    assert closed.status == GrievanceStatus.APPEALED


def test_the_appeal_carries_the_statement_and_not_the_decision(decided, supervisor):
    """The appeal is heard on what the complainant said, not on what the tier
    below concluded about it."""
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    child = services.appeal(closed, ground="They checked the wrong month.", actor=supervisor)

    assert child.summary == closed.summary
    assert child.outcome == ""


def test_an_appeal_needs_a_ground(decided, supervisor):
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    with pytest.raises(TransitionError):
        services.appeal(closed, ground="  ", actor=supervisor)


def test_the_appeal_window_closes(decided, supervisor, settings):
    settings.GRIEVANCE_APPEAL_WINDOW_DAYS = 15
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    closed.resolution_date = date.today() - timedelta(days=40)
    closed.save(update_fields=["resolution_date"])

    with pytest.raises(TransitionError):
        services.appeal(closed, ground="Too late.", actor=supervisor)


def test_there_is_nothing_above_the_federal_tier(decided, supervisor):
    """Region and federal are recorded, not worked. Offering an appeal beyond
    the chain would put a queue in front of somebody who does not use this."""
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    closed.tier = Tier.FEDERAL
    closed.save(update_fields=["tier"])

    with pytest.raises(TransitionError):
        services.appeal(closed, ground="Still wrong.", actor=supervisor)


def test_nothing_leaves_an_appealed_record(decided, supervisor):
    """The work continues on the child, which has its own clock."""
    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    services.appeal(closed, ground="Wrong month.", actor=supervisor)
    closed.refresh_from_db()

    with pytest.raises(TransitionError):
        services.start_review(closed, actor=supervisor)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def test_the_overturn_rate_carries_its_denominator(decided, supervisor):
    """One of three overturned is not 33%. A zero overturn rate is a finding,
    not a success, and neither reads without the denominator."""
    from apps.grievances.models import Grievance

    closed = services.record_feedback_and_close(decided, method="In person", actor=supervisor)
    child = services.appeal(closed, ground="Wrong month.", actor=supervisor)
    services.acknowledge(child, method="By phone", actor=supervisor)
    services.start_review(child, actor=supervisor)
    services.decide(child, outcome=Outcome.UPHELD, reason="The March payroll was the one to check.", actor=supervisor)

    rate = services.overturn_rate(Grievance.objects.all())
    assert rate == {"appeals_decided": 1, "overturned": 1}


def test_referring_out_stops_the_clock(under_review, supervisor):
    referred = services.refer_out(under_review, to="Adama police, ref 2018/442", actor=supervisor)
    assert referred.status == GrievanceStatus.REFERRED_OUT
    assert referred.is_open is False
    assert referred.resolution_date is not None


def test_referring_out_needs_to_name_the_body(under_review, supervisor):
    with pytest.raises(TransitionError):
        services.refer_out(under_review, to="", actor=supervisor)
