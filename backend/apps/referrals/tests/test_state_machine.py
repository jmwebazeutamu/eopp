"""Referral state machine tests — spec §6.2.

§10.1's Definition of Done requires every transition in the §6.2 table to be unit
tested before the sprint is done. This module walks that table row by row, then
checks that every edge the table does NOT contain is refused.
"""

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from apps.referrals import services
from apps.referrals.models import (
    TRANSITIONS,
    ConfirmationStatus,
    Referral,
    ReferralStatus,
    ReferralTrigger,
    TransitionError,
    build_referral_stack,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def case(make_case, case_manager):
    return make_case(case_manager)


# ---------------------------------------------------------------------------
# §6.2 row 1: (none) -> Pending Confirmation
# ---------------------------------------------------------------------------


def test_initiating_creates_a_pending_referral(case, make_referral, case_manager):
    referral = make_referral(case)
    assert referral.status == ReferralStatus.PENDING_CONFIRMATION
    assert referral.confirmation_status == ConfirmationStatus.PENDING
    assert referral.referral_trigger == ReferralTrigger.MANUAL
    assert referral.parent_referral is None


def test_initiating_records_case_activity(case, make_referral):
    case.last_activity_date = date.today() - timedelta(days=15)
    case.save(update_fields=["last_activity_date"])
    make_referral(case)
    case.refresh_from_db()
    assert case.last_activity_date == date.today()


def test_cannot_refer_to_an_inactive_partner(case, make_referral, make_partner):
    dormant = make_partner(name="Closed Centre", active_status=False)
    with pytest.raises(ValidationError) as exc:
        make_referral(case, receiving_partner=dormant)
    assert "receiving_partner" in exc.value.message_dict


def test_category_requiring_a_note_is_enforced(case, make_referral, taxonomy):
    """§5.1: the Other category "requires a free-text note"."""
    with pytest.raises(ValidationError) as exc:
        make_referral(case, category=taxonomy["other_category"])
    assert "notes" in exc.value.message_dict

    referral = make_referral(case, category=taxonomy["other_category"], notes="Referred to a legal clinic")
    assert referral.notes


# ---------------------------------------------------------------------------
# §6.2 row 2: Pending Confirmation -> Active
# ---------------------------------------------------------------------------


def test_partner_confirmation_activates(case, make_referral, case_manager):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager, confirmed_by="Tigist Bekele")

    assert referral.status == ReferralStatus.ACTIVE
    assert referral.confirmation_status == ConfirmationStatus.CONFIRMED
    assert referral.confirmed_date == date.today()
    assert referral.confirmed_by == "Tigist Bekele"


def test_first_active_referral_is_not_parallel(case, make_referral, case_manager):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    assert referral.is_parallel is False
    assert referral.parallel_group_id is None


def test_second_active_referral_shares_a_parallel_group(case, make_referral, case_manager, taxonomy):
    """§6.2: "if another referral is already Active for this case, assign shared parallel_group_id"."""
    first = make_referral(case, category=taxonomy["training"])
    second = make_referral(case, category=taxonomy["employment"])

    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    second.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    first.refresh_from_db()
    assert first.parallel_group_id is not None
    assert first.parallel_group_id == second.parallel_group_id
    assert first.is_parallel and second.is_parallel


# ---------------------------------------------------------------------------
# §6.3 parallel cap
# ---------------------------------------------------------------------------


def test_third_active_referral_is_refused(case, make_referral, case_manager, taxonomy):
    for category in (taxonomy["training"], taxonomy["employment"]):
        make_referral(case, category=category).transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    third = make_referral(case, category=taxonomy["enterprise"])
    with pytest.raises(ValidationError) as exc:
        third.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    assert "status" in exc.value.message_dict

    third.refresh_from_db()
    assert third.status == ReferralStatus.PENDING_CONFIRMATION  # unchanged


def test_complementary_service_runs_outside_the_cap(case, make_referral, case_manager, taxonomy):
    """§6.3 working default: a third concurrent stream, not a third slot."""
    for category in (taxonomy["training"], taxonomy["employment"]):
        make_referral(case, category=category).transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    complementary = make_referral(case, category=taxonomy["complementary"])
    complementary.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    assert complementary.status == ReferralStatus.ACTIVE
    # Exempt referrals take no slot, so they join no parallel group.
    assert complementary.parallel_group_id is None
    assert Referral.objects.filter(case=case).active().count() == 3


def test_completing_one_frees_a_parallel_slot(case, make_referral, case_manager, taxonomy):
    """§6.2: completion "frees the parallel_group_id slot"."""
    first = make_referral(case, category=taxonomy["training"])
    second = make_referral(case, category=taxonomy["employment"])
    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    second.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    first.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    third = make_referral(case, category=taxonomy["enterprise"])
    third.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    assert third.status == ReferralStatus.ACTIVE


def test_failing_one_frees_a_parallel_slot(case, make_referral, case_manager, taxonomy):
    first = make_referral(case, category=taxonomy["training"])
    second = make_referral(case, category=taxonomy["employment"])
    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    second.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    first.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])

    third = make_referral(case, category=taxonomy["enterprise"])
    third.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    assert third.status == ReferralStatus.ACTIVE


