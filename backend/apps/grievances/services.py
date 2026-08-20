"""Grievance operations — spec §4.10.

A complaints channel is judged on two things: whether a complaint reaches
somebody, and how long it then sits. Both are properties of the *process*, not
of the complaint, so both are computed here rather than stored.

The one rule with teeth is that resolving requires saying what was done.
`RESOLVED` with empty notes is a status change dressed as an outcome, and it is
what turns a resolution rate into a number nobody should quote.
"""

from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import ComplaintType, Grievance, ResolutionStatus


class GrievanceError(ValidationError):
    """A refused grievance operation."""


@transaction.atomic
def raise_grievance(*, complaint_type, raised_by, summary, assigned_staff, woreda="", case=None, **fields):
    """Record a complaint.

    `case` is optional by §4.10 and that is the point: a complaint from an
    employer, a trainer, or a young person who never registered has to land
    somewhere. Where there is no case there is no woreda to inherit, so one is
    asked for — otherwise the complaint is invisible to every supervisor.
    """
    if case is None and not woreda:
        raise GrievanceError({"woreda": _("Say which woreda this concerns, so it reaches the right office.")})
    if not (summary or "").strip():
        raise GrievanceError({"summary": _("Record what happened.")})

    grievance = Grievance(
        case=case,
        complaint_type=complaint_type,
        raised_by=raised_by,
        summary=summary,
        assigned_staff=assigned_staff,
        woreda=woreda or (case.woreda if case else ""),
        **fields,
    )
    grievance.full_clean()
    grievance.save()
    if case is not None:
        case.touch()
    return grievance


@transaction.atomic
def start_work(grievance, *, actor=None):
    if grievance.resolution_status != ResolutionStatus.OPEN:
        raise GrievanceError(_("This grievance is no longer open."))
    grievance.resolution_status = ResolutionStatus.IN_PROGRESS
    grievance.full_clean()
    grievance.save(update_fields=["resolution_status", "updated_at"])
    return grievance


@transaction.atomic
def resolve(grievance, *, notes, resolution_date=None, actor=None):
    """Something was done about it, and here is what.

    The notes are mandatory. A resolution rate computed over status changes
    nobody described is the kind of figure that survives right up until somebody
    asks for an example.
    """
    if grievance.resolution_status in ResolutionStatus.terminal():
        raise GrievanceError(_("This grievance has already been concluded."))
    if not (notes or "").strip():
        raise GrievanceError({"resolution_notes": _("Say what was done about it.")})

    grievance.resolution_status = ResolutionStatus.RESOLVED
    grievance.resolution_date = resolution_date or date.today()
    grievance.resolution_notes = notes
    grievance.full_clean()
    grievance.save()
    if grievance.case_id:
        grievance.case.touch()
    return grievance


@transaction.atomic
def close_without_resolution(grievance, *, reason, closed_on=None, actor=None):
    """The file is shut and nothing was resolved.

    Kept apart from `resolve` because §4.10 keeps them apart, and because
    folding the two would inflate the resolution rate with every complaint whose
    complainant withdrew or could not be traced.
    """
    if grievance.resolution_status in ResolutionStatus.terminal():
        raise GrievanceError(_("This grievance has already been concluded."))
    if not (reason or "").strip():
        raise GrievanceError({"resolution_notes": _("Say why the file is being closed.")})

    grievance.resolution_status = ResolutionStatus.CLOSED
    grievance.resolution_date = closed_on or date.today()
    grievance.resolution_notes = reason
    grievance.full_clean()
    grievance.save()
    return grievance


def resolution_inputs(grievances):
    """`(resolved, concluded)` — the two numbers the resolution rate is built from.

    The denominator is grievances that have **concluded**, of either kind. One
    still open is neither resolved nor unresolved, and counting it as a failure
    would make the rate fall every time somebody files a complaint.
    """
    concluded = grievances.filter(resolution_status__in=ResolutionStatus.terminal()).count()
    return grievances.resolved().count(), concluded


def median_days_to_resolution(grievances):
    """How long a complaint sits, in days. None when nothing has concluded."""
    from apps.dashboard.rules import median

    days = [
        (grievance.resolution_date - grievance.date_raised).days
        for grievance in grievances.filter(resolution_status__in=ResolutionStatus.terminal())
        if grievance.resolution_date
    ]
    return median(days)


def partner_quality_feedback(partner=None):
    """Complaints about referral quality or timeliness, by partner.

    The qualitative counterpart to §8's failure rates. A partner with a good
    confirmation median and six quality complaints is not a good partner, and
    the numbers alone cannot say so.
    """
    queryset = Grievance.objects.about_referral_quality()
    if partner is not None:
        queryset = queryset.filter(about_partner=partner)

    rows = {}
    for grievance in queryset.select_related("about_partner"):
        key = grievance.about_partner_id
        name = grievance.about_partner.partner_name if grievance.about_partner_id else str(_("Not attributed"))
        row = rows.setdefault(key, {"partner_id": key, "partner": name, "total": 0, "open": 0, "types": {}})
        row["total"] += 1
        row["open"] += int(grievance.is_open)
        label = str(ComplaintType(grievance.complaint_type).label)
        row["types"][label] = row["types"].get(label, 0) + 1
    return sorted(rows.values(), key=lambda row: row["total"], reverse=True)


def overdue(grievances, as_of=None):
    """Open past the service standard.

    A grievance process nobody answers is worse than none: it collects the
    complaint, creates the expectation, and then does nothing with it.
    """
    return grievances.overdue(settings.GRIEVANCE_RESPONSE_DAYS, as_of=as_of)
