"""The handoff's SQL assertions A1 to A32, mirrored in Python.

`django/MODELS.md` asks for exactly this: "Mirror the SQL assertions in the
Python suite so the rules are enforced at both layers." The bundle's own suite
runs against a scratch database built from `sql/000_core_stubs.sql`, which models
a core platform this one is not — so the assertions are re-expressed against the
real models rather than run as SQL.

Each test names the assertion it carries. Where the number here differs from the
bundle's, the difference is stated in the test and it is deliberate.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.wlt.models import (
    CLA,
    ChildType,
    Delegate,
    EntryType,
    ExitReason,
    Federation,
    GroupMembership,
    GroupStatus,
    LedgerEntry,
    Loan,
    LoanPurpose,
    LoanStatus,
    MeetingCadence,
    OfficeHolder,
    OfficeRole,
    ParentType,
    Phase,
    PhaseEvent,
    ServiceChargeBasis,
    StructuralMembership,
)
from apps.wlt.services import formation as formation_service
from apps.wlt.services import indicators as indicator_service
from apps.wlt.services import ledger as ledger_service

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# A1 to A3 — formation produced the expected shape
# ---------------------------------------------------------------------------


def test_a1_roster_is_twenty_members(wlt_group):
    assert wlt_group.current_members.count() == 20


def test_a2_twelve_meetings_closed(wlt_group):
    assert wlt_group.meetings.closed().count() == 12


def test_a3_savings_total_is_4800_birr(wlt_group):
    total = sum(entry.amount_etb for entry in wlt_group.ledger_entries.filter(entry_type=EntryType.SAVINGS))
    assert total == Decimal("4800.00")


# ---------------------------------------------------------------------------
# A4 to A6 — the till and the ledger
# ---------------------------------------------------------------------------


def test_a4_unbalanced_till_is_refused_and_names_the_difference(wlt_group, wlt_members, facilitator):
    """The error has to name the birr. A facilitator can find 200 birr; she
    cannot find "a validation error"."""
    meeting = ledger_service.open_meeting(wlt_group, held_on=date(2026, 4, 21), recorded_by=facilitator)
    ledger_service.record_savings(meeting, person=wlt_members[0], amount_etb=400, actor=facilitator)

    with pytest.raises(ValidationError) as caught:
        ledger_service.close_meeting(meeting, counted_cash_etb=Decimal("5000.00"), actor=facilitator)

    message = " ".join(caught.value.messages)
    assert "200" in message
    meeting.refresh_from_db()
    assert meeting.status == "OPEN"


def test_a4_a_failed_reconciliation_raises_an_at_risk_flag(wlt_group, wlt_members, facilitator):
    """And the flag survives the refusal — that is the record it happened."""
    from apps.wlt.models import RiskFlag, RiskReason

    meeting = ledger_service.open_meeting(wlt_group, held_on=date(2026, 4, 21), recorded_by=facilitator)
    ledger_service.record_savings(meeting, person=wlt_members[0], amount_etb=400, actor=facilitator)
    with pytest.raises(ValidationError):
        ledger_service.close_meeting(meeting, counted_cash_etb=Decimal("5000.00"))

    assert RiskFlag.objects.open().for_group(wlt_group).filter(reason_code=RiskReason.UNBALANCED_TILL).exists()


def test_a4_the_trigger_refuses_an_unbalanced_close_even_bypassing_the_service(wlt_group, facilitator):
    """The service is not the only writer. The admin and a data fix reach here too."""
    meeting = ledger_service.open_meeting(wlt_group, held_on=date(2026, 4, 21), recorded_by=facilitator)
    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            meeting.status = "CLOSED"
            meeting.closing_cash_etb = Decimal("9999.00")
            meeting.counted_cash_etb = Decimal("9999.00")
            meeting.save()
    assert "reconcile" in str(caught.value).lower()


def test_a5_the_ledger_refuses_an_update(wlt_group):
    entry = wlt_group.ledger_entries.first()
    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            entry.amount_etb = Decimal("999.00")
            entry.save()
    assert "append-only" in str(caught.value)


def test_a6_the_ledger_refuses_a_delete(wlt_group):
    entry = wlt_group.ledger_entries.first()
    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            entry.delete()
    assert "append-only" in str(caught.value)


def test_a5_a_correction_is_a_reversal_that_keeps_both_rows(wlt_group, facilitator):
    entry = wlt_group.ledger_entries.filter(entry_type=EntryType.SAVINGS).first()
    before = wlt_group.ledger_entries.count()

    reversal = ledger_service.reverse_entry(entry, reason="Recorded against the wrong member.", actor=facilitator)

    assert wlt_group.ledger_entries.count() == before + 1
    assert reversal.amount_etb == -entry.amount_etb
    assert reversal.reverses_id == entry.pk
    assert LedgerEntry.objects.filter(pk=entry.pk).exists()


def test_a5_a_reversal_without_a_reason_is_refused(wlt_group, facilitator):
    entry = wlt_group.ledger_entries.first()
    with pytest.raises(ValidationError):
        ledger_service.reverse_entry(entry, reason="   ", actor=facilitator)


# ---------------------------------------------------------------------------
# A7, A8 — one group per woman, one holder per office
# ---------------------------------------------------------------------------


def test_a7_a_woman_cannot_join_a_second_group(wlt_group, wlt_members, wlt_locations, facilitator):
    rival = formation_service.open_draft(name="Rival SHG", kebele=wlt_locations["kebele"], facilitator=facilitator)
    with pytest.raises(ValidationError) as caught:
        formation_service.add_member(rival, wlt_members[0])
    assert "Temsalet" in " ".join(caught.value.messages)


def test_a7_the_database_refuses_it_too(wlt_group, wlt_members, wlt_locations, facilitator):
    rival = formation_service.open_draft(name="Rival SHG", kebele=wlt_locations["kebele"], facilitator=facilitator)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            GroupMembership.objects.create(group=rival, person=wlt_members[0], joined_on=date(2026, 2, 1))


def test_a8_two_concurrent_treasurers_are_refused(wlt_group, wlt_members):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            OfficeHolder.objects.create(
                group=wlt_group, person=wlt_members[5], role=OfficeRole.TREASURER, from_date=date(2026, 3, 1)
            )


def test_a8_a_rotation_closes_the_old_term_rather_than_editing_it(wlt_group, wlt_members):
    sitting = wlt_group.office_holder_on(OfficeRole.TREASURER, date(2026, 2, 1))
    formation_service.elect_officer(
        wlt_group, person=wlt_members[5], role=OfficeRole.TREASURER, from_date=date(2026, 3, 1)
    )
    sitting.refresh_from_db()

    assert sitting.to_date == date(2026, 3, 1)
    # The question that gets asked is "who was treasurer on the day of that
    # disbursement", and it still has an answer.
    assert wlt_group.office_holder_on(OfficeRole.TREASURER, date(2026, 2, 1)).pk == sitting.pk
    assert wlt_group.office_holder_on(OfficeRole.TREASURER, date(2026, 3, 15)).person_id == wlt_members[5].pk


# ---------------------------------------------------------------------------
# A9 to A11 — loans, PAR30 and exit
# ---------------------------------------------------------------------------


@pytest.fixture
def loans(wlt_group, wlt_members, facilitator):
    """One loan repaid in full, one 30+ days overdue and untouched."""
    repaid = Loan.objects.create(
        group=wlt_group,
        person=wlt_members[4],
        cycle_batch=1,
        principal_etb=Decimal("400.00"),
        charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        charge_rate=Decimal("0.0500"),
        purpose=LoanPurpose.IGA,
        disbursed_on=date(2026, 3, 3),
        due_on=date(2026, 3, 31),
        status=LoanStatus.DISBURSED,
    )
    overdue = Loan.objects.create(
        group=wlt_group,
        person=wlt_members[5],
        cycle_batch=1,
        principal_etb=Decimal("600.00"),
        charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        charge_rate=Decimal("0.0500"),
        purpose=LoanPurpose.EMERGENCY,
        disbursed_on=date(2026, 2, 3),
        due_on=date(2026, 3, 3),
        status=LoanStatus.DISBURSED,
    )
    ledger_service.record_repayment(repaid, principal_etb=400, charge_etb=20, meeting=None, paid_on=date(2026, 3, 24))
    return {"repaid": repaid, "overdue": overdue}


def test_a9_outstanding_principal_is_600_after_one_loan_is_repaid(wlt_group, loans):
    figures = indicator_service.compute(wlt_group, as_of=date(2026, 4, 30))
    assert figures.loans_outstanding_etb == Decimal("600.00")


def test_a10_par30_is_100_percent_when_the_only_outstanding_loan_is_overdue(wlt_group, loans):
    figures = indicator_service.compute(wlt_group, as_of=date(2026, 4, 30))
    assert figures.par30_pct == Decimal("100.0")


def test_par30_is_zero_before_the_default_window_has_passed(wlt_group, loans):
    """A loan one day past due is delinquent, not at risk. PAR30 is a 30-day
    measure and the two must not be conflated."""
    figures = indicator_service.compute(wlt_group, as_of=date(2026, 3, 10))
    assert figures.par30_pct == Decimal("0.0")
    assert figures.loans_delinquent == 1


def test_a11_a_member_with_an_outstanding_loan_cannot_exit(wlt_group, loans, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[5])
    with pytest.raises(ValidationError) as caught:
        formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date(2026, 4, 1))
    assert "600" in " ".join(caught.value.messages)


def test_a11_the_database_refuses_it_too(wlt_group, loans, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[5])
    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            membership.exited_on = date(2026, 4, 1)
            membership.exit_reason = ExitReason.MOVED
            membership.save()
    assert "outstanding" in str(caught.value).lower()


# ---------------------------------------------------------------------------
# A12 to A14 — the roster is historical
# ---------------------------------------------------------------------------


def test_a12_a_clean_exit_drops_the_roster_to_nineteen(wlt_group, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[19])
    formation_service.exit_member(membership, reason=ExitReason.MARRIED_OUT, on_date=date(2026, 4, 20))
    assert wlt_group.current_members.count() == 19


def test_a13_roster_on_returns_twenty_for_a_date_before_the_exit(wlt_group, wlt_members):
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[19])
    formation_service.exit_member(membership, reason=ExitReason.MARRIED_OUT, on_date=date(2026, 4, 20))
    assert wlt_group.roster_on(date(2026, 2, 10)).count() == 20


def test_a14_attendance_is_not_distorted_by_a_later_exit(wlt_group, wlt_members):
    """The denominator is the roster as it stood at each meeting. A woman who
    leaves in April must not make February look better."""
    membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[19])
    formation_service.exit_member(membership, reason=ExitReason.MARRIED_OUT, on_date=date(2026, 4, 20))

    figures = indicator_service.compute(wlt_group, as_of=date(2026, 4, 25))
    assert figures.attendance_pct == Decimal("100.0")
    assert figures.attendances_expected == 240  # 12 meetings x 20 on the roster then


def test_a_late_joiner_does_not_make_earlier_months_look_worse(wlt_group, make_wlt_member, wlt_members, facilitator):
    joiner = make_wlt_member("Late Joiner")
    # After the twelfth meeting (24 March), so she was on the roster for none
    # of them. The last meeting is deliberately close: a join dated *before* a
    # meeting does count for it, which is the same dated-range rule read the
    # other way.
    formation_service.add_member(wlt_group, joiner, on_date=date(2026, 3, 25))

    figures = indicator_service.compute(wlt_group, as_of=date(2026, 3, 26))
    # She was on the roster for none of the twelve meetings, so the denominator
    # is unchanged and attendance stays 100%.
    assert figures.attendances_expected == 240
    assert figures.attendance_pct == Decimal("100.0")


# ---------------------------------------------------------------------------
# A24 to A28 — governance and versioning
# ---------------------------------------------------------------------------


def test_a24_the_submitter_cannot_be_the_approver(wlt_group, facilitator):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PhaseEvent.objects.create(
                group=wlt_group,
                from_phase=Phase.P1,
                to_phase=Phase.P2,
                submitted_by=facilitator,
                decided_by=facilitator,
                gate_snapshot={},
            )


def test_a25_a_decision_stores_its_whole_evidence_snapshot(wlt_group, facilitator, woreda_officer):
    from django.utils import timezone

    event = PhaseEvent.objects.create(
        group=wlt_group,
        from_phase=Phase.P1,
        to_phase=Phase.P2,
        submitted_by=facilitator,
        decided_by=woreda_officer,
        decided_at=timezone.now(),
        gate_snapshot={"conditions": [{"code": "attendance", "threshold": 80, "actual": "100.0", "met": True}]},
    )
    condition = event.gate_snapshot["conditions"][0]
    # Threshold *and* actual. A snapshot of `passed` alone cannot answer "on what
    # numbers" two years later, which is the only question that gets asked.
    assert condition["threshold"] == 80
    assert condition["actual"] == "100.0"


def test_a26_a_decided_phase_event_cannot_be_rewritten(wlt_group, facilitator, woreda_officer):
    from django.utils import timezone

    event = PhaseEvent.objects.create(
        group=wlt_group,
        from_phase=Phase.P1,
        to_phase=Phase.P2,
        submitted_by=facilitator,
        decided_by=woreda_officer,
        decided_at=timezone.now(),
        gate_snapshot={"attendance_pct": "100.0"},
    )
    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            event.gate_snapshot = {}
            event.save()
    assert "cannot be rewritten" in str(caught.value)


def test_a26_an_undecided_submission_can_still_change(wlt_group, facilitator):
    """A submission is a request, not a record. It locks when it is decided.

    This is where the implementation departs from `sql/002`, which blocks every
    UPDATE on the table: with that trigger a submission could never be approved,
    because approving one writes the decision onto the row.
    """
    pending = PhaseEvent.objects.create(
        group=wlt_group,
        from_phase=Phase.P1,
        to_phase=Phase.P2,
        submitted_by=facilitator,
        gate_snapshot={},
    )
    pending.override_reason = "Woreda asked for it in writing."
    pending.save()  # no exception


def test_a27_only_one_bylaw_version_is_in_force(wlt_group):
    from apps.wlt.models import BylawVersion

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BylawVersion.objects.create(
                group=wlt_group,
                version_no=2,
                effective_from=date(2026, 6, 1),
                meeting_cadence=MeetingCadence.WEEKLY,
                contribution_etb=30,
            )


def test_a28_superseding_keeps_the_old_version_for_historical_compliance(wlt_group, facilitator):
    v1 = wlt_group.current_bylaw
    formation_service.record_bylaws(
        wlt_group,
        effective_from=date(2026, 6, 1),
        recorded_by=facilitator,
        meeting_cadence=MeetingCadence.WEEKLY,
        contribution_etb=30,
        service_charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
        service_charge_rate="0.0500",
    )
    wlt_group.refresh_from_db()

    assert wlt_group.current_bylaw.contribution_etb == Decimal("30.00")
    assert wlt_group.current_bylaw.version_no == 2
    # And months 1 to 7 still measure against ETB 20.
    assert wlt_group.bylaw_on(date(2026, 3, 1)).pk == v1.pk
    assert wlt_group.bylaw_on(date(2026, 3, 1)).contribution_etb == Decimal("20.00")


def test_bylaws_cannot_be_recorded_without_a_service_charge_basis(wlt_group, facilitator):
    """Open question Q4. A flat 5% per loan and 5% per month on a three-month
    loan differ by a factor of three, so the system must not pick one."""
    with pytest.raises(ValidationError):
        formation_service.record_bylaws(
            wlt_group,
            effective_from=date(2026, 7, 1),
            meeting_cadence=MeetingCadence.WEEKLY,
            contribution_etb=30,
        )


# ---------------------------------------------------------------------------
# A21 to A23 — the structural hierarchy
# ---------------------------------------------------------------------------


@pytest.fixture
def cla(db, wlt_locations):
    return CLA.objects.create(name="Dessie Zuria CLA", kebele=wlt_locations["kebele"], formed_on=date(2027, 2, 1))


def test_a21_a_group_belongs_to_at_most_one_cla(wlt_group, cla, wlt_locations):
    StructuralMembership.objects.create(
        parent_type=ParentType.CLA,
        parent_id=cla.pk,
        child_type=ChildType.GROUP,
        child_id=wlt_group.pk,
        joined_on=date(2027, 2, 1),
    )
    second = CLA.objects.create(name="Second CLA", kebele=wlt_locations["kebele"], formed_on=date(2027, 3, 1))

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StructuralMembership.objects.create(
                parent_type=ParentType.CLA,
                parent_id=second.pk,
                child_type=ChildType.GROUP,
                child_id=wlt_group.pk,
                joined_on=date(2027, 3, 1),
            )


def test_a22_a_federation_contains_clas_and_never_groups(wlt_group, wlt_locations):
    federation = Federation.objects.create(
        name="Dessie Zuria Federation", woreda=wlt_locations["woreda"], formed_on=date(2028, 1, 1)
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            StructuralMembership.objects.create(
                parent_type=ParentType.FEDERATION,
                parent_id=federation.pk,
                child_type=ChildType.GROUP,
                child_id=wlt_group.pk,
                joined_on=date(2028, 1, 1),
            )


def test_a23_a_group_cannot_seat_three_delegates_in_one_cla(wlt_group, cla, wlt_members):
    for person in wlt_members[:2]:
        Delegate.objects.create(cla=cla, group=wlt_group, person=person, from_date=date(2027, 2, 1))

    with pytest.raises(Exception) as caught:
        with transaction.atomic():
            Delegate.objects.create(cla=cla, group=wlt_group, person=wlt_members[2], from_date=date(2027, 2, 1))
    assert "2 active delegates" in str(caught.value)


# ---------------------------------------------------------------------------
# A29 to A32 — the reporting layer
# ---------------------------------------------------------------------------


def test_a29_cla_readiness_says_how_many_more_groups_a_kebele_needs(wlt_group, wlt_locations):
    """The screen that drives facilitator behaviour more than any other: "seven
    more groups at P2 and this kebele can form a CLA"."""
    from apps.wlt import reporting
    from apps.wlt.models import Group

    Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2, status=GroupStatus.ACTIVE)
    reporting.refresh()

    rows = {row["kebele_id"]: row for row in reporting.cla_readiness()}
    row = rows[wlt_locations["kebele"].pk]
    assert row["eligible_groups"] == 1
    assert row["threshold"] == 8
    assert row["groups_short"] == 7


