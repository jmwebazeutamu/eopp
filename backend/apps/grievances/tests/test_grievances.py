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
from apps.grievances.models import ComplaintType, Grievance, GrievanceStatus, Outcome, RaisedBy
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


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


def test_the_database_refuses_an_outcome_with_no_reason(raise_grievance):
    """A decision nobody explained is a status change wearing a decision's
    clothes, and the reason is what a complainant hears read back."""
    grievance = raise_grievance()
    with pytest.raises(IntegrityError), transaction.atomic():
        Grievance.objects.filter(pk=grievance.pk).update(outcome=Outcome.UPHELD, outcome_reason="")


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


def test_a_staff_conduct_complaint_is_hidden_from_everyone_but_its_assignee(as_user, db, supervisor, raise_grievance):
    """The person complained about may be the supervisor who would otherwise
    read it."""
    other = User.objects.create_user(
        "sup-b", "pw-Test-12345", full_name="Other Supervisor", role=Role.SUPERVISOR, woreda_assignment=["Adama"]
    )
    raise_grievance(complaint_type=ComplaintType.STAFF_CONDUCT, assigned_staff=other, summary="Serious matter.")

    assert as_user(supervisor).get("/api/v1/grievances/").data["count"] == 0
    assert as_user(other).get("/api/v1/grievances/").data["count"] == 1


def test_the_administrator_reads_everything_except_a_disclosure(as_user, system_admin, db, supervisor, raise_grievance):
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
        {"status": "CLOSED", "outcome": "UPHELD", "resolution_date": date.today().isoformat()},
        format="json",
    )
    grievance.refresh_from_db()
    # A client that could PATCH the status could close a case having told
    # nobody anything, which is the one thing the workflow exists to refuse.
    assert grievance.status == GrievanceStatus.RECEIVED
    assert grievance.outcome == ""


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


# ---------------------------------------------------------------------------
# One channel, two modules — added 2026-08-25
# ---------------------------------------------------------------------------


def test_a_complaint_names_one_subject_or_none(raise_grievance, make_case, case_manager, wlt_group):
    """`NONE` is a real subject type here, unlike on the referral side."""
    from apps.grievances.models import GrievanceSubjectType

    nobody = raise_grievance()
    assert nobody.subject_type == GrievanceSubjectType.NONE

    about_a_group = raise_grievance(subject_group=wlt_group)
    assert about_a_group.subject_type == GrievanceSubjectType.GROUP
    assert about_a_group.subject_label() == wlt_group.name


def test_a_group_complaint_takes_its_group_woreda(raise_grievance, wlt_group, wlt_locations):
    """A hand-typed woreda that disagrees scopes to one office and reports in
    another."""
    grievance = raise_grievance(subject_group=wlt_group, woreda="")
    assert grievance.woreda == wlt_locations["woreda"].name


def test_the_database_refuses_two_subjects(raise_grievance, make_case, case_manager, wlt_group):
    case = make_case(case_manager=case_manager)
    with pytest.raises(ValidationError):
        raise_grievance(case=case, subject_group=wlt_group)


def test_a_facilitator_reads_her_own_group_complaint(as_user, facilitator, raise_grievance, wlt_group):
    """The channel is shared. Gating it on `CanAccessCases` gave every WLT role
    a 403, so a savings group could not complain about anything."""
    raise_grievance(subject_group=wlt_group, summary="The bank refused to open the account.")

    response = as_user(facilitator).get("/api/v1/grievances/")
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_a_facilitator_does_not_thereby_read_case_complaints(as_user, facilitator, raise_grievance, wlt_group):
    """Reading a complaint about her group is not reading a young person's file."""
    raise_grievance(subject_group=wlt_group)
    raise_grievance(woreda="Adama", summary="A complaint about the youth programme.")

    response = as_user(facilitator).get("/api/v1/grievances/")
    assert response.data["count"] == 1
    assert response.data["results"][0]["subject_type"] == "GROUP"


def test_a_case_manager_does_not_read_a_group_complaint(as_user, case_manager, raise_grievance, wlt_group):
    """The boundary in the other direction, on the same channel."""
    raise_grievance(subject_group=wlt_group)
    assert as_user(case_manager).get("/api/v1/grievances/").data["count"] == 0


def test_a_facilitator_can_file_one(as_user, facilitator, wlt_group, supervisor):
    """Filing is the act the mechanism exists to receive. An outreach worker or
    a facilitator who can only read complaints cannot take one."""
    response = as_user(facilitator).post(
        "/api/v1/grievances/",
        {
            "subject_group": str(wlt_group.pk),
            "complaint_type": "PAYMENT",
            "raised_by": "YOUTH",
            "summary": "The group's grant has not arrived.",
            "assigned_staff": str(supervisor.pk),
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["subject_type"] == "GROUP"
