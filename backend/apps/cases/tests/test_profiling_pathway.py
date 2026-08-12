"""Profiling (§4.3) and Pathway Assignment (§4.4) tests."""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.cases.models import Pathway, PathwayAssignment, ProfilingRecord

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(make_case, case_manager):
    return make_case(case_manager)


@pytest.fixture
def pathway(case, case_manager):
    return PathwayAssignment.objects.create(
        case=case,
        selected_pathway=Pathway.TRAINING,
        assessor=case_manager,
        is_current=True,
    )


# ---------------------------------------------------------------------------
# Profiling — spec §4.3
# ---------------------------------------------------------------------------


def test_profiling_requires_at_least_one_eligibility_flag(case, case_manager):
    record = ProfilingRecord(case=case, assessor=case_manager, eligibility_flags=[])
    with pytest.raises(ValidationError) as exc:
        record.clean()
    assert "eligibility_flags" in exc.value.message_dict


def test_profiling_rejects_an_unknown_pathway_flag(case, case_manager):
    record = ProfilingRecord(case=case, assessor=case_manager, eligibility_flags=["ASTRONAUT"])
    with pytest.raises(ValidationError) as exc:
        record.clean()
    assert "eligibility_flags" in exc.value.message_dict


def test_profiling_assessment_cannot_be_in_the_future(case, case_manager):
    record = ProfilingRecord(
        case=case,
        assessor=case_manager,
        eligibility_flags=[Pathway.TRAINING],
        assessed_date=date.today() + timedelta(days=1),
    )
    with pytest.raises(ValidationError) as exc:
        record.clean()
    assert "assessed_date" in exc.value.message_dict


def test_latest_profiling_record_is_current(case, case_manager):
    """§3: "may be revised; latest record is current" — revision adds a row."""
    ProfilingRecord.objects.create(
        case=case,
        assessor=case_manager,
        eligibility_flags=[Pathway.TRAINING],
        assessed_date=date.today() - timedelta(days=30),
        vulnerability_index_score=10,
    )
    newer = ProfilingRecord.objects.create(
        case=case,
        assessor=case_manager,
        eligibility_flags=[Pathway.WAGE_EMPLOYMENT],
        assessed_date=date.today(),
        vulnerability_index_score=42,
    )
    assert case.current_profiling == newer
    assert case.profiling_records.count() == 2  # history preserved, not overwritten


def test_profiling_records_are_never_deleted(case, case_manager, as_user):
    record = ProfilingRecord.objects.create(case=case, assessor=case_manager, eligibility_flags=[Pathway.TRAINING])
    assert as_user(case_manager).delete(f"/api/v1/cases/profiling/{record.pk}/").status_code == 405


def test_profiling_records_the_logged_in_assessor(case, case_manager, as_user):
    response = as_user(case_manager).post(
        "/api/v1/cases/profiling/",
        {"case": str(case.pk), "eligibility_flags": [Pathway.TRAINING], "priority_flag": True},
        format="json",
    )
    assert response.status_code == 201, response.data
    # response.data holds the pre-render values, so this is a UUID, not a string.
    assert response.data["assessor"] == case_manager.pk
    assert response.data["eligibility_flags_display"] == ["Training"]


def test_profiling_is_scoped_to_the_caseload(case, case_manager, other_case_manager, make_case, as_user):
    theirs = make_case(other_case_manager, name="Theirs")
    ProfilingRecord.objects.create(case=theirs, assessor=other_case_manager, eligibility_flags=[Pathway.TRAINING])
    ProfilingRecord.objects.create(case=case, assessor=case_manager, eligibility_flags=[Pathway.TRAINING])

    response = as_user(case_manager).get("/api/v1/cases/profiling/")
    assert response.data["count"] == 1


# ---------------------------------------------------------------------------
# Pathway assignment — spec §4.4
# ---------------------------------------------------------------------------


def test_only_one_current_pathway_per_case(case, pathway, case_manager):
    """§4.4: "Only one record per case set true", enforced by a partial index."""
    with pytest.raises(IntegrityError), transaction.atomic():
        PathwayAssignment.objects.create(
            case=case,
            selected_pathway=Pathway.WAGE_EMPLOYMENT,
            assessor=case_manager,
            is_current=True,
        )


