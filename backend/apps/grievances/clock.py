"""Deadlines, in working days, against the calendar people actually keep.

A grievance mechanism is judged on whether it answered in time, so the
arithmetic behind "3 days late" has to be defensible to the person it is said
about. Three decisions make it so:

* **Working days, not elapsed days.** A complaint taken on a Friday afternoon
  and answered on Monday morning took one working day, and a metric that calls
  it three teaches woreda staff that the metric is wrong.

* **Ethiopian public holidays are loaded**, not assumed away. A deadline that
  lands on Meskel and is marked breached destroys trust in the figure faster
  than no figure at all. The movable feasts are listed rather than computed:
  Fasika and the Islamic holidays follow calendars this module has no business
  implementing, and a wrong date printed confidently is worse than a table
  somebody has to extend.

* **The week ends on Sunday alone.** Ethiopian government offices work Monday
  to Friday and often Saturday morning; counting Saturday as a working day
  would flatter every figure. Saturday is excluded and the assumption is stated
  here so it can be argued with.

The deadlines themselves are configuration — `settings.GRIEVANCE_*` — because
the federal 10/10/15/30 default may not be what this project is contractually
held to, and that is open question 4 of the review.
"""

from datetime import date, timedelta

from django.conf import settings

#: Ethiopian public holidays, Gregorian, for the years this pilot runs.
#:
#: Hand-listed on purpose. Fasika, Eid al-Fitr and Eid al-Adha move against the
#: Gregorian calendar by rules — Julian Easter, and a lunar calendar observed by
#: sighting — that do not belong in a grievance module. Extending the table is a
#: five-minute job somebody does once a year; getting Ramadan wrong in code is a
#: bug nobody notices until a deadline is disputed.
#:
#: TODO(open-question): confirm against the regional calendar for Oromia. Some
#: regional holidays (Irreecha) are observed in East Shewa and are not here.
PUBLIC_HOLIDAYS = {
    # 2026
    date(2026, 1, 7): "Genna",
    date(2026, 1, 19): "Timkat",
    date(2026, 3, 2): "Adwa Victory Day",
    date(2026, 3, 20): "Eid al-Fitr",
    date(2026, 4, 10): "Good Friday",
    date(2026, 4, 12): "Fasika",
    date(2026, 5, 1): "Labour Day",
    date(2026, 5, 5): "Patriots' Victory Day",
    date(2026, 5, 27): "Eid al-Adha",
    date(2026, 5, 28): "Downfall of the Derg",
    date(2026, 8, 25): "Mawlid",
    date(2026, 9, 11): "Enkutatash",
    date(2026, 9, 27): "Meskel",
    # 2027
    date(2027, 1, 7): "Genna",
    date(2027, 1, 19): "Timkat",
    date(2027, 3, 2): "Adwa Victory Day",
    date(2027, 3, 10): "Eid al-Fitr",
    date(2027, 4, 30): "Good Friday",
    date(2027, 5, 1): "Labour Day",
    date(2027, 5, 2): "Fasika",
    date(2027, 5, 5): "Patriots' Victory Day",
    date(2027, 5, 17): "Eid al-Adha",
    date(2027, 5, 28): "Downfall of the Derg",
    date(2027, 8, 15): "Mawlid",
    date(2027, 9, 11): "Enkutatash",
    date(2027, 9, 27): "Meskel",
}

#: Sunday. `weekday()` numbers Monday 0 … Sunday 6.
_REST_DAY = 6


def is_working_day(day):
    return day.weekday() != _REST_DAY and day not in PUBLIC_HOLIDAYS


def add_working_days(start, days):
    """`days` working days after `start`, skipping rests and holidays.

    Counting forward one day at a time rather than by arithmetic on weeks: the
    holiday table is irregular, and a closed-form version would have to special
    case every one of them. The loop runs at most a few dozen times.
    """
    day = start
    remaining = max(0, int(days))
    while remaining:
        day += timedelta(days=1)
        if is_working_day(day):
            remaining -= 1
    return day


def working_days_between(start, end):
    """Working days from `start` to `end`, signed.

    Negative when `end` is before `start`, which is what lets one figure carry
    both "due in 2 days" and "3 days late" without the caller branching on
    which side of the deadline it is.
    """
    if end == start:
        return 0
    step = 1 if end > start else -1
    day, count = start, 0
    while day != end:
        day += timedelta(days=step)
        if is_working_day(day):
            count += step
    return count


def response_days(*, severity=None):
    """How long this complaint has, in working days.

    Severity overrides the default: a critical complaint is answered in three
    working days whatever tier it sits at, because the thing that makes it
    critical does not wait for a committee's usual rhythm.

    Both numbers are settings and both are unagreed — the federal GRM default
    is 10 working days at kebele and woreda, and this platform's own
    `GRIEVANCE_RESPONSE_DAYS` has been 21 calendar days since Sprint 6. They are
    not the same standard and somebody has to choose.
    """
    from .models import Severity

    if severity == Severity.CRITICAL:
        return settings.GRIEVANCE_CRITICAL_RESPONSE_DAYS
    if severity == Severity.SERIOUS:
        return settings.GRIEVANCE_SERIOUS_RESPONSE_DAYS
    return settings.GRIEVANCE_RESPONSE_DAYS


def acknowledgement_days():
    """How long to tell the complainant it arrived.

    A separate and much shorter clock. Acknowledgement is not an answer — it is
    the promise that an answer is coming, and it is the step most often skipped
    because nothing in the record used to ask for it.
    """
    return settings.GRIEVANCE_ACKNOWLEDGEMENT_DAYS


def due_on(*, raised_on, severity=None):
    return add_working_days(raised_on, response_days(severity=severity))


def acknowledgement_due_on(*, raised_on):
    return add_working_days(raised_on, acknowledgement_days())


def standing(grievance, as_of=None):
    """How this case stands against its clock, as data.

    One shape for every state, so the screen does not branch: `days` is signed
    working days to the deadline, `state` names which sentence to render, and a
    concluded case reports `closed` with the clock stopped at its resolution
    date rather than still counting.
    """
    as_of = as_of or date.today()

    if not grievance.is_open:
        stopped = grievance.resolution_date or as_of
        return {
            "state": "closed",
            "days": working_days_between(grievance.date_raised, stopped),
            "due_on": grievance.due_on.isoformat() if grievance.due_on else None,
        }

    if grievance.due_on is None:
        return {"state": "unscheduled", "days": None, "due_on": None}

    remaining = working_days_between(as_of, grievance.due_on)
    return {
        "state": "late" if remaining < 0 else "due" if remaining <= 2 else "on_time",
        "days": remaining,
        "due_on": grievance.due_on.isoformat(),
    }
