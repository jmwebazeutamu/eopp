"""Placement and retention — spec §4.7, Sprint 5.

Three things carry most of the risk and most of these tests:

* **The checkpoints open with the placement.** A placement written without them
  is a placement nobody follows up, because the queue, the reminders and the
  retention figure all read `RetentionCheck`.
* **An exit closes the outstanding checks.** Otherwise the reminder keeps
  telephoning somebody about a job that ended in March.
* **The retention denominator is answered checks, not placements.** Divide by
  placements and the rate falls every time the programme succeeds at placing
  somebody new.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.alerts import tasks
from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.placements import services
from apps.placements.models import (
    CHECKPOINT_DAYS,
    ExitReason,
    Placement,
    PlacementType,
    RetentionCheck,
    RetentionStatus,
)
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def liaison(db):
    return User.objects.create_user("liaison-1", "pw-Test-12345", full_name="Liaison One", role=Role.EMPLOYER_LIAISON)


@pytest.fixture
def other_liaison(db):
    return User.objects.create_user("liaison-2", "pw-Test-12345", full_name="Liaison Two", role=Role.EMPLOYER_LIAISON)


@pytest.fixture
def make_placement(db, liaison, make_referral, taxonomy):
    def _make(case, placement_date=None, recorded_by=None, **fields):
        return services.record_placement(
            case=case,
            employer_name=fields.pop("employer_name", "Adama Textiles"),
            sector=fields.pop("sector", "Manufacturing"),
            placement_type=fields.pop("placement_type", PlacementType.JOB),
            placement_date=placement_date or date.today() - timedelta(days=100),
            recorded_by=recorded_by or liaison,
            source_referral=fields.pop("source_referral", make_referral(case, category=taxonomy["employment"])),
            **fields,
        )

    return _make


# ---------------------------------------------------------------------------
# Recording a placement
# ---------------------------------------------------------------------------


def test_a_placement_opens_all_three_checkpoints(make_case, case_manager, make_placement):
    placement = make_placement(make_case(case_manager))
    checks = placement.retention_checks.order_by("checkpoint")

    assert [check.checkpoint for check in checks] == list(CHECKPOINT_DAYS)
    assert all(check.status == RetentionStatus.PENDING for check in checks)
    assert checks[0].due_date == placement.placement_date + timedelta(days=30)


def test_opening_the_checkpoints_twice_does_not_double_the_queue(make_case, case_manager, make_placement):
    """A backfill over existing placements must not put every youth in the
    queue twice."""
    placement = make_placement(make_case(case_manager))
    services.open_checkpoints(placement)
    assert placement.retention_checks.count() == 3


def test_a_fourth_checkpoint_is_refused_by_the_database(make_case, case_manager, make_placement):
    placement = make_placement(make_case(case_manager))
    with pytest.raises(IntegrityError), transaction.atomic():
        RetentionCheck.objects.create(placement=placement, checkpoint=30, due_date=date.today())


def test_a_placement_moves_the_case_to_placed(make_case, case_manager, make_placement):
    from apps.cases.models import CaseStatus

    case = make_case(case_manager)
    make_placement(case)
    case.refresh_from_db()
    assert case.case_status == CaseStatus.PLACED


def test_a_placement_requires_a_source_referral(make_case, case_manager, liaison):
    with pytest.raises(ValidationError):
        services.record_placement(
            case=make_case(case_manager),
            employer_name="Adama Textiles",
            sector="Manufacturing",
            placement_type=PlacementType.JOB,
            placement_date=date.today(),
            recorded_by=liaison,
        )


def test_only_employment_or_apprenticeship_referrals_may_create_a_placement(
    make_case, case_manager, liaison, make_referral, taxonomy
):
    case = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.record_placement(
            case=case,
            employer_name="Adama Textiles",
            sector="Manufacturing",
            placement_type=PlacementType.JOB,
            placement_date=date.today(),
            recorded_by=liaison,
            source_referral=make_referral(case, category=taxonomy["training"]),
        )
    assert "source_referral" in caught.value.message_dict


def test_a_placement_cannot_start_in_the_future(make_case, case_manager, liaison, make_referral, taxonomy):
    case = make_case(case_manager)
    with pytest.raises(ValidationError):
        services.record_placement(
            case=case,
            employer_name="Adama Textiles",
            sector="Manufacturing",
            placement_type=PlacementType.JOB,
            placement_date=date.today() + timedelta(days=10),
            recorded_by=liaison,
            source_referral=make_referral(case, category=taxonomy["employment"]),
        )


def test_a_wage_may_be_left_blank(make_case, case_manager, make_placement):
    """Youth often will not say, and a guessed wage is worse than a blank."""
    placement = make_placement(make_case(case_manager), wage_amount=None)
    assert placement.wage_amount is None


# ---------------------------------------------------------------------------
# Exits — OQ-5
# ---------------------------------------------------------------------------


def test_an_exit_without_a_reason_is_refused_by_the_database(make_case, case_manager, make_placement):
    """OQ-5's whole point: by the time somebody asks why she left, nobody
    remembers."""
    placement = make_placement(make_case(case_manager))
    with pytest.raises(IntegrityError), transaction.atomic():
        Placement.objects.filter(pk=placement.pk).update(exit_date=date.today(), exit_reason="")


def test_an_exit_closes_the_outstanding_checks(make_case, case_manager, make_placement, liaison):
    """Once she has left, "still there at 90 days" is answered. Leaving them
    pending would keep telephoning about a job that ended."""
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=100))
    services.record_exit(
        placement, exit_date=date.today() - timedelta(days=10), exit_reason=ExitReason.DISMISSED, actor=liaison
    )

    assert not placement.retention_checks.pending().exists()


def test_an_exit_answers_each_checkpoint_from_the_date_she_left(make_case, case_manager, make_placement, liaison):
    """A checkpoint that fell due before she left was genuinely retained then.

    Answering all three as "exited" would understate retention at 30 days for a
    youth who held the job for two months.
    """
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=100))
    services.record_exit(
        placement, exit_date=date.today() - timedelta(days=55), exit_reason=ExitReason.BETTER_JOB, actor=liaison
    )
    answers = {check.checkpoint: check.status for check in placement.retention_checks.all()}

    assert answers[30] == RetentionStatus.RETAINED  # she was 45 days in
    assert answers[60] == RetentionStatus.EXITED
    assert answers[90] == RetentionStatus.EXITED


def test_a_placement_cannot_be_exited_twice(make_case, case_manager, make_placement, liaison):
    placement = make_placement(make_case(case_manager))
    services.record_exit(placement, exit_date=date.today(), exit_reason=ExitReason.RESIGNED, actor=liaison)
    with pytest.raises(ValidationError):
        services.record_exit(placement, exit_date=date.today(), exit_reason=ExitReason.DISMISSED, actor=liaison)


def test_leaving_for_a_better_job_is_reported_apart_from_the_rest(make_case, case_manager, make_placement, liaison):
    """ "Left for a better job" and "dismissed" are opposite results, and a free
    text field could not tell a report which had happened."""
    up = make_placement(make_case(case_manager, name="Up"))
    services.record_exit(up, exit_date=date.today(), exit_reason=ExitReason.BETTER_JOB, actor=liaison)
    down = make_placement(make_case(case_manager, name="Down"))
    services.record_exit(down, exit_date=date.today(), exit_reason=ExitReason.DISMISSED, actor=liaison)

    disposition = services.exit_disposition(Placement.objects.all())
    assert disposition["total_exits"] == 2
    assert disposition["upward"] == 1


# ---------------------------------------------------------------------------
# Retention checks
# ---------------------------------------------------------------------------


def test_a_check_needs_an_actor_and_a_date(make_case, case_manager, make_placement):
    """§9 wants a name against a status change, and a retention figure whose
    checks nobody signed is not evidence."""
    placement = make_placement(make_case(case_manager))
    check = placement.retention_checks.first()
    with pytest.raises(ValidationError):
        services.record_check(check, status=RetentionStatus.RETAINED, actor=None)


def test_recording_a_check_stamps_who_and_when(make_case, case_manager, make_placement, liaison):
    placement = make_placement(make_case(case_manager))
    check = placement.retention_checks.first()
    services.record_check(check, status=RetentionStatus.RETAINED, actor=liaison)

    assert check.status == RetentionStatus.RETAINED
    assert check.checked_by == liaison
    assert check.checked_on == date.today()


def test_answering_a_check_as_exited_points_at_the_placement_instead(make_case, case_manager, make_placement, liaison):
    """Recording it on the check alone would leave the placement open and count
    her as employed in the retention figure."""
    placement = make_placement(make_case(case_manager))
    check = placement.retention_checks.first()
    with pytest.raises(ValidationError) as caught:
        services.record_check(check, status=RetentionStatus.EXITED, actor=liaison)
    assert "exit" in " ".join(caught.value.messages).lower()


def test_unreachable_is_an_answer_and_not_a_loss(make_case, case_manager, make_placement, liaison):
    """At 90 days a real share of youth cannot be contacted. Counting them as
    "not retained" would overstate loss; as retained, overstate success."""
    placement = make_placement(make_case(case_manager))
    for check in placement.retention_checks.all():
        services.record_check(check, status=RetentionStatus.UNREACHABLE, actor=liaison)

    retained, answered, unreachable, _due = services.retention_inputs(Placement.objects.all(), 90)
    assert (retained, answered, unreachable) == (0, 1, 1)


def test_the_retention_denominator_is_answered_checks_not_placements(make_case, case_manager, make_placement, liaison):
    """Divide by placements and the rate falls every time the programme places
    somebody new — a figure that drops when the programme succeeds."""
    answered = make_placement(make_case(case_manager, name="Answered"))
    services.record_check(answered.retention_checks.get(checkpoint=90), status=RetentionStatus.RETAINED, actor=liaison)
    make_placement(make_case(case_manager, name="Unanswered"))

    retained, denominator, _unreachable, _due = services.retention_inputs(Placement.objects.all(), 90)
    assert (retained, denominator) == (1, 1)


def test_the_reported_anchor_excludes_subsidised_placements(make_case, case_manager, make_placement, liaison):
    """OQ-9: "wage-employed three months after completion, unsubsidised". A
    placement the programme pays for is not that."""
    subsidised = make_placement(make_case(case_manager, name="Subsidised"), is_subsidised=True)
    services.record_check(
        subsidised.retention_checks.get(checkpoint=90), status=RetentionStatus.RETAINED, actor=liaison
    )

    figures = services.reportable_retention_inputs(Placement.objects.all())
    assert figures["answered"] == 0
    assert figures["excluded_subsidised"] == 1


# ---------------------------------------------------------------------------
# Reminders — §4.7 "including reminders", §4.13
# ---------------------------------------------------------------------------


def test_a_due_check_raises_a_retention_alert(make_case, case_manager, make_placement):
    make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=40))

    assert tasks.detect_retention_checks_due() == 1
    alert = Alert.objects.get(alert_type=AlertType.RETENTION_CHECK_DUE)
    assert "30-day" in alert.summary


def test_a_check_not_yet_due_raises_nothing(make_case, case_manager, make_placement):
    make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=10))
    assert tasks.detect_retention_checks_due() == 0


def test_two_outstanding_checkpoints_raise_one_alert(make_case, case_manager, make_placement):
    """A youth whose 30 and 60-day checks are both outstanding needs one phone
    call, and two alerts for one call is how an inbox stops being read."""
    make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=70))

    assert tasks.detect_retention_checks_due() == 1
    assert Alert.objects.filter(alert_type=AlertType.RETENTION_CHECK_DUE).count() == 1


def test_an_exited_placement_stops_asking(make_case, case_manager, make_placement, liaison):
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=100))
    services.record_exit(
        placement, exit_date=date.today() - timedelta(days=5), exit_reason=ExitReason.CONTRACT_ENDED, actor=liaison
    )
    assert tasks.detect_retention_checks_due() == 0


def test_the_alert_clears_once_the_checks_are_answered(make_case, case_manager, make_placement, liaison):
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=40))
    tasks.detect_retention_checks_due()

    for check in placement.retention_checks.due():
        services.record_check(check, status=RetentionStatus.RETAINED, actor=liaison)

    assert tasks.resolve_cleared_alerts() == 1
    assert Alert.objects.get(alert_type=AlertType.RETENTION_CHECK_DUE).status == AlertStatus.ACTIONED


# ---------------------------------------------------------------------------
# §7 scoping
# ---------------------------------------------------------------------------


def test_an_employer_liaison_sees_the_placements_she_recorded(
    as_user, liaison, other_liaison, make_case, case_manager, make_placement
):
    mine = make_placement(make_case(case_manager, name="Mine"), recorded_by=liaison)
    make_placement(make_case(case_manager, name="Theirs"), recorded_by=other_liaison)

    response = as_user(liaison).get("/api/v1/placements/")
    assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]


def test_an_employer_liaison_reaches_the_case_behind_her_own_placement(
    as_user, liaison, make_case, case_manager, make_placement
):
    case = make_case(case_manager)
    make_placement(case, recorded_by=liaison)

    response = as_user(liaison).get("/api/v1/cases/")
    assert [row["id"] for row in response.data["results"]] == [str(case.pk)]


def test_a_trainer_cannot_read_placements_she_did_not_record(as_user, db, make_case, case_manager, make_placement):
    trainer = User.objects.create_user("trainer-x", "pw-Test-12345", full_name="Trainer", role=Role.TRAINER)
    make_placement(make_case(case_manager))

    response = as_user(trainer).get("/api/v1/placements/")
    assert response.data["count"] == 0


def test_the_due_queue_is_scoped_like_everything_else(
    as_user, liaison, other_liaison, make_case, case_manager, make_placement
):
    make_placement(
        make_case(case_manager, name="Mine"), placement_date=date.today() - timedelta(days=40), recorded_by=liaison
    )
    make_placement(
        make_case(case_manager, name="Theirs"),
        placement_date=date.today() - timedelta(days=40),
        recorded_by=other_liaison,
    )

    response = as_user(liaison).get("/api/v1/placements/checks/due/")
    assert response.status_code == 200
    assert response.data["count"] == 1


def test_an_exit_cannot_be_patched_onto_a_placement(as_user, case_manager, make_case, make_placement):
    """It would leave three checks pending against a job that has ended."""
    placement = make_placement(make_case(case_manager))
    as_user(case_manager).patch(
        f"/api/v1/placements/{placement.pk}/",
        {"exit_date": date.today().isoformat(), "exit_reason": ExitReason.DISMISSED},
        format="json",
    )
    placement.refresh_from_db()

    assert placement.exit_date is None
    assert placement.retention_checks.pending().count() == 3


def test_recording_an_exit_through_the_api_closes_the_checks(as_user, case_manager, make_case, make_placement):
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=100))
    response = as_user(case_manager).post(
        f"/api/v1/placements/{placement.pk}/exit/",
        {"exit_date": date.today().isoformat(), "exit_reason": ExitReason.BETTER_JOB},
        format="json",
    )
    placement.refresh_from_db()

    assert response.status_code == 200
    assert placement.exit_date == date.today()
    assert not placement.retention_checks.pending().exists()


def test_the_api_refuses_a_category_not_flagged_for_placement(
    as_user, case_manager, make_case, make_referral, taxonomy
):
    """This viewset already saved through the service, so the rule held here.

    Pinned anyway: `perform_create` is one edit away from `serializer.save()`,
    which is exactly how the same rule went unenforced on enterprises.
    """
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["training"])

    response = as_user(case_manager).post(
        "/api/v1/placements/",
        {
            "source_referral": str(referral.pk),
            "employer_name": "Wrong Category Ltd",
            "sector": "Agro-processing",
            "placement_type": PlacementType.JOB,
            "placement_date": (date.today() - timedelta(days=5)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400
    assert "source_referral" in response.data
    assert not Placement.objects.exists()


def test_an_administrator_can_widen_which_categories_open_a_placement(
    case_manager, make_case, make_referral, taxonomy, partner
):
    """The flag is configuration (§9), not a tuple in `apps.placements.models`.

    A programme whose training partners place their own graduates turns this on
    in the admin rather than waiting for a deploy.
    """
    training = taxonomy["training"]
    training.creates_placement = True
    training.save(update_fields=["creates_placement"])

    case = make_case(case_manager)
    placement = services.record_placement(
        case=case,
        employer_name="Trained And Placed",
        sector="Agro-processing",
        placement_type=PlacementType.JOB,
        placement_date=date.today() - timedelta(days=5),
        recorded_by=case_manager,
        source_referral=make_referral(case, category=training),
    )

    assert placement.pk is not None
    assert RetentionCheck.objects.filter(placement=placement).count() == 3


def test_a_placement_created_through_the_api_opens_its_checkpoints(
    as_user, case_manager, make_case, make_referral, taxonomy
):
    """The viewset saves through the service for this reason: a placement
    written without its checks is one nobody follows up."""
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["employment"])
    response = as_user(case_manager).post(
        "/api/v1/placements/",
        {
            "source_referral": str(referral.pk),
            "employer_name": "Bishoftu Foods",
            "sector": "Agro-processing",
            "placement_type": PlacementType.JOB,
            "placement_date": (date.today() - timedelta(days=5)).isoformat(),
        },
        format="json",
    )
    assert response.status_code == 201
    assert RetentionCheck.objects.filter(placement_id=response.data["id"]).count() == 3
    assert str(response.data["case"]) == str(case.pk)


def test_an_employer_liaison_can_answer_her_own_queue(as_user, liaison, make_case, case_manager, make_placement):
    """§7 gives the role no case write, and she is the person who makes the call.

    Gating the check on `case_write` left her looking at a queue she could not
    action — which is the one thing that screen exists for.
    """
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=40))
    check = placement.retention_checks.get(checkpoint=30)

    response = as_user(liaison).post(
        f"/api/v1/placements/checks/{check.pk}/record/", {"status": RetentionStatus.RETAINED}, format="json"
    )
    check.refresh_from_db()

    assert response.status_code == 200
    assert check.status == RetentionStatus.RETAINED
    assert check.checked_by == liaison


def test_a_supervisor_reads_the_queue_and_cannot_answer_it(
    as_user, supervisor, make_case, case_manager, make_placement
):
    """A placement figure is a claim about something that happened, made by
    whoever was there."""
    placement = make_placement(make_case(case_manager), placement_date=date.today() - timedelta(days=40))
    check = placement.retention_checks.get(checkpoint=30)

    assert as_user(supervisor).get("/api/v1/placements/").status_code == 200
    refused = as_user(supervisor).post(
        f"/api/v1/placements/checks/{check.pk}/record/", {"status": RetentionStatus.RETAINED}, format="json"
    )
    assert refused.status_code == 403