def test_a_superseded_pathway_cannot_also_be_current(case, pathway, case_manager):
    other = PathwayAssignment.objects.create(
        case=case, selected_pathway=Pathway.TRAINING, assessor=case_manager, is_current=False
    )
    pathway.superseded_by = other
    with pytest.raises(ValidationError) as exc:
        pathway.clean()
    assert "is_current" in exc.value.message_dict


def test_revise_supersedes_and_creates_a_new_current(case, pathway, case_manager):
    replacement = pathway.revise(
        selected_pathway=Pathway.SELF_EMPLOYMENT,
        assessor=case_manager,
        revision_reason="Youth chose enterprise after the case review",
    )

    pathway.refresh_from_db()
    case.refresh_from_db()

    assert pathway.is_current is False
    assert pathway.superseded_by == replacement
    assert pathway.revision_reason.startswith("Youth chose enterprise")
    assert replacement.is_current is True
    assert replacement.selected_pathway == Pathway.SELF_EMPLOYMENT
    # §4.2's pointer and §4.4's flag are maintained together.
    assert case.current_pathway_assignment == replacement
    assert case.pathway_assignments.current().count() == 1


def test_revise_records_case_activity(case, pathway, case_manager):
    case.last_activity_date = date.today() - timedelta(days=20)
    case.save(update_fields=["last_activity_date"])

    pathway.revise(Pathway.APPRENTICESHIP, case_manager, "Revised at case review")

    case.refresh_from_db()
    assert case.last_activity_date == date.today()


def test_only_the_current_pathway_can_be_revised(case, pathway, case_manager):
    replacement = pathway.revise(Pathway.TRAINING, case_manager, "First revision")
    pathway.refresh_from_db()

    with pytest.raises(ValidationError):
        pathway.revise(Pathway.WAGE_EMPLOYMENT, case_manager, "Second revision on a stale record")

    assert case.pathway_assignments.current().get() == replacement


def test_revision_chain_is_walkable(case, pathway, case_manager):
    """The history must reconstruct: original -> second -> third."""
    second = pathway.revise(Pathway.WAGE_EMPLOYMENT, case_manager, "Reason one")
    third = second.revise(Pathway.SELF_EMPLOYMENT, case_manager, "Reason two")

    pathway.refresh_from_db()
    second.refresh_from_db()

    assert pathway.superseded_by == second
    assert second.superseded_by == third
    assert third.superseded_by is None
    assert third.is_current is True
    assert case.pathway_assignments.count() == 3


def test_creating_a_second_pathway_via_api_is_refused(case, pathway, case_manager, as_user):
    response = as_user(case_manager).post(
        "/api/v1/cases/pathways/",
        {"case": str(case.pk), "selected_pathway": Pathway.TRAINING},
        format="json",
    )
    assert response.status_code == 400
    assert "case" in response.data


def test_revise_endpoint_requires_a_reason(case, pathway, case_manager, as_user):
    response = as_user(case_manager).post(
        f"/api/v1/cases/pathways/{pathway.pk}/revise/",
        {"selected_pathway": Pathway.TRAINING},
        format="json",
    )
    assert response.status_code == 400
    assert "revision_reason" in response.data


def test_revise_endpoint_returns_the_replacement(case, pathway, case_manager, as_user):
    response = as_user(case_manager).post(
        f"/api/v1/cases/pathways/{pathway.pk}/revise/",
        {"selected_pathway": Pathway.APPRENTICESHIP, "revision_reason": "Apprenticeship slot became available"},
        format="json",
    )
    assert response.status_code == 201, response.data
    assert response.data["selected_pathway"] == Pathway.APPRENTICESHIP
    assert response.data["is_current"] is True


def test_supervisor_cannot_revise_a_pathway(case, pathway, supervisor, as_user):
    """§7 makes the supervisor read-only on case content."""
    response = as_user(supervisor).post(
        f"/api/v1/cases/pathways/{pathway.pk}/revise/",
        {"selected_pathway": Pathway.TRAINING, "revision_reason": "Should not work"},
        format="json",
    )
    assert response.status_code == 403


def test_case_detail_exposes_the_current_pathway_and_profiling(case, pathway, case_manager, as_user):
    ProfilingRecord.objects.create(
        case=case, assessor=case_manager, eligibility_flags=[Pathway.TRAINING], priority_flag=True
    )
    response = as_user(case_manager).get(f"/api/v1/cases/{case.pk}/")
    assert response.status_code == 200
    assert response.data["current_pathway"]["selected_pathway"] == Pathway.TRAINING
    assert response.data["current_profiling"]["priority_flag"] is True
