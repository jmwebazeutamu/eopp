"""The safeguarding lane.

A different product that happens to live in the same application. What is worth
asserting is not that the code runs but that four specific people cannot read a
disclosure: a supervisor in the same woreda, a facilitator, a focal point whose
appointment has ended, and the system administrator.

The last of those reverses a decision that holds everywhere else in this
platform, and the test is here so that reversing it back is a deliberate act.
"""

from datetime import date, timedelta

import pytest

from apps.grievances import safeguarding, services
from apps.grievances.models import (
    ComplaintType,
    GrievanceAccess,
    RaisedBy,
    SafeguardingFocalPoint,
)
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def disclosure(db, supervisor):
    return services.raise_grievance(
        complaint_type=ComplaintType.SAFEGUARDING,
        raised_by=RaisedBy.YOUTH,
        summary="A matter I will only discuss with the focal point.",
        assigned_staff=supervisor,
        woreda="Adama",
    )


@pytest.fixture
def focal_point(db):
    person = User.objects.create_user(
        "fp-adama", "pw-Test-12345", full_name="Focal Point", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    SafeguardingFocalPoint.objects.create(woreda="Adama", person=person)
    return person


def test_the_category_is_restricted_without_anybody_ticking_a_box(disclosure):
    """A disclosure that reached the shared queue because somebody left a box
    unticked is the whole failure mode."""
    assert disclosure.is_restricted is True


def test_an_ordinary_complaint_is_not(raise_grievance):
    assert raise_grievance().is_restricted is False


def test_a_named_focal_point_may_read_it(disclosure, focal_point):
    assert safeguarding.may_read_content(focal_point, disclosure) is True


def test_a_supervisor_in_the_same_woreda_may_not(disclosure, supervisor, db):
    other = User.objects.create_user(
        "sup-c", "pw-Test-12345", full_name="Other", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    assert safeguarding.may_read_content(other, disclosure) is False


def test_the_administrator_may_not(disclosure, system_admin):
    """Everywhere else the administrator reads everything, and that widening is
    a confirmed decision. It is reversed here, for restricted content only."""
    assert safeguarding.may_read_content(system_admin, disclosure) is False


def test_a_focal_point_for_another_woreda_may_not(disclosure, db):
    person = User.objects.create_user(
        "fp-lume", "pw-Test-12345", full_name="Lume FP", role=Role.SUPERVISOR, woreda_assignment=["Lume"]
    )
    SafeguardingFocalPoint.objects.create(woreda="Lume", person=person)
    assert safeguarding.may_read_content(person, disclosure) is False


def test_an_appointment_that_has_ended_does_not_read_last_month(disclosure, db):
    """Dated, not flagged: a focal point who left in April must not read March's
    disclosure in May."""
    person = User.objects.create_user(
        "fp-old", "pw-Test-12345", full_name="Former FP", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    SafeguardingFocalPoint.objects.create(
        woreda="Adama",
        person=person,
        from_date=date.today() - timedelta(days=400),
        to_date=date.today() - timedelta(days=30),
    )
    assert safeguarding.may_read_content(person, disclosure) is False


# ---------------------------------------------------------------------------
# Over HTTP — the payload, not the screen
# ---------------------------------------------------------------------------


def test_the_row_stays_in_the_queue_but_says_nothing(as_user, disclosure, db):
    """Redacted, not omitted. A disclosure that vanishes from every list is one
    nobody can be held to, and nothing counts it."""
    other = User.objects.create_user(
        "sup-d", "pw-Test-12345", full_name="Other", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    response = as_user(other).get("/api/v1/grievances/")

    assert response.data["count"] == 1
    row = response.data["results"][0]
    assert row["restricted"] is True
    assert row["woreda"] == "Adama"
    assert row["short_reference"]
    # Nothing that could identify a survivor or describe what happened.
    assert "summary" not in row
    assert "complainant_name" not in row
    assert "assigned_staff_name" not in row


def test_a_focal_point_gets_the_record(as_user, disclosure, focal_point):
    response = as_user(focal_point).get("/api/v1/grievances/")
    row = response.data["results"][0]
    assert row["restricted"] is False
    assert row["summary"].startswith("A matter I will only")


def test_the_administrator_sees_the_shape_and_not_the_content(as_user, disclosure, system_admin):
    row = as_user(system_admin).get("/api/v1/grievances/").data["results"][0]
    assert row["restricted"] is True
    assert "summary" not in row


def test_free_text_search_cannot_confirm_what_it_says(as_user, disclosure, focal_point, db):
    """A search box that returns a restricted row for the word in its summary
    has published the summary one word at a time."""
    other = User.objects.create_user(
        "sup-e", "pw-Test-12345", full_name="Other", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    response = as_user(other).get("/api/v1/grievances/?search=focal")
    assert response.data["count"] == 0


def test_opening_one_is_written_down(as_user, disclosure, focal_point):
    as_user(focal_point).get(f"/api/v1/grievances/{disclosure.pk}/")

    access = GrievanceAccess.objects.get(grievance=disclosure)
    assert access.reader == focal_point
    assert access.granted is True
    assert access.role == Role.SUPERVISOR


def test_a_refused_attempt_is_the_more_interesting_row(as_user, disclosure, system_admin):
    as_user(system_admin).get(f"/api/v1/grievances/{disclosure.pk}/")

    access = GrievanceAccess.objects.get(grievance=disclosure)
    assert access.reader == system_admin
    assert access.granted is False


def test_an_ordinary_complaint_is_not_logged(as_user, raise_grievance, supervisor):
    grievance = raise_grievance()
    as_user(supervisor).get(f"/api/v1/grievances/{grievance.pk}/")
    assert GrievanceAccess.objects.count() == 0


def test_reassigning_is_not_a_route_to_reading_one(disclosure, supervisor):
    """Assignment is a field anybody with write access can change.

    If the assignee could read a disclosure, a reader could grant herself access
    by putting her own name in that field — no other permission needed, and
    nothing on screen to say she had. The escape hatch is `recorded_by`, which
    is stamped once from the request and writable by nobody.
    """
    disclosure.assigned_staff = supervisor
    disclosure.save(update_fields=["assigned_staff"])

    assert safeguarding.may_read_content(supervisor, disclosure) is False


def test_the_person_who_wrote_it_down_may_read_it(disclosure, supervisor):
    """She already heard it. Hiding it from her protects nobody, and in a woreda
    with no focal point named yet she is the only reader there is."""
    disclosure.recorded_by = supervisor
    disclosure.save(update_fields=["recorded_by"])

    assert safeguarding.may_read_content(supervisor, disclosure) is True