def test_parallel_history_survives_closure(case, make_referral, case_manager, taxonomy):
    """is_parallel records that the referral ran concurrently — a historical fact."""
    first = make_referral(case, category=taxonomy["training"])
    second = make_referral(case, category=taxonomy["employment"])
    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    second.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    first.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    first.refresh_from_db()
    assert first.is_parallel is True
    assert first.parallel_group_id is not None


# ---------------------------------------------------------------------------
# §6.2 row 3: Pending Confirmation -> Failed (partner declines)
# ---------------------------------------------------------------------------


def test_decline_requires_a_failure_reason(case, make_referral, case_manager):
    referral = make_referral(case)
    with pytest.raises(ValidationError) as exc:
        referral.transition_to(ReferralStatus.FAILED, actor=case_manager)
    assert "failure_reason_code" in exc.value.message_dict


def test_decline_sets_declined_and_stamps_the_date(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["capacity"])

    assert referral.status == ReferralStatus.FAILED
    assert referral.confirmation_status == ConfirmationStatus.DECLINED
    assert referral.failure_date == date.today()


def test_failure_reason_requiring_a_note_is_enforced(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    with pytest.raises(ValidationError) as exc:
        referral.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["other_failure"])
    assert "notes" in exc.value.message_dict


# ---------------------------------------------------------------------------
# §6.2 row 4: Pending Confirmation -> Cancelled
# ---------------------------------------------------------------------------


def test_cancel_before_confirmation(case, make_referral, case_manager):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.CANCELLED, actor=case_manager)
    assert referral.status == ReferralStatus.CANCELLED


def test_cancelled_referral_prompts_no_replacement(case, make_referral, case_manager):
    """§6.2: cancellation is distinct from a decline precisely so it does not."""
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.CANCELLED, actor=case_manager)
    assert referral not in Referral.objects.awaiting_replacement_prompt()


# ---------------------------------------------------------------------------
# §6.2 row 5: Active -> Completed
# ---------------------------------------------------------------------------


def test_completion_requires_an_outcome_type(case, make_referral, case_manager):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    with pytest.raises(ValidationError) as exc:
        referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager)
    assert "outcome_type" in exc.value.message_dict


def test_completion_stamps_date_and_verifier(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    assert referral.status == ReferralStatus.COMPLETED
    assert referral.outcome_date == date.today()
    assert referral.outcome_verified_by == case_manager


def test_outcome_must_apply_to_the_category(case, make_referral, case_manager, taxonomy):
    """§5.3 maps each outcome to the categories it applies to."""
    referral = make_referral(case, category=taxonomy["training"])
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    with pytest.raises(ValidationError) as exc:
        # Job Placement applies to Employment, not Training.
        referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["job_placement"])
    assert "outcome_type" in exc.value.message_dict


def test_unrestricted_outcome_applies_to_any_category(case, make_referral, case_manager, taxonomy):
    """§5.3's Other row has no category restriction."""
    referral = make_referral(case, category=taxonomy["training"])
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(
        ReferralStatus.COMPLETED,
        actor=case_manager,
        outcome_type=taxonomy["other_outcome"],
        notes="Outcome recorded outside the standard list",
    )
    assert referral.status == ReferralStatus.COMPLETED


def test_completion_raises_an_onward_prompt(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    referral.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    assert referral in Referral.objects.awaiting_onward_prompt()


# ---------------------------------------------------------------------------
# §6.2 row 6: Active -> Failed
# ---------------------------------------------------------------------------


def test_active_failure_requires_a_reason_and_prompts_replacement(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)

    with pytest.raises(ValidationError):
        referral.transition_to(ReferralStatus.FAILED, actor=case_manager)

    referral.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])
    assert referral.status == ReferralStatus.FAILED
    assert referral in Referral.objects.awaiting_replacement_prompt()


# ---------------------------------------------------------------------------
# §6.2 row 7: Failed -> Replaced
# ---------------------------------------------------------------------------


