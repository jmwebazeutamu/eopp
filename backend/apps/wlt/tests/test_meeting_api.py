"""The weekly meeting, over HTTP — the operational act of the whole module.

Savings are collected, attendance is taken and the cash is counted at a meeting.
Everything in `services/ledger.py` was tested from stage 1; what was missing was
a route a screen could be built on, and in particular a way to *read* what a
meeting already holds. `record_savings` appends and there is no update path, so
a screen that could not see what was posted would double a woman's contribution
on a retry — and correcting that needs a reversal with a reason.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.wlt.models import AttendanceStatus, EntryType, LedgerEntry, MeetingStatus
from apps.wlt.services import formation as formation_service
from apps.wlt.services import ledger as ledger_service

pytestmark = pytest.mark.django_db

MEETINGS = "/api/v1/wlt/meetings/"


@pytest.fixture
def open_meeting(wlt_group, facilitator):
    return ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)


def _register(client, meeting):
    response = client.get(f"{MEETINGS}{meeting.pk}/register/")
    assert response.status_code == 200
    return response.data


class TestTheRegister:
    def test_it_lists_the_roster_with_nothing_recorded_yet(self, as_user, facilitator, open_meeting, wlt_members):
        data = _register(as_user(facilitator), open_meeting)

        assert len(data["members"]) == len(wlt_members)
        first = data["members"][0]
        assert first["attendance"] is None
        # None, not "0": a woman who saved nothing is a compliance finding, and
        # a woman not yet asked is a blank row. They must not render alike.
        assert first["saved_etb"] is None

    def test_it_shows_what_has_already_been_posted(self, as_user, facilitator, open_meeting, wlt_members):
        """The read that stops a retry doubling her contribution."""
        client = as_user(facilitator)
        client.post(
            f"{MEETINGS}{open_meeting.pk}/savings/",
            {"person": str(wlt_members[0].pk), "amount_etb": "20"},
            format="json",
        )

        data = _register(client, open_meeting)
        row = next(m for m in data["members"] if m["person"] == str(wlt_members[0].pk))
        assert Decimal(row["saved_etb"]) == Decimal("20")

    def test_it_shows_attendance_already_taken(self, as_user, facilitator, open_meeting, wlt_members):
        client = as_user(facilitator)
        client.post(
            f"{MEETINGS}{open_meeting.pk}/attendance/",
            {"rows": [{"person": str(wlt_members[0].pk), "status": AttendanceStatus.PRESENT}]},
            format="json",
        )

        data = _register(client, open_meeting)
        row = next(m for m in data["members"] if m["person"] == str(wlt_members[0].pk))
        assert row["attendance"] == AttendanceStatus.PRESENT

    def test_the_roster_is_the_one_in_force_on_the_meeting_date(
        self, as_user, facilitator, wlt_group, wlt_members
    ):
        """Membership is a dated range, so a meeting is registered against the
        roster as it stood *then*. A woman who left last week was in the group
        when last month's meeting was held, and her attendance is part of that
        meeting's denominator."""
        from apps.wlt.models import ExitReason, GroupMembership

        old_meeting = ledger_service.open_meeting(
            wlt_group, held_on=date.today() - timedelta(days=30), recorded_by=facilitator
        )
        membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0], exited_on__isnull=True)
        formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date.today() - timedelta(days=2))

        data = _register(as_user(facilitator), old_meeting)
        assert str(wlt_members[0].pk) in {m["person"] for m in data["members"]}

    def test_it_carries_the_contribution_and_the_expected_cash(self, as_user, facilitator, open_meeting):
        data = _register(as_user(facilitator), open_meeting)
        assert data["contribution_etb"] is not None
        assert "expected_cash_etb" in data
        assert data["group_name"]

    def test_it_is_refused_across_the_module_boundary(self, as_user, case_manager, open_meeting):
        assert as_user(case_manager).get(f"{MEETINGS}{open_meeting.pk}/register/").status_code == 403


