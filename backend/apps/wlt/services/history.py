"""The group's audit trail, assembled from what already happened.

There is no event table and this deliberately does not add one. Everything the
history needs is already recorded, because each of these facts had to be
durable for its own sake:

* `PhaseEvent` — a submission and its decision, immutable once decided.
* `LinkageEvent` — every linkage status change, with its actor.
* `GroupMembership` — dated ranges, so a join and an exit are both dates on a
  row that is never deleted.
* `Meeting` — closed meetings, with the counted cash that balanced.
* `OfficeHolder` — dated terms, closed rather than overwritten.

Writing those a second time into an event log would create a second version of
the truth that could disagree with the first, and the disagreement would only
ever be discovered by somebody reading the audit trail — the one place it must
not happen. So this reads them and merges.

The cost is that paging is done in Python over a merged list rather than by the
database. That is acceptable at this scale: the sources are one group's records,
the largest of which is its meetings, and a group with a year behind it has
about fifty. It would not be acceptable across all groups, and this is
deliberately per-group only.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from django.utils.translation import gettext as _

#: The four families the screen filters by. Office changes are membership
#: events: they are facts about who is in the group and what they do in it,
#: and a fifth filter for three rows a year would be a control nobody uses.
PHASE = "PHASE"
MEMBERSHIP = "MEMBERSHIP"
MEETING = "MEETING"
LINKAGE = "LINKAGE"

EVENT_TYPES = (PHASE, MEMBERSHIP, MEETING, LINKAGE)


@dataclass(order=True)
class Event:
    """One thing that happened, ordered by when."""

    sort_key: datetime = field(compare=True)
    at: str = field(compare=False, default="")
    type: str = field(compare=False, default="")
    title: str = field(compare=False, default="")
    detail: str = field(compare=False, default="")
    actor: str = field(compare=False, default="")

    def as_dict(self):
        return {"at": self.at, "type": self.type, "title": self.title, "detail": self.detail, "actor": self.actor}


def _moment(value):
    """A date or datetime as a comparable, timezone-aware datetime.

    Some sources carry a date and some a timestamp. Sorting them together needs
    one type, and a naive datetime compared against an aware one raises — which
    would surface as a 500 on a group whose history happened to mix the two.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _day(value):
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def _name(user):
    return getattr(user, "full_name", "") or ""


def build(group, types=None, limit=40, offset=0):
    """The group's history, newest first, with a total so the screen can page.

    `types` filters to a subset of `EVENT_TYPES`; anything unrecognised is
    ignored rather than refused, because the value arrives from a URL.
    """
    wanted = {t for t in (types or EVENT_TYPES) if t in EVENT_TYPES} or set(EVENT_TYPES)
    events: list[Event] = []

    if PHASE in wanted:
        for phase in group.phase_events.select_related("submitted_by", "decided_by"):
            moved_from = phase.get_from_phase_display() or _("Forming")
            if phase.submitted_at:
                events.append(
                    Event(
                        sort_key=_moment(phase.submitted_at),
                        at=_day(phase.submitted_at),
                        type=PHASE,
                        title=_("Readiness submitted"),
                        detail=_("%(from)s to %(to)s") % {"from": moved_from, "to": phase.get_to_phase_display()},
                        actor=_name(phase.submitted_by),
                    )
                )
            # The decision is its own event, not a property of the submission:
            # "who decided, and when" is the question the trail is read for, and
            # it is frequently a different person on a different day.
            if phase.decided_at:
                events.append(
                    Event(
                        sort_key=_moment(phase.decided_at),
                        at=_day(phase.decided_at),
                        type=PHASE,
                        title=_("Phase decided"),
                        detail=_("%(from)s to %(to)s") % {"from": moved_from, "to": phase.get_to_phase_display()},
                        actor=_name(phase.decided_by),
                    )
                )

    if MEMBERSHIP in wanted:
        for membership in group.memberships.select_related("person"):
            events.append(
                Event(
                    sort_key=_moment(membership.joined_on),
                    at=_day(membership.joined_on),
                    type=MEMBERSHIP,
                    title=_("%(name)s joined") % {"name": membership.person.full_name},
                    detail="",
                )
            )
            # An exit carries its reason. "Moved away" and "expelled" are
            # opposite programme outcomes, and a trail that recorded only the
            # date could not tell them apart afterwards.
            if membership.exited_on:
                events.append(
                    Event(
                        sort_key=_moment(membership.exited_on),
                        at=_day(membership.exited_on),
                        type=MEMBERSHIP,
                        title=_("%(name)s left") % {"name": membership.person.full_name},
                        detail=membership.get_exit_reason_display() or "",
                    )
                )

        for office in group.office_holders.select_related("person"):
            events.append(
                Event(
                    sort_key=_moment(office.from_date),
                    at=_day(office.from_date),
                    type=MEMBERSHIP,
                    title=_("%(name)s elected %(role)s")
                    % {"name": office.person.full_name, "role": office.get_role_display().lower()},
                    detail="",
                )
            )

    if MEETING in wanted:
        from ..models import MeetingStatus

        for meeting in group.meetings.filter(status=MeetingStatus.CLOSED):
            events.append(
                Event(
                    sort_key=_moment(meeting.held_on),
                    at=_day(meeting.held_on),
                    type=MEETING,
                    title=_("Meeting %(no)s closed") % {"no": meeting.meeting_no},
                    detail=_("ETB %(counted)s counted in the box") % {"counted": meeting.counted_cash_etb},
                    actor=_name(meeting.recorded_by),
                )
            )

    if LINKAGE in wanted:
        from ..models import LinkageEvent

        for event in (
            LinkageEvent.objects.filter(linkage__subject_group=group)
            .select_related("linkage__linkage_type", "actor")
            .order_by("-occurred_at")
        ):
            events.append(
                Event(
                    sort_key=_moment(event.occurred_at),
                    at=_day(event.occurred_at),
                    type=LINKAGE,
                    title=_("%(type)s — %(status)s")
                    % {
                        "type": event.linkage.linkage_type.label,
                        "status": event.get_to_status_display(),
                    },
                    detail=event.reason or "",
                    actor=_name(event.actor),
                )
            )

    events.sort(reverse=True)
    return {
        "total": len(events),
        "events": [event.as_dict() for event in events[offset : offset + limit]],
    }
