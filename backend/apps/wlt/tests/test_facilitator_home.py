"""Tier 1 of the WLT dashboard handoff — the facilitator's home screen.

What is worth asserting is the handoff's own acceptance criteria, not the shape
of the payload: every count carries the list behind it, a facilitator sees her
own kebeles and nobody else's, and the two delinquency classes never collapse
into one number.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.wlt.models import Group, GroupStatus, Meeting, MeetingStatus, RiskFlag
from apps.wlt.services import facilitator as service

pytestmark = pytest.mark.django_db


def cards(payload):
    return {card["id"]: card for card in payload["cards"]}


def test_the_screen_is_one_request_carrying_all_six_cards(facilitator, wlt_group):
    payload = service.home(facilitator)
    assert sorted(cards(payload)) == ["FC-1", "FC-2", "FC-3", "FC-4", "FC-5", "FC-6"]


def test_every_count_carries_the_list_behind_it(facilitator, wlt_group):
    """The handoff deletes any figure that cannot be tapped to produce the
    named groups, meetings or members behind it."""
    payload = service.home(facilitator)
    for card in payload["cards"]:
        if card["total"]:
            assert card["rows"], f"{card['id']} reported a count with no list"


def test_the_screen_says_how_stale_it_is(facilitator, wlt_group):
    """A dashboard that does not say how stale it is invites the reader to
    assume it is live — and this one is read where it will not be."""
    payload = service.home(facilitator)
    assert "last_sync_at" in payload
    assert payload["as_of"]


def test_a_facilitator_sees_her_own_groups_and_no_others(facilitator, other_facilitator, wlt_group):
    """Criterion 3, tested in both directions."""
    mine = service.home(facilitator)
    theirs = service.home(other_facilitator)

    assert mine["groups_in_scope"] >= 1
    assert theirs["groups_in_scope"] == 0
    assert all(card["total"] == 0 for card in theirs["cards"])


def test_an_overdue_meeting_leads_the_landing_card(facilitator, wlt_group):
    """Sorted by how late, which is the order the work should be done in — not
    the order the meetings were created."""
    today = timezone.localdate()
    Meeting.objects.filter(group=wlt_group).update(status=MeetingStatus.CLOSED)
    early = Meeting.objects.create(
        group=wlt_group, meeting_no=901, scheduled_for=today - timedelta(days=20), status=MeetingStatus.OPEN
    )
    Meeting.objects.create(
        group=wlt_group, meeting_no=902, scheduled_for=today - timedelta(days=2), status=MeetingStatus.OPEN
    )

    card = cards(service.home(facilitator))["FC-1"]

    assert card["total"] == 2
    assert card["rows"][0]["meeting"] == str(early.pk)
    assert card["rows"][0]["days_late"] == 20


def test_the_till_card_says_the_state_cannot_exist_rather_than_reporting_zero(facilitator, wlt_group):
    """The handoff asks for closed meetings whose count disagrees with the book.
    A meeting cannot close in that state — `wlt_meeting_close_requires_
    reconciliation` refuses the update — so a zero here would read as "every
    till balanced", which is exactly what a supervision mission would want
    evidenced and is not what the data says.
    """
    card = cards(service.home(facilitator))["FC-2"]

    assert card["available"] is False
    assert card["total"] == 0
    assert "cannot be closed" in card["note"]


def test_the_database_still_refuses_an_unbalanced_close(wlt_group):
    """The invariant this card defers to, asserted here so that relaxing it
    later is a deliberate act rather than a silent one."""
    from django.db import DatabaseError, transaction

    meeting = Meeting.objects.filter(group=wlt_group, status=MeetingStatus.CLOSED).first()
    # `RAISE EXCEPTION` from PL/pgSQL, so it arrives as a database error rather
    # than as an IntegrityError — the trigger is a statement, not a constraint.
    with pytest.raises(DatabaseError, match="till does not reconcile"):
        with transaction.atomic():
            Meeting.objects.filter(pk=meeting.pk).update(counted_cash_etb=160)


def test_delinquent_and_default_are_never_one_overdue_count(facilitator, wlt_group):
    """One is a conversation at the next meeting; the other is a PAR30 event
    that blocks a gate. A single number loses the only thing that decides what
    the facilitator does."""
    card = cards(service.home(facilitator))["FC-3"]

    classes = [block["class"] for block in card["rows"]]
    assert classes == ["DELINQUENT", "DEFAULT"]
    # Each block names the threshold it was measured against.
    assert all(block["threshold_days"] for block in card["rows"])


def test_a_risk_flag_renders_its_reason_not_a_count(facilitator, wlt_group):
    """Six reason codes exist and they are not collapsed. "No treasurer" and
    "attendance 54%" are different problems with different fixes."""
    today = timezone.localdate()
    flag = RiskFlag.objects.create(
        subject_type="GROUP",
        subject_id=wlt_group.pk,
        reason_code=RiskFlag._meta.get_field("reason_code").choices[0][0],
        raised_on=today - timedelta(days=9),
        detail={"actual": "54", "threshold": "60"},
    )

    card = cards(service.home(facilitator))["FC-4"]
    row = next(r for r in card["rows"] if r["flag"] == str(flag.pk))

    assert row["reason"]
    assert row["days_open"] == 9
    # The value that raised it, so the row can read "Attendance 54% (floor 60%)".
    assert row["detail"] == {"actual": "54", "threshold": "60"}


def test_the_formation_clock_counts_down_rather_than_naming_a_date(facilitator, wlt_draft):
    """ "11 days left" is a decision; "18 September" is arithmetic somebody has
    to do standing in a kebele."""
    today = timezone.localdate()
    Group.objects.filter(pk=wlt_draft.pk).update(status=GroupStatus.DRAFT, drafted_on=today - timedelta(days=50))

    card = cards(service.home(facilitator))["FC-5"]
    row = next(r for r in card["rows"] if r["group"] == str(wlt_draft.pk))

    assert row["days_remaining"] == 10
    assert row["expiring_soon"] is True
    assert row["expired"] is False


def test_the_sync_card_says_financial_records_are_never_merged(facilitator, wlt_group):
    card = cards(service.home(facilitator))["FC-6"]
    assert "never merged automatically" in card["note"]