class TestClosingTheMeeting:
    def test_a_balanced_till_closes(self, as_user, facilitator, open_meeting, wlt_members):
        client = as_user(facilitator)
        for person in wlt_members[:3]:
            client.post(
                f"{MEETINGS}{open_meeting.pk}/savings/", {"person": str(person.pk), "amount_etb": "20"}, format="json"
            )

        expected = _register(client, open_meeting)["expected_cash_etb"]
        closed = client.post(
            f"{MEETINGS}{open_meeting.pk}/close/", {"counted_cash_etb": str(expected)}, format="json"
        )

        assert closed.status_code == 200
        open_meeting.refresh_from_db()
        assert open_meeting.status == MeetingStatus.CLOSED

    def test_an_unbalanced_till_is_refused_and_says_by_how_much(
        self, as_user, facilitator, open_meeting, wlt_members
    ):
        """The rule everything else depends on. The message is the product —
        a facilitator has to know which way and by how much."""
        client = as_user(facilitator)
        client.post(
            f"{MEETINGS}{open_meeting.pk}/savings/",
            {"person": str(wlt_members[0].pk), "amount_etb": "20"},
            format="json",
        )

        refused = client.post(f"{MEETINGS}{open_meeting.pk}/close/", {"counted_cash_etb": "15"}, format="json")

        assert refused.status_code == 400
        assert "does not balance" in str(refused.data)
        open_meeting.refresh_from_db()
        assert open_meeting.status == MeetingStatus.OPEN

    def test_a_failed_reconciliation_leaves_a_risk_flag_behind(
        self, as_user, facilitator, open_meeting, wlt_members, wlt_group
    ):
        """It outlives the refusal on purpose: a till that did not balance is
        the earliest visible sign of a problem the indicators will not show for
        weeks, and a refusal that left no trace would hide it."""
        from apps.wlt.models import RiskFlag, RiskReason

        client = as_user(facilitator)
        client.post(
            f"{MEETINGS}{open_meeting.pk}/savings/",
            {"person": str(wlt_members[0].pk), "amount_etb": "20"},
            format="json",
        )
        client.post(f"{MEETINGS}{open_meeting.pk}/close/", {"counted_cash_etb": "15"}, format="json")

        assert RiskFlag.objects.open().for_group(wlt_group).filter(reason_code=RiskReason.UNBALANCED_TILL).exists()

    def test_nothing_can_be_posted_to_a_closed_meeting(self, as_user, facilitator, open_meeting, wlt_members):
        client = as_user(facilitator)
        expected = _register(client, open_meeting)["expected_cash_etb"]
        client.post(f"{MEETINGS}{open_meeting.pk}/close/", {"counted_cash_etb": str(expected)}, format="json")

        late = client.post(
            f"{MEETINGS}{open_meeting.pk}/savings/",
            {"person": str(wlt_members[0].pk), "amount_etb": "20"},
            format="json",
        )
        assert late.status_code == 400

    def test_savings_posted_twice_are_visible_rather_than_silent(
        self, as_user, facilitator, open_meeting, wlt_members
    ):
        """The hazard the register exists to make visible.

        The ledger appends and has no update path, so a retried request doubles
        her contribution. The service does not block it — a genuine catch-up
        payment is a real thing — so the register has to *show* the total, which
        is what lets a screen refuse the second press.
        """
        client = as_user(facilitator)
        for _ in range(2):
            client.post(
                f"{MEETINGS}{open_meeting.pk}/savings/",
                {"person": str(wlt_members[0].pk), "amount_etb": "20"},
                format="json",
            )

        row = next(
            m for m in _register(client, open_meeting)["members"] if m["person"] == str(wlt_members[0].pk)
        )
        assert Decimal(row["saved_etb"]) == Decimal("40")
        assert LedgerEntry.objects.filter(meeting=open_meeting, entry_type=EntryType.SAVINGS).count() == 2


def test_two_meetings_on_one_date_sort_by_number(as_user, facilitator, wlt_group):
    """Defect P5a: 31 listed above 32, both held the same day.

    Two meetings on one date is ordinary — a catch-up beside the regular one —
    and a date-only sort leaves their order to the database.
    """
    first = ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)
    ledger_service.close_meeting(first, counted_cash_etb=ledger_service.expected_cash(first), actor=facilitator)
    second = ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)

    listed = as_user(facilitator).get(MEETINGS, {"group": str(wlt_group.pk), "page_size": 100})
    rows = listed.data["results"] if isinstance(listed.data, dict) else listed.data
    same_day = [row for row in rows if row["held_on"] == date.today().isoformat()]

    assert [row["meeting_no"] for row in same_day] == sorted(
        (row["meeting_no"] for row in same_day), reverse=True
    )
    assert same_day[0]["meeting_no"] == second.meeting_no


# ---------------------------------------------------------------------------
# Lending — the money out, and the money back
# ---------------------------------------------------------------------------


def _lendable(group, facilitator):
    """Ten closed savings meetings, which is what the service requires."""
    from apps.wlt.models import MeetingStatus

    while group.meetings.filter(status=MeetingStatus.CLOSED).count() < 10:
        meeting = ledger_service.open_meeting(group, held_on=date.today(), recorded_by=facilitator)
        ledger_service.close_meeting(
            meeting, counted_cash_etb=ledger_service.expected_cash(meeting), actor=facilitator
        )
    return ledger_service.open_meeting(group, held_on=date.today(), recorded_by=facilitator)


