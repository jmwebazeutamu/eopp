"""Training Enrolment — spec §4.5, Sprint 5.

The behaviour worth pinning is the part with consequences beyond the row:
completion raises the onward prompt, a dropout carries its reason, a failed
assessment is not a dropout, and a trainer sees the enrolments she recorded and
nothing else.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.alerts import tasks
from apps.training import services
from apps.training.models import CertificateStatus, CompletionStatus, TrainingEnrolment, TrainingType
from apps.users.models import Role, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def trainer(db):
    return User.objects.create_user("trainer-1", "pw-Test-12345", full_name="Trainer One", role=Role.TRAINER)


@pytest.fixture
def other_trainer(db):
    return User.objects.create_user("trainer-2", "pw-Test-12345", full_name="Trainer Two", role=Role.TRAINER)


@pytest.fixture
def make_enrolment(db, partner, trainer, make_referral, taxonomy):
    def _make(case, training_type=TrainingType.LIFE_SKILLS, recorded_by=None, **fields):
        fields.setdefault("start_date", date.today() - timedelta(days=30))
        fields.setdefault("end_date", date.today() + timedelta(days=30))
        if training_type == TrainingType.TVET:
            fields.setdefault("trade_or_skill_area", "Carpentry")
        fields.setdefault("source_referral", make_referral(case, category=taxonomy["training"]))
        return services.enrol(
            case=case,
            training_type=training_type,
            training_provider=partner,
            recorded_by=recorded_by or trainer,
            **fields,
        )

    return _make


# ---------------------------------------------------------------------------
# §4.5's own rules
# ---------------------------------------------------------------------------


def test_a_tvet_course_has_to_name_its_trade(make_case, case_manager, partner, trainer, make_referral, taxonomy):
    """§4.5 marks the field TVET-only, which reads both ways: a technical course
    with no trade cannot be reported against a skills gap.

    The referral is supplied because an enrolment cannot exist without one — the
    point here is the trade, so the test must reach it rather than stopping at
    the earlier refusal.
    """
    case = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.enrol(
            case=case,
            training_type=TrainingType.TVET,
            training_provider=partner,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            recorded_by=trainer,
            source_referral=make_referral(case, category=taxonomy["training"]),
        )
    assert "trade_or_skill_area" in caught.value.message_dict


def test_only_a_category_flagged_for_it_may_open_an_enrolment(
    make_case, case_manager, partner, trainer, make_referral, taxonomy
):
    """§4.5 enrolments come from a referral, and *which* referrals is taxonomy.

    An employment referral is a real referral on the same case; it just does not
    deliver a course.
    """
    case = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.enrol(
            case=case,
            training_type=TrainingType.LIFE_SKILLS,
            training_provider=partner,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            recorded_by=trainer,
            source_referral=make_referral(case, category=taxonomy["employment"]),
        )
    assert "source_referral" in caught.value.message_dict


def test_the_api_refuses_a_non_training_referral_too(
    as_user, case_manager, partner, make_case, make_referral, taxonomy
):
    """The rule has to hold on the route people actually use.

    `perform_create` calls `serializer.save()`, and a ModelSerializer does not
    run `full_clean` — so a rule stated only in `Model.clean` was unenforced
    over the API while looking enforced in the model.
    """
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["employment"])

    response = as_user(case_manager).post(
        "/api/v1/training/",
        {
            "source_referral": str(referral.pk),
            "training_type": TrainingType.LIFE_SKILLS,
            "training_provider": str(partner.pk),
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=60)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 400
    assert "source_referral" in response.data
    assert not TrainingEnrolment.objects.exists()


def test_an_administrator_can_widen_which_categories_deliver_a_course(
    make_case, case_manager, partner, trainer, make_referral, taxonomy
):
    """The flag is configuration (§9), not a tuple in `apps.training.models`.

    A programme that starts delivering courses through apprenticeship partners
    turns this on in the admin. Before, the category she added silently could
    not open an enrolment and only a deploy could fix it.
    """
    apprenticeship = taxonomy["training"].__class__.objects.get(code="APPRENTICESHIP")
    apprenticeship.creates_training_enrolment = True
    apprenticeship.save(update_fields=["creates_training_enrolment"])

    case = make_case(case_manager)
    enrolment = services.enrol(
        case=case,
        training_type=TrainingType.LIFE_SKILLS,
        training_provider=partner,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=60),
        recorded_by=trainer,
        source_referral=make_referral(case, category=apprenticeship),
    )

    assert enrolment.pk is not None


def test_a_referral_on_another_case_cannot_open_an_enrolment(
    make_case, case_manager, partner, trainer, make_referral, taxonomy
):
    case = make_case(case_manager)
    other = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.enrol(
            case=case,
            training_type=TrainingType.LIFE_SKILLS,
            training_provider=partner,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            recorded_by=trainer,
            source_referral=make_referral(other, category=taxonomy["training"]),
        )
    assert "source_referral" in caught.value.message_dict


def test_a_life_skills_course_needs_no_trade(make_case, case_manager, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    assert enrolment.trade_or_skill_area == ""


def test_enrolling_stamps_case_activity(make_case, case_manager, make_enrolment):
    """A youth who started a course last week is not a stalled case, and the
    stall detector reads `last_activity_date`."""
    from apps.cases.models import Case

    case = make_case(case_manager)
    Case.objects.filter(pk=case.pk).update(last_activity_date=date.today() - timedelta(days=90))

    make_enrolment(case)
    case.refresh_from_db()
    assert case.last_activity_date == date.today()


def test_completion_records_a_date_and_arms_the_onward_trigger(make_case, case_manager, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    services.complete(enrolment, assessment_result="Pass", certificate_status=CertificateStatus.AWARDED)

    assert enrolment.completion_status == CompletionStatus.COMPLETED
    assert enrolment.completion_date == date.today()
    # §4.5 marks this System-set: true on completion, and it drives the prompt.
    assert enrolment.triggers_onward_referral is True
    assert enrolment.dropout_flag is False


def test_a_dropout_without_a_reason_is_refused(make_case, case_manager, make_enrolment):
    """A count of dropouts tells a programme nothing it can act on."""
    enrolment = make_enrolment(make_case(case_manager))
    with pytest.raises(ValidationError):
        services.drop_out(enrolment, reason="   ")


def test_a_dropout_sets_the_flag_and_the_date_together(make_case, case_manager, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    services.drop_out(enrolment, reason="Moved to another woreda.")

    assert enrolment.completion_status == CompletionStatus.DROPPED_OUT
    assert enrolment.dropout_flag is True
    assert enrolment.dropout_date == date.today()
    assert enrolment.triggers_onward_referral is False


def test_a_failed_assessment_is_not_a_dropout(make_case, case_manager, make_enrolment):
    """She attended to the end. Filing it as a dropout would understate
    attendance and hide an assessment problem that belongs to the provider."""
    enrolment = make_enrolment(make_case(case_manager))
    services.fail_assessment(enrolment, assessment_result="Did not reach the pass mark on the practical.")

    assert enrolment.completion_status == CompletionStatus.FAILED_ASSESSMENT
    assert enrolment.dropout_flag is False
    assert enrolment.triggers_onward_referral is False


def test_an_enrolment_can_only_conclude_once(make_case, case_manager, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    services.complete(enrolment)
    with pytest.raises(ValidationError):
        services.drop_out(enrolment, reason="Changed her mind.")


def test_an_attendance_rate_outside_the_range_is_refused(make_case, case_manager, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    with pytest.raises(ValidationError):
        services.record_attendance_rate(enrolment, attendance_rate=140)


# ---------------------------------------------------------------------------
# The completion rate — §8.3
# ---------------------------------------------------------------------------


def test_the_completion_rate_divides_by_concluded_not_by_enrolled(make_case, case_manager, make_enrolment):
    """A course still running is neither a completion nor a failure.

    Counting it as either would move the rate every time a cohort starts, which
    is the one thing a rate reported to a donor must not do.
    """
    completed = make_enrolment(make_case(case_manager, name="A"))
    services.complete(completed)
    dropped = make_enrolment(make_case(case_manager, name="B"))
    services.drop_out(dropped, reason="Family illness.")
    make_enrolment(make_case(case_manager, name="C"))  # still running

    completed_count, concluded = services.completion_rate_inputs(TrainingEnrolment.objects.all())
    assert (completed_count, concluded) == (1, 2)


def test_a_failed_assessment_sits_in_the_denominator(make_case, case_manager, make_enrolment):
    passed = make_enrolment(make_case(case_manager, name="A"))
    services.complete(passed)
    failed = make_enrolment(make_case(case_manager, name="B"))
    services.fail_assessment(failed, assessment_result="Below the pass mark.")

    assert services.completion_rate_inputs(TrainingEnrolment.objects.all()) == (1, 2)


# ---------------------------------------------------------------------------
# The onward prompt — §4.5, §6.2
# ---------------------------------------------------------------------------


def test_a_training_enrolment_requires_a_source_referral(make_case, case_manager, partner, trainer):
    with pytest.raises(ValidationError) as caught:
        services.enrol(
            case=make_case(case_manager),
            training_type=TrainingType.LIFE_SKILLS,
            training_provider=partner,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            recorded_by=trainer,
        )
    assert "source_referral" in caught.value.message_dict


def test_only_a_training_referral_may_create_a_training_enrolment(
    make_case, case_manager, partner, trainer, make_referral, taxonomy
):
    case = make_case(case_manager)
    with pytest.raises(ValidationError) as caught:
        services.enrol(
            case=case,
            training_type=TrainingType.LIFE_SKILLS,
            training_provider=partner,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=60),
            recorded_by=trainer,
            source_referral=make_referral(case, category=taxonomy["employment"]),
        )
    assert "source_referral" in caught.value.message_dict


def test_a_referral_sourced_training_does_not_raise_a_second_prompt(
    make_case, case_manager, make_referral, make_enrolment, taxonomy
):
    """The referral's own prompt already covers it. Two alerts for one decision
    is how an inbox stops being read."""
    case = make_case(case_manager)
    referral = make_referral(case)
    enrolment = make_enrolment(case, source_referral=referral)
    services.complete(enrolment)

    assert tasks.generate_training_onward_prompts() == 0


def test_the_prompt_clears_once_an_onward_referral_exists(make_case, case_manager, make_enrolment, make_referral):
    case = make_case(case_manager)
    enrolment = make_enrolment(case)
    services.complete(enrolment)
    tasks.generate_training_onward_prompts()

    enrolment.onward_referral = make_referral(case)
    enrolment.save(update_fields=["onward_referral", "updated_at"])

    assert not TrainingEnrolment.objects.awaiting_onward_prompt().exists()


def test_a_referral_sourced_enrolment_raises_no_training_side_prompt(make_case, case_manager, make_enrolment):
    """The referral's own prompt covers it; two jobs must not raise one prompt.

    Since §4.5 enrolments come from a referral this is now every new enrolment,
    which is why `generate_training_onward_prompts` is a legacy sweep.
    """
    enrolment = make_enrolment(make_case(case_manager))
    services.complete(enrolment)

    assert enrolment.source_referral is not None
    assert tasks.generate_training_onward_prompts() == 0


def test_an_enrolment_recorded_before_the_referral_rule_still_gets_its_prompt(
    make_case, case_manager, make_enrolment, make_referral
):
    """Those rows are still valid, and her youth still needs a next step.

    Written directly rather than through the service, because the service is
    what now refuses it — which is the state this sweep exists to drain.
    """
    enrolment = make_enrolment(make_case(case_manager))
    services.complete(enrolment)
    TrainingEnrolment.objects.filter(pk=enrolment.pk).update(source_referral=None)

    assert tasks.generate_training_onward_prompts() == 1
    # Idempotent: the second run finds the alert already open.
    assert tasks.generate_training_onward_prompts() == 0


# ---------------------------------------------------------------------------
# §7 scoping
# ---------------------------------------------------------------------------


def test_a_trainer_sees_the_enrolments_she_recorded(
    as_user, trainer, other_trainer, make_case, case_manager, make_enrolment
):
    mine = make_enrolment(make_case(case_manager, name="Mine"), recorded_by=trainer)
    make_enrolment(make_case(case_manager, name="Theirs"), recorded_by=other_trainer)

    response = as_user(trainer).get("/api/v1/training/")
    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]


def test_a_trainer_reaches_the_case_behind_her_own_enrolment(as_user, trainer, make_case, case_manager, make_enrolment):
    """§7 gives the role LINKED case scope. Sprint 5 is what resolves it."""
    case = make_case(case_manager)
    make_enrolment(case, recorded_by=trainer)

    response = as_user(trainer).get("/api/v1/cases/")
    assert [row["id"] for row in response.data["results"]] == [str(case.pk)]


def test_a_trainer_reaches_no_case_she_has_not_trained(
    as_user, trainer, other_trainer, make_case, case_manager, make_enrolment
):
    make_enrolment(make_case(case_manager, name="Theirs"), recorded_by=other_trainer)
    response = as_user(trainer).get("/api/v1/cases/")
    assert response.data["count"] == 0


def test_one_case_with_three_enrolments_appears_once(as_user, trainer, make_case, case_manager, make_enrolment):
    """The LINKED join fans out. Without `.distinct()` a paginated list would
    repeat the case and pages would overlap."""
    case = make_case(case_manager)
    for _ in range(3):
        make_enrolment(case, recorded_by=trainer)

    response = as_user(trainer).get("/api/v1/cases/")
    assert response.data["count"] == 1


def test_a_case_manager_sees_her_caseloads_enrolments(as_user, case_manager, make_case, make_enrolment):
    make_enrolment(make_case(case_manager))
    response = as_user(case_manager).get("/api/v1/training/")
    assert response.data["count"] == 1


def test_completion_status_cannot_be_patched_directly(as_user, case_manager, make_case, make_enrolment):
    """It moves through `services`, which stamps the date, derives the onward
    trigger and touches the case. A PATCH would skip all three."""
    enrolment = make_enrolment(make_case(case_manager))
    response = as_user(case_manager).patch(
        f"/api/v1/training/{enrolment.pk}/", {"completion_status": "COMPLETED"}, format="json"
    )
    enrolment.refresh_from_db()

    assert response.status_code == 200
    assert enrolment.completion_status == CompletionStatus.ENROLLED


def test_completing_through_the_api_arms_the_prompt(as_user, case_manager, make_case, make_enrolment):
    enrolment = make_enrolment(make_case(case_manager))
    response = as_user(case_manager).post(f"/api/v1/training/{enrolment.pk}/complete/", {}, format="json")
    enrolment.refresh_from_db()

    assert response.status_code == 200
    assert enrolment.triggers_onward_referral is True


def test_a_training_created_through_the_api_derives_its_case_from_the_referral(
    as_user, case_manager, make_case, partner, make_referral, taxonomy
):
    case = make_case(case_manager)
    referral = make_referral(case, category=taxonomy["training"])
    response = as_user(case_manager).post(
        "/api/v1/training/",
        {
            "source_referral": str(referral.pk),
            "training_type": TrainingType.LIFE_SKILLS,
            "training_provider": str(partner.pk),
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=60)).isoformat(),
        },
        format="json",
    )

    assert response.status_code == 201
    assert str(response.data["case"]) == str(case.pk)
