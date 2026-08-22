"""The group's audit trail.

Assembled from records that already exist rather than from an event table.
Writing these facts a second time into a log would create a second version of
the truth that could disagree with the first — and the audit trail is the one
place that must not happen.
"""

from datetime import date, timedelta

import pytest

from apps.wlt.models import ExitReason, GroupMembership, MeetingStatus
from apps.wlt.services import formation as formation_service
from apps.wlt.services import history as history_service
from apps.wlt.services import ledger as ledger_service

pytestmark = pytest.mark.django_db


def URL(group):
    return f"/api/v1/wlt/groups/{group.pk}/history/"


def titles(payload):
    return [event["title"] for event in payload["events"]]


class TestAssembly:
    def test_a_join_and_an_exit_are_both_events(self, wlt_group, wlt_members, facilitator):
        membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0], exited_on__isnull=True)
        formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date.today())

        payload = history_service.build(wlt_group, types=["MEMBERSHIP"])
        joined = [e for e in payload["events"] if e["title"].endswith("joined")]
        left = [e for e in payload["events"] if e["title"].endswith("left")]

        assert len(joined) == len(wlt_members)
        assert len(left) == 1

    def test_an_exit_carries_its_reason(self, wlt_group, wlt_members):
        """"Moved away" and "expelled" are opposite programme outcomes, and a
        trail recording only the date could not tell them apart afterwards."""
        membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0], exited_on__isnull=True)
        formation_service.exit_member(membership, reason=ExitReason.EXPELLED, on_date=date.today())

        payload = history_service.build(wlt_group, types=["MEMBERSHIP"])
        left = next(e for e in payload["events"] if e["title"].endswith("left"))
        assert left["detail"] == "Expelled"

    def test_a_closed_meeting_is_an_event_and_an_open_one_is_not(self, wlt_group, facilitator):
        """An open meeting has not happened yet in any auditable sense: its cash
        is uncounted and its register is still being written."""
        closed = ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)
        ledger_service.close_meeting(closed, counted_cash_etb=ledger_service.expected_cash(closed), actor=facilitator)
        ledger_service.open_meeting(wlt_group, held_on=date.today(), recorded_by=facilitator)

        payload = history_service.build(wlt_group, types=["MEETING"])
        assert payload["total"] == wlt_group.meetings.filter(status=MeetingStatus.CLOSED).count()

    def test_an_election_shows_as_a_membership_event(self, wlt_group, wlt_members):
        formation_service.elect_officer(wlt_group, person=wlt_members[3], role="CHAIR")
        payload = history_service.build(wlt_group, types=["MEMBERSHIP"])
        assert any("elected chair" in title for title in titles(payload))

    def test_newest_first(self, wlt_group, wlt_members, facilitator):
        membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0], exited_on__isnull=True)
        formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date.today())

        payload = history_service.build(wlt_group)
        dates = [event["at"] for event in payload["events"]]
        assert dates == sorted(dates, reverse=True)

    def test_dates_and_timestamps_sort_together(self, wlt_group, wlt_members, facilitator):
        """Memberships carry a date and linkage events a timestamp. Comparing a
        naive datetime with an aware one raises, which would surface as a 500 on
        whichever group happened to mix them."""
        membership = GroupMembership.objects.get(group=wlt_group, person=wlt_members[0], exited_on__isnull=True)
        formation_service.exit_member(membership, reason=ExitReason.MOVED, on_date=date.today() - timedelta(days=1))

        payload = history_service.build(wlt_group)
        assert payload["total"] > 0

    def test_filtering_narrows_to_one_family(self, wlt_group, wlt_members):
        everything = history_service.build(wlt_group)["total"]
        members_only = history_service.build(wlt_group, types=["MEMBERSHIP"])["total"]

        assert 0 < members_only <= everything

    def test_an_unknown_filter_is_ignored_rather_than_emptying_the_page(self, wlt_group, wlt_members):
        """The value arrives from a URL."""
        payload = history_service.build(wlt_group, types=["NONSENSE"])
        assert payload["total"] == history_service.build(wlt_group)["total"]

    def test_paging_reports_the_whole_total(self, wlt_group, wlt_members):
        page = history_service.build(wlt_group, limit=3)
        assert len(page["events"]) == 3
        # The total is the trail, not the page — "load earlier" needs to know
        # whether there is any earlier.
        assert page["total"] > 3

    def test_a_later_page_does_not_repeat_the_first(self, wlt_group, wlt_members):
        first = history_service.build(wlt_group, limit=3, offset=0)["events"]
        second = history_service.build(wlt_group, limit=3, offset=3)["events"]
        assert first != second


class TestTheEndpoint:
    def test_a_facilitator_reads_her_group_s_history(self, as_user, facilitator, wlt_group, wlt_members):
        response = as_user(facilitator).get(URL(wlt_group))
        assert response.status_code == 200
        assert response.data["total"] > 0

    def test_bad_paging_values_are_the_first_page_not_a_500(self, as_user, facilitator, wlt_group):
        response = as_user(facilitator).get(URL(wlt_group), {"limit": "all", "offset": "-5"})
        assert response.status_code == 200

    def test_it_is_refused_across_the_module_boundary(self, as_user, case_manager, wlt_group):
        assert as_user(case_manager).get(URL(wlt_group)).status_code == 403