class TestLending:
    def test_a_loan_is_disbursed_at_a_meeting(self, as_user, facilitator, wlt_group, wlt_members):
        """At a meeting because that is where the money is: the cash leaves the
        box in the room, and `expected_cash` counts it."""
        meeting = _lendable(wlt_group, facilitator)
        client = as_user(facilitator)

        before = client.get(f"{MEETINGS}{meeting.pk}/register/").data["expected_cash_etb"]
        issued = client.post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "100",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        )

        assert issued.status_code == 201
        assert issued.data["borrower_name"] == wlt_members[0].full_name
        after = client.get(f"{MEETINGS}{meeting.pk}/register/").data["expected_cash_etb"]
        assert Decimal(str(after)) == Decimal(str(before)) - Decimal("100")

    def test_lending_before_the_tenth_meeting_is_refused_and_says_so(
        self, as_user, facilitator, wlt_draft, wlt_members
    ):
        """The message is the answer, so it is passed through rather than
        replaced with a generic failure.

        `wlt_draft`, not `wlt_group`: the active fixture is well past its tenth
        meeting, so it could never show the refusal.
        """
        meeting = ledger_service.open_meeting(wlt_draft, held_on=date.today(), recorded_by=facilitator)

        refused = as_user(facilitator).post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "100",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        )

        assert refused.status_code == 400
        assert "savings meetings" in str(refused.data)

    def test_more_than_the_box_holds_is_refused(self, as_user, facilitator, wlt_group, wlt_members):
        meeting = _lendable(wlt_group, facilitator)
        refused = as_user(facilitator).post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "9999999",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        )
        assert refused.status_code == 400

    def test_an_outstanding_loan_appears_on_the_register(self, as_user, facilitator, wlt_group, wlt_members):
        meeting = _lendable(wlt_group, facilitator)
        client = as_user(facilitator)
        client.post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "100",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        )

        loans = client.get(f"{MEETINGS}{meeting.pk}/register/").data["loans"]
        assert len(loans) == 1
        assert Decimal(loans[0]["outstanding_principal_etb"]) == Decimal("100")

    def test_a_repayment_splits_principal_from_charge(self, as_user, facilitator, wlt_group, wlt_members):
        """PAR30 is a statement about principal alone, and a repayment recorded
        as one number cannot be split afterwards."""
        meeting = _lendable(wlt_group, facilitator)
        client = as_user(facilitator)
        loan = client.post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "100",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        ).data

        repaid = client.post(
            f"{MEETINGS}{meeting.pk}/loans/{loan['id']}/repay/",
            {"principal_etb": "40", "charge_etb": "5"},
            format="json",
        )

        assert repaid.status_code == 200
        assert Decimal(repaid.data["outstanding_principal_etb"]) == Decimal("60")

    def test_repaying_more_principal_than_is_owed_is_refused(self, as_user, facilitator, wlt_group, wlt_members):
        meeting = _lendable(wlt_group, facilitator)
        client = as_user(facilitator)
        loan = client.post(
            f"{MEETINGS}{meeting.pk}/loans/",
            {
                "person": str(wlt_members[0].pk),
                "principal_etb": "100",
                "purpose": "IGA",
                "due_on": (date.today() + timedelta(days=90)).isoformat(),
            },
            format="json",
        ).data

        refused = client.post(
            f"{MEETINGS}{meeting.pk}/loans/{loan['id']}/repay/",
            {"principal_etb": "500"},
            format="json",
        )
        assert refused.status_code == 400

    def test_a_loan_from_another_group_cannot_be_repaid_here(
        self, as_user, facilitator, other_facilitator, wlt_group, wlt_members, wlt_locations
    ):
        """The loan is looked up through the meeting's group rather than trusted
        from the URL."""
        meeting = _lendable(wlt_group, facilitator)
        theirs = formation_service.open_draft(
            name="Another SHG", kebele=wlt_locations["other_kebele"], facilitator=other_facilitator
        )
        from apps.wlt.models import Loan, LoanPurpose, LoanStatus

        from apps.wlt.models import ServiceChargeBasis

        stranger = Loan.objects.create(
            group=theirs,
            person=wlt_members[1],
            principal_etb=Decimal("50"),
            charge_basis=ServiceChargeBasis.FLAT_PER_LOAN,
            charge_rate=Decimal("5"),
            purpose=LoanPurpose.IGA,
            disbursed_on=date.today(),
            due_on=date.today() + timedelta(days=30),
            status=LoanStatus.DISBURSED,
        )

        response = as_user(facilitator).post(
            f"{MEETINGS}{meeting.pk}/loans/{stranger.pk}/repay/", {"principal_etb": "10"}, format="json"
        )
        assert response.status_code == 404

    def test_lending_is_refused_across_the_module_boundary(self, as_user, case_manager, wlt_group, facilitator):
        meeting = ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)
        assert as_user(case_manager).post(f"{MEETINGS}{meeting.pk}/loans/", {}, format="json").status_code == 403
