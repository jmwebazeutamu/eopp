"""Grievance — spec §4.10, Sprint 6.

The entity's whole design follows from one field: `case_id` is nullable. A
complaints channel that only accepts complaints from people already on file is
not a complaints channel, and everything else here — the woreda, the scoping,
the anonymous complainant — exists to make that work.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.grievances import services
from apps.grievances.models import ComplaintType, Grievance, RaisedBy, ResolutionStatus
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def raise_grievance(db, supervisor):
    def _raise(**fields):
        fields.setdefault("complaint_type", ComplaintType.SERVICE_QUALITY)
        fields.setdefault("raised_by", RaisedBy.YOUTH)
        fields.setdefault("summary", "The training centre had no materials for three weeks.")
        fields.setdefault("assigned_staff", supervisor)
        fields.setdefault("woreda", "Adama")
        return services.raise_grievance(**fields)

    return _raise


# ---------------------------------------------------------------------------
# A complaint with no case
# ---------------------------------------------------------------------------


def test_a_complaint_can_be_raised_with_no_case(raise_grievance):
    """§4.10 makes the case nullable, and that is the design: an employer's
    complaint about the programme names no youth."""
    grievance = raise_grievance(raised_by=RaisedBy.EMPLOYER, complainant_name="Adama Textiles")
    assert grievance.case_id is None
    assert grievance.woreda == "Adama"


def test_a_complaint_with_no_case_needs_a_woreda(raise_grievance):
    """Without one it is invisible to every supervisor, which is the only way it
    reaches anybody."""
    with pytest.raises(ValidationError) as caught:
        raise_grievance(woreda="")
    assert "woreda" in caught.value.message_dict


def test_a_complaint_with_a_case_inherits_its_woreda(raise_grievance, make_case, case_manager):
    case = make_case(case_manager, woreda="Bishoftu")
    grievance = raise_grievance(case=case, woreda="")
    assert grievance.woreda == "Bishoftu"


def test_a_complaint_may_be_anonymous(raise_grievance):
    grievance = raise_grievance(complainant_name="", complainant_contact="")
    assert grievance.pk is not None


def test_a_complaint_needs_a_description(raise_grievance):
    with pytest.raises(ValidationError):
        raise_grievance(summary="   ")


# ---------------------------------------------------------------------------
# Resolution — and the difference §4.10 insists on
# ---------------------------------------------------------------------------


def test_resolving_requires_saying_what_was_done(raise_grievance, supervisor):
    """A resolution rate computed over status changes nobody described is the
    kind of figure that survives until somebody asks for an example."""
    grievance = raise_grievance()
    with pytest.raises(ValidationError):
        services.resolve(grievance, notes="  ", actor=supervisor)


def test_the_database_refuses_a_resolution_with_no_notes(raise_grievance):
    grievance = raise_grievance()
    with pytest.raises(IntegrityError), transaction.atomic():
        Grievance.objects.filter(pk=grievance.pk).update(
            resolution_status=ResolutionStatus.RESOLVED, resolution_date=date.today(), resolution_notes=""
        )


def test_closing_without_resolution_is_not_a_resolution(raise_grievance, supervisor):
    """Folding the two would inflate the resolution rate with every complaint
    whose complainant withdrew or could not be traced."""
    resolved = raise_grievance()
    services.resolve(resolved, notes="Materials delivered and the centre apologised.", actor=supervisor)
    closed = raise_grievance()
    services.close_without_resolution(closed, reason="Complainant withdrew and could not be traced.", actor=supervisor)

    assert services.resolution_inputs(Grievance.objects.all()) == (1, 2)


def test_an_open_grievance_is_neither(raise_grievance, supervisor):
    """Counting it as a failure would make the rate fall every time somebody
    files a complaint."""
    resolved = raise_grievance()
    services.resolve(resolved, notes="Sorted.", actor=supervisor)
    raise_grievance()

    assert services.resolution_inputs(Grievance.objects.all()) == (1, 1)


def test_a_concluded_grievance_cannot_be_concluded_again(raise_grievance, supervisor):
    grievance = raise_grievance()
    services.resolve(grievance, notes="Sorted.", actor=supervisor)
    with pytest.raises(ValidationError):
        services.close_without_resolution(grievance, reason="Changed my mind.", actor=supervisor)


def test_time_to_resolution_is_measured_in_days(raise_grievance, supervisor):
    grievance = raise_grievance(date_raised=date.today() - timedelta(days=10))
    services.resolve(grievance, notes="Sorted.", actor=supervisor)
    assert services.median_days_to_resolution(Grievance.objects.all()) == 10


def test_an_overdue_grievance_is_one_nobody_answered(raise_grievance, settings):
    """A complaints process nobody answers is worse than none: it collects the
    complaint, creates the expectation, and does nothing with it."""
    settings.GRIEVANCE_RESPONSE_DAYS = 21
    raise_grievance(date_raised=date.today() - timedelta(days=30))
    raise_grievance(date_raised=date.today() - timedelta(days=3))

    assert services.overdue(Grievance.objects.all()).count() == 1


# ---------------------------------------------------------------------------
# Partner feedback — §4.11's qualitative counterpart
# ---------------------------------------------------------------------------


def test_a_referral_complaint_flags_itself_for_the_partner_panel(raise_grievance, partner):
    """A "referral delay" nobody ticked would never reach the panel, and the
    panel is the only place the complaint changes anything."""
    grievance = raise_grievance(complaint_type=ComplaintType.REFERRAL_DELAY, about_partner=partner)
    assert grievance.referral_quality_feedback_flag is True


def test_an_unrelated_complaint_does_not(raise_grievance):
    grievance = raise_grievance(complaint_type=ComplaintType.PAYMENT)
    assert grievance.referral_quality_feedback_flag is False


def test_partner_feedback_groups_complaints_by_partner(raise_grievance, make_partner):
    good = make_partner(name="Reliable TVET")
    poor = make_partner(name="Slow TVET")
    raise_grievance(complaint_type=ComplaintType.REFERRAL_DELAY, about_partner=poor)
    raise_grievance(complaint_type=ComplaintType.REFERRAL_QUALITY, about_partner=poor)
    raise_grievance(complaint_type=ComplaintType.SERVICE_QUALITY, about_partner=good)

    rows = services.partner_quality_feedback()
    assert rows[0]["partner"] == "Slow TVET"
    assert rows[0]["total"] == 2
    # The service-quality complaint is not referral feedback and does not appear.
    assert all(row["partner"] != "Reliable TVET" for row in rows)


# ---------------------------------------------------------------------------
# Who may read what
# ---------------------------------------------------------------------------


def test_a_supervisor_sees_complaints_from_her_own_woreda(as_user, supervisor, raise_grievance):
    raise_grievance(woreda="Adama")
    raise_grievance(woreda="Hawassa")

    response = as_user(supervisor).get("/api/v1/grievances/")
    assert response.data["count"] == 1
    assert response.data["results"][0]["woreda"] == "Adama"


def test_a_safeguarding_complaint_is_hidden_from_everyone_but_its_assignee(as_user, db, supervisor, raise_grievance):
    """The person complained about may be the supervisor who would otherwise
    read it."""
    other = User.objects.create_user(
        "sup-b", "pw-Test-12345", full_name="Other Supervisor", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    raise_grievance(complaint_type=ComplaintType.SAFEGUARDING, assigned_staff=other, summary="Serious matter.")

    assert as_user(supervisor).get("/api/v1/grievances/").data["count"] == 0
    assert as_user(other).get("/api/v1/grievances/").data["count"] == 1


def test_the_administrator_reads_everything(as_user, system_admin, db, supervisor, raise_grievance):
    raise_grievance(complaint_type=ComplaintType.STAFF_CONDUCT, assigned_staff=supervisor, summary="Serious.")
    assert as_user(system_admin).get("/api/v1/grievances/").data["count"] == 1


def test_a_linked_role_reads_no_grievances(as_user, db, raise_grievance):
    """A trainer has no business reading complaints about other people's cases,
    and the fail-closed default gives that for free."""
    trainer = User.objects.create_user("tr-x", "pw-Test-12345", full_name="Trainer", role=Role.TRAINER)
    raise_grievance()
    assert as_user(trainer).get("/api/v1/grievances/").data["count"] == 0


def test_resolution_cannot_be_patched_onto_a_grievance(as_user, supervisor, raise_grievance):
    grievance = raise_grievance()
    as_user(supervisor).patch(
        f"/api/v1/grievances/{grievance.pk}/",
        {"resolution_status": "RESOLVED", "resolution_date": date.today().isoformat()},
        format="json",
    )
    grievance.refresh_from_db()
    assert grievance.resolution_status == ResolutionStatus.OPEN


def test_creating_through_the_api_inherits_woreda_from_the_case(as_user, make_case, case_manager):
    case = make_case(case_manager, woreda="Bishoftu")
    response = as_user(case_manager).post(
        "/api/v1/grievances/",
        {
            "case": str(case.pk),
            "complaint_type": ComplaintType.SERVICE_QUALITY,
            "raised_by": RaisedBy.YOUTH,
            "summary": "The provider kept moving the appointment.",
            "assigned_staff": str(case_manager.pk),
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["woreda"] == "Bishoftu"
