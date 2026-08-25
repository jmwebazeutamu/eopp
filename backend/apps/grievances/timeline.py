"""The case file, read forwards.

A grievance is worked over weeks by several people, and the question the file is
opened to answer is "what has happened to this so far". That was unanswerable:
the status was a single word, the notes were one overwritable field, and the
audit trail existed but only in the admin.

**No new event table.** Everything here is already recorded, because each fact
had to be durable for its own sake — the history rows `simple_history` writes on
every save, the append-only notes, the acknowledgement stamp, the resolution.
Writing them a second time into a log would create a second version of the truth
that could disagree with the first, and the audit trail is the one place that
must not happen. Same reasoning as `wlt.services.history`.

The original statement is always the first entry and is never editable. A
correction appends; it does not overwrite.
"""

from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from django.utils.translation import gettext as _

STATEMENT = "STATEMENT"
ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
NOTE = "NOTE"
STATUS = "STATUS"
OUTCOME = "OUTCOME"

EVENT_TYPES = (STATEMENT, ACKNOWLEDGEMENT, NOTE, STATUS, OUTCOME)


@dataclass(order=True)
class Event:
    sort_key: datetime = field(compare=True)
    at: str = field(compare=False, default="")
    type: str = field(compare=False, default="")
    title: str = field(compare=False, default="")
    body: str = field(compare=False, default="")
    actor: str = field(compare=False, default="")

    def as_dict(self):
        return {"at": self.at, "type": self.type, "title": self.title, "body": self.body, "actor": self.actor}


def _moment(value):
    """A date or a datetime as one comparable, aware type.

    History rows carry timestamps and `date_raised` carries a date. Sorting them
    together needs one type, and comparing a naive datetime against an aware one
    raises — which would surface as a 500 on whichever case happened to mix them.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _day(value):
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def _name(user):
    return getattr(user, "full_name", "") or ""


def build(grievance):
    """Oldest first — a file is read from the beginning, unlike a queue."""
    events = [
        Event(
            sort_key=_moment(grievance.date_raised),
            at=_day(grievance.date_raised),
            type=STATEMENT,
            title=_("Complaint received"),
            body=grievance.summary,
            actor=_name(grievance.recorded_by),
        )
    ]

    if grievance.acknowledged_at:
        events.append(
            Event(
                sort_key=_moment(grievance.acknowledged_at),
                at=_day(grievance.acknowledged_at),
                type=ACKNOWLEDGEMENT,
                title=_("Complainant told it had arrived"),
                body=grievance.acknowledgement_method,
                actor=_name(grievance.acknowledged_by),
            )
        )

    for note in grievance.notes.select_related("author"):
        events.append(
            Event(
                sort_key=_moment(note.created_at),
                at=_day(note.created_at),
                type=NOTE,
                title=_("Note"),
                body=note.body,
                actor=_name(note.author),
            )
        )

    # Status moves come from the history table rather than from a field this
    # module writes. `simple_history` already records who changed what and when
    # on every save, so a second record of the same move could only ever be a
    # second record that disagreed.
    previous = None
    for record in grievance.history.order_by("history_date"):
        if previous is not None and record.status != previous:
            events.append(
                Event(
                    sort_key=_moment(record.history_date),
                    at=_day(record.history_date),
                    type=OUTCOME if record.outcome else STATUS,
                    title=record.get_status_display(),
                    body=record.outcome_reason or "",
                    actor=_name(record.history_user),
                )
            )
        previous = record.status

    events.sort()
    return [event.as_dict() for event in events]
