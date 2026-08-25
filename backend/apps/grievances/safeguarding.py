"""Who may read a safeguarding disclosure, and the record that they did.

Treated as a different product that happens to live in the same application.
The rules below are deliberately narrower than anything else in the platform,
and three of them are departures from how the rest of it works:

* **Access is a named list, not a role.** `SafeguardingFocalPoint` names people
  per woreda. A role is inherited — provision a new account with the right
  permission and it silently acquires the ability to read a survivor's account
  of what happened to her.
* **The system administrator is not on the list.** Everywhere else in this
  platform the administrator reads everything, and that widening is a confirmed
  decision. It is reversed here, for restricted content only: an administrator
  is an account somebody holds in order to run the software, and running the
  software has never required reading this. She still sees that the record
  exists, and the log shows if she has broken it open.
* **The record is never hidden, only redacted.** A disclosure that vanishes from
  every list is one nobody can be held to. The row stays, showing its reference,
  its date and its woreda, so the queue can prove the mechanism received it.
"""

from datetime import date

from django.db import models
from django.utils.translation import gettext_lazy as _

#: What a reader who is not a focal point may see of a restricted record.
#: A reference, a date, a place, and the fact that it is restricted. Nothing
#: that could identify a survivor, and nothing about what happened.
VISIBLE_WHEN_RESTRICTED = (
    "id",
    "short_reference",
    "woreda",
    "date_raised",
    "status",
    "tier",
    "tier_display",
    "status_display",
    "complaint_type",
    "complaint_type_display",
    "is_restricted",
    "restricted",
    "subject_type",
    # How long it has been open, and whether it still is. Neither says anything
    # about a survivor, and the safeguarding lead has to be able to see that a
    # disclosure has been sitting for forty days without reading it. Withheld,
    # the queue rendered "undefined day(s) open" — which is how this was found.
    "days_open",
    "is_open",
    # The clock, but not what it is about. A lead has to see that a disclosure
    # is three days from its deadline without reading a word of it.
    "severity",
    "severity_display",
    "can_act",
    "due_on",
    "standing",
    "created_at",
    "updated_at",
)

#: The sentence the screen shows a focal point before they open one.
ACCESS_NOTICE = _("Opening this record is logged, with your name and the time, and the safeguarding lead can see it.")


def focal_points_for(woreda, on_date=None):
    """The people named for this woreda today."""
    from .models import SafeguardingFocalPoint

    on_date = on_date or date.today()
    return SafeguardingFocalPoint.objects.filter(woreda=woreda, from_date__lte=on_date).filter(
        models.Q(to_date__isnull=True) | models.Q(to_date__gte=on_date)
    )


def may_read_content(user, grievance, on_date=None):
    """May this person read what the complaint actually says?

    Three ways in, and no fourth:

    * the record is not restricted at all — the ordinary rules apply and this
      function is not the one deciding;
    * the reader is a named focal point for the record's woreda, today;
    * the reader is the person who wrote it down. She already heard it, and
      hiding it from her protects nobody; it is also the only way a disclosure
      is readable at all in a woreda where no focal point has been named yet.

    **`recorded_by`, not `assigned_staff`, and the difference is the control.**
    Assignment is a field anybody with write access can change, so granting the
    assignee read access would let a reader grant it to herself by reassigning
    the record to her own name — with no other permission required and nothing
    on screen to say she had done it. `recorded_by` is stamped once from
    `request.user` and is read-only on every serializer.

    Note what is absent: the system administrator, the assignee, a supervisor,
    and anybody holding a role that merely *sounds* senior.
    """
    from .models import SafeguardingFocalPoint

    if not grievance.is_restricted:
        return True
    if user is None or not user.is_authenticated:
        return False
    if grievance.recorded_by_id and grievance.recorded_by_id == user.pk:
        return True

    on_date = on_date or date.today()
    return any(
        appointment.covers(on_date)
        for appointment in SafeguardingFocalPoint.objects.filter(woreda=grievance.woreda, person=user)
    )


def record_access(grievance, user, *, granted):
    """Write the event. Called on every open of a restricted record.

    A refused attempt is the more interesting row and is recorded too — the
    question "who tried" has no answer otherwise.
    """
    from .models import GrievanceAccess

    return GrievanceAccess.objects.create(
        grievance=grievance,
        reader=user,
        role=user.role or "",
        granted=granted,
    )