def test_a30_a_refused_endorsement_is_visible_in_formation_attrition(db, wlt_policy, wlt_locations, facilitator):
    """A kebele that produced no groups is programme learning, and it is
    invisible if only successes are stored."""
    from apps.wlt import reporting
    from apps.wlt.models import MobilisationEvent

    MobilisationEvent.objects.create(
        kebele=wlt_locations["kebele"],
        held_on=date(2026, 1, 5),
        facilitator=facilitator,
        endorsement_obtained=False,
        endorsement_note="Elders asked for more consultation.",
    )
    reporting.refresh()

    rows = {row["kebele_id"]: row for row in reporting.formation_attrition()}
    assert rows[wlt_locations["kebele"].pk]["endorsement_refused"] == 1


def test_a31_the_allocation_is_policy_data_and_editable_without_a_deployment(db, wlt_policy):
    from apps.wlt import reporting
    from apps.wlt.models import EnrolmentAllocation

    reporting.refresh()
    rows = {row["region"]: row for row in reporting.enrolment_vs_allocation()}
    assert rows["Amhara"]["target_members"] == 1200

    allocation = EnrolmentAllocation.objects.get(location__code="ET-AM")
    allocation.target_members = 1400
    allocation.save()
    reporting.refresh()

    rows = {row["region"]: row for row in reporting.enrolment_vs_allocation()}
    assert rows["Amhara"]["target_members"] == 1400


def test_a32_the_linkage_funnel_picks_up_a_savings_account(wlt_group, make_partner, facilitator):
    from apps.wlt import reporting
    from apps.wlt.models import Group
    from apps.wlt.services import linkage as linkage_service

    Group.objects.filter(pk=wlt_group.pk).update(current_phase=Phase.P2)
    wlt_group.refresh_from_db()
    provider = make_partner(name="Amhara Rural Bank", woredas=["Dessie Zuria"])

    linkage_service.propose(linkage_type="savings_account", subject=wlt_group, provider=provider, actor=facilitator)
    reporting.refresh()

    rows = [row for row in reporting.linkage_funnel() if row["type_code"] == "savings_account"]
    assert len(rows) == 1
    assert rows[0]["n"] == 1