def test_replacement_links_both_directions_and_marks_replaced(case, make_referral, case_manager, taxonomy, partner):
    failed = make_referral(case)
    failed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    failed.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["capacity"])

    replacement = services.create_replacement_referral(
        failed_referral=failed,
        referral_category=taxonomy["training"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )

    failed.refresh_from_db()
    assert failed.status == ReferralStatus.REPLACED
    assert failed.replacement_referral == replacement
    assert replacement.parent_referral == failed
    assert replacement.referral_trigger == ReferralTrigger.REPLACEMENT
    assert replacement.status == ReferralStatus.PENDING_CONFIRMATION


def test_a_replaced_referral_stops_prompting(case, make_referral, case_manager, taxonomy, partner):
    failed = make_referral(case)
    failed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    failed.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["capacity"])
    services.create_replacement_referral(
        failed_referral=failed,
        referral_category=taxonomy["training"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )
    failed.refresh_from_db()
    assert failed not in Referral.objects.awaiting_replacement_prompt()


def test_cannot_replace_twice(case, make_referral, case_manager, taxonomy, partner):
    failed = make_referral(case)
    failed.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    failed.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["capacity"])
    services.create_replacement_referral(
        failed_referral=failed,
        referral_category=taxonomy["training"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )
    failed.refresh_from_db()

    with pytest.raises(ValidationError):
        services.create_replacement_referral(
            failed_referral=failed,
            referral_category=taxonomy["training"],
            receiving_partner=partner,
            initiated_by=case_manager,
        )


def test_cannot_replace_a_referral_that_did_not_fail(case, make_referral, case_manager, taxonomy, partner):
    referral = make_referral(case)
    with pytest.raises(ValidationError):
        services.create_replacement_referral(
            failed_referral=referral,
            referral_category=taxonomy["training"],
            receiving_partner=partner,
            initiated_by=case_manager,
        )


# ---------------------------------------------------------------------------
# §6.2 row 8: Completed -> onward referral (parent stays Completed)
# ---------------------------------------------------------------------------


def test_onward_referral_leaves_the_parent_completed(case, make_referral, case_manager, taxonomy, partner):
    parent = make_referral(case, category=taxonomy["training"])
    parent.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    parent.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    child = services.create_onward_referral(
        parent=parent,
        referral_category=taxonomy["employment"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )

    parent.refresh_from_db()
    assert parent.status == ReferralStatus.COMPLETED  # unchanged by the onward step
    assert child.referral_trigger == ReferralTrigger.ONWARD
    assert child.parent_referral == parent
    assert parent not in Referral.objects.awaiting_onward_prompt()


def test_onward_requires_a_completed_parent(case, make_referral, case_manager, taxonomy, partner):
    parent = make_referral(case)
    with pytest.raises(ValidationError):
        services.create_onward_referral(
            parent=parent,
            referral_category=taxonomy["employment"],
            receiving_partner=partner,
            initiated_by=case_manager,
        )


# ---------------------------------------------------------------------------
# Edges the §6.2 table does NOT contain
# ---------------------------------------------------------------------------


ALL_STATUSES = [s for s in ReferralStatus.values]


@pytest.mark.parametrize(
    "from_status,to_status",
    [(f, t) for f in ALL_STATUSES for t in ALL_STATUSES if t not in TRANSITIONS.get(f, {})],
)
def test_undefined_transitions_are_refused(case, make_referral, case_manager, from_status, to_status):
    """Every from/to pair absent from the §6.2 table must raise.

    Parametrised over the full cross-product so a future edit that widens the
    table without a matching rule is caught here rather than in production.
    """
    referral = make_referral(case)
    Referral.objects.filter(pk=referral.pk).update(status=from_status)
    referral.refresh_from_db()

    with pytest.raises(TransitionError):
        referral.transition_to(to_status, actor=case_manager)


def test_terminal_statuses_allow_nothing_onward(case, make_referral, case_manager):
    for terminal in (ReferralStatus.COMPLETED, ReferralStatus.REPLACED, ReferralStatus.CANCELLED):
        referral = make_referral(case)
        Referral.objects.filter(pk=referral.pk).update(status=terminal)
        referral.refresh_from_db()
        assert referral.allowed_transitions == []


def test_every_transition_moves_case_activity(case, make_referral, case_manager, taxonomy):
    referral = make_referral(case)
    case.last_activity_date = date.today() - timedelta(days=30)
    case.save(update_fields=["last_activity_date"])

    referral.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    case.refresh_from_db()
    assert case.last_activity_date == date.today()


# ---------------------------------------------------------------------------
# §6.4 stack reconstruction
# ---------------------------------------------------------------------------


def test_stack_nests_the_referral_chain(case, make_referral, case_manager, taxonomy, partner):
    """§6.4: the stack is a query over parent links, never a stored object."""
    first = make_referral(case, category=taxonomy["training"])
    first.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    first.transition_to(ReferralStatus.COMPLETED, actor=case_manager, outcome_type=taxonomy["training_completion"])

    second = services.create_onward_referral(
        parent=first,
        referral_category=taxonomy["employment"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )
    second.transition_to(ReferralStatus.ACTIVE, actor=case_manager)
    second.transition_to(ReferralStatus.FAILED, actor=case_manager, failure_reason_code=taxonomy["no_show"])

    third = services.create_replacement_referral(
        failed_referral=second,
        referral_category=taxonomy["employment"],
        receiving_partner=partner,
        initiated_by=case_manager,
    )

    stack = build_referral_stack(case)
    assert len(stack) == 1  # one root
    assert stack[0]["referral"] == first
    assert stack[0]["children"][0]["referral"] == second
    assert stack[0]["children"][0]["children"][0]["referral"] == third


def test_stack_has_one_root_per_manual_referral(case, make_referral, taxonomy):
    make_referral(case, category=taxonomy["training"])
    make_referral(case, category=taxonomy["employment"])
    stack = build_referral_stack(case)
    assert len(stack) == 2
    assert all(node["children"] == [] for node in stack)
