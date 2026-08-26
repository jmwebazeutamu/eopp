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

from .models import ComplaintType, Grievance, GrievanceStatus, Outcome, Tier


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
    subject_group = fields.get("subject_group")
    subject_youth = fields.get("subject_youth")

    # A group complaint takes its group's woreda; a person complaint takes hers.
    # A hand-typed one that disagrees would scope to one office and report in
    # another, which is the same fault `Case.woreda` is denormalised to avoid.
    if not woreda and subject_group is not None:
        woreda = _woreda_of(subject_group)
    if not woreda and subject_youth is not None:
        woreda = subject_youth.woreda

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


def _woreda_of(group):
    """The woreda name a group sits in, walked up from its kebele.

    Groups carry a `Location` row; grievances carry a woreda *name*, because
    most complaints have neither a group nor a case to inherit a location from.
    This is the one place the two vocabularies meet.
    """
    node = getattr(group, "kebele", None)
    while node is not None:
        if getattr(node, "level", None) == "WOREDA":
            return node.name
        node = node.parent
    return ""


@transaction.atomic
def acknowledge(grievance, *, method, actor, when=None):
    """Record that the complainant was told it had arrived.

    A separate step from working on it, and the artifact is right that it is the
    one auditors check: action notes capture what staff did, and nothing used to
    capture what the complainant was told. In a district where many complainants
    cannot read a letter and share a household phone, it is also the step most
    likely to be skipped.

    **The method is required.** "Acknowledged" with no record of how is a tick
    somebody can apply from a desk, and the whole point of the field is that it
    describes something that happened in the world.
    """
    from django.utils import timezone

    if grievance.acknowledged_at:
        raise GrievanceError({"detail": _("This complaint has already been acknowledged.")})
    if not (method or "").strip():
        raise GrievanceError({"method": _("Say how the complainant was told — in person, by phone, at a meeting.")})

    # The stamp *and* the move, in that order and in one transaction. Written
    # as a stamp alone at first, which left an acknowledged complaint still
    # reading "Received" — the exact conflation of "what happened" and "where
    # the work is" that eight states exist to undo.
    #
    # The fact is persisted **before** the edge is attempted, because
    # `transition_to` re-reads the row under `select_for_update` and its gate
    # asks the database, not this instance. That is the right way round: the
    # gate's question is "is this true of the record", and an unsaved attribute
    # is not yet true of anything.
    grievance.acknowledged_at = when or timezone.now()
    grievance.acknowledged_by = actor
    grievance.acknowledgement_method = method.strip()
    grievance.save(update_fields=["acknowledged_at", "acknowledged_by", "acknowledgement_method", "updated_at"])

    grievance.transition_to(GrievanceStatus.ACKNOWLEDGED, actor=actor)
    grievance.save(update_fields=["status", "updated_at"])
    return grievance


@transaction.atomic
def add_note(grievance, *, body, author):
    """Append to the case file. Nothing here is ever edited afterwards."""
    from .models import GrievanceNote

    if not (body or "").strip():
        raise GrievanceError({"body": _("Write what happened.")})

    return GrievanceNote.objects.create(
        grievance=grievance,
        body=body.strip(),
        author=author,
        author_role=author.role or "",
    )


def queue_counts(grievances, as_of=None):
    """The first row of the queue — what needs somebody today.

    Counted over the caller's already-scoped queryset, never over the table: an
    aggregate is a disclosure too, and "4 late" told to someone entitled to see
    one woreda must mean four in that woreda.
    """
    return {
        "late": grievances.late(as_of=as_of).count(),
        "due_this_week": grievances.due_within(7, as_of=as_of).count(),
        "awaiting_acknowledgement": grievances.awaiting_acknowledgement().count(),
        "restricted": grievances.filter(is_restricted=True).count(),
    }


# ---------------------------------------------------------------------------
# The workflow
#
# Every one of these is a thin wrapper over `Grievance.transition_to`, which owns
# the edges and the gates. The wrapper's job is to write the facts the edge
# demanded — the outcome, the feedback, the pause reason — in the same
# transaction that moves the status, so a case can never sit in `DECIDED` with
# no outcome or in `CLOSED` with nobody told.
# ---------------------------------------------------------------------------


@transaction.atomic
def start_review(grievance, *, actor=None):
    """A committee or officer picks it up.

    Reachable only from `ACKNOWLEDGED`. Working a complaint before telling the
    complainant it arrived is the order this workflow refuses on purpose: the
    acknowledgement is a promise, and a promise made after the fact is not one.
    """
    grievance.transition_to(GrievanceStatus.UNDER_REVIEW, actor=actor)
    grievance.save(update_fields=["status", "updated_at"])
    return grievance


@transaction.atomic
def pause_for_complainant(grievance, *, reason, chase_date, actor=None):
    """The only pause, and it stops the clock.

    Any other pause would be a hiding place — a state whose clock does not run
    and which nobody is accountable for. This one has a reason and a date to
    chase, and both are required by the edge rather than by a form.
    """
    grievance.transition_to(
        GrievanceStatus.AWAITING_COMPLAINANT, actor=actor, pause_reason=reason, chase_date=chase_date
    )
    grievance.pause_reason = (reason or "").strip()
    grievance.chase_date = chase_date
    grievance.paused_on = date.today()
    grievance.save(update_fields=["status", "pause_reason", "chase_date", "paused_on", "updated_at"])
    return grievance


@transaction.atomic
def resume(grievance, *, actor=None):
    """The complainant answered, or the chase date passed.

    **The deadline moves by however long the pause lasted.** Leaving `due_on`
    where it was would charge the programme for time it spent waiting on
    somebody else, and a metric that does that teaches people not to pause —
    which means recording the wait somewhere it cannot be seen.
    """
    from . import clock

    grievance.transition_to(GrievanceStatus.UNDER_REVIEW, actor=actor)
    if grievance.paused_on and grievance.due_on:
        waited = clock.working_days_between(grievance.paused_on, date.today())
        grievance.due_on = clock.add_working_days(grievance.due_on, max(0, waited))
    grievance.pause_reason = ""
    grievance.chase_date = None
    grievance.paused_on = None
    grievance.save(update_fields=["status", "due_on", "pause_reason", "chase_date", "paused_on", "updated_at"])
    return grievance


@transaction.atomic
def decide(grievance, *, outcome, reason, actor=None, decided_on=None):
    """Record what was decided — which is not the same as shutting the file.

    `DECIDED` exists as its own state because a decision the complainant has not
    heard is not a conclusion. The old ladder went straight from in-progress to
    resolved, so the gap between deciding and telling somebody was invisible and
    therefore unmeasured.
    """
    grievance.transition_to(GrievanceStatus.DECIDED, actor=actor, outcome=outcome, outcome_reason=reason)
    grievance.outcome = outcome
    grievance.outcome_reason = (reason or "").strip()
    grievance.resolution_date = decided_on or date.today()
    grievance.save(update_fields=["status", "outcome", "outcome_reason", "resolution_date", "updated_at"])
    return grievance


@transaction.atomic
def record_feedback_and_close(grievance, *, method, satisfied=None, actor=None, when=None):
    """Shut the file, having told the complainant the answer.

    The gate the whole rebuild turns on. Before this it was possible to close a
    case having told nobody anything: action notes captured what staff did, and
    nothing captured what the complainant was told. It is the step most likely
    to be skipped and the one an auditor asks about first.

    `satisfied` is deliberately nullable. "Told, and did not say" is a real and
    common answer, and recording it as dissatisfaction would be as wrong as
    recording it as agreement.
    """
    from django.utils import timezone

    grievance.transition_to(GrievanceStatus.CLOSED, actor=actor, feedback_method=method)
    grievance.feedback_given_at = when or timezone.now()
    grievance.feedback_method = (method or "").strip()
    grievance.complainant_satisfied = satisfied
    grievance.resolution_date = grievance.resolution_date or date.today()
    grievance.save(
        update_fields=[
            "status",
            "feedback_given_at",
            "feedback_method",
            "complainant_satisfied",
            "resolution_date",
            "updated_at",
        ]
    )
    return grievance


@transaction.atomic
def appeal(grievance, *, ground, actor=None):
    """The complainant rejects the decision, and the case goes up a tier.

    A **child record**, not a status flip on the parent. Both records keep their
    own history, their own clock and their own decision — which is the only
    shape in which "the woreda overturned the kebele" is a computable fact
    rather than a story somebody remembers.

    The statement travels with it and the outcome does not: the appeal is heard
    on what the complainant said, not on what the tier below concluded about it.
    """
    grievance.transition_to(GrievanceStatus.APPEALED, actor=actor, appeal_ground=ground)
    # The ground belongs to the **child**, not to the parent. Storing it on both
    # tripped `grievance_appeal_needs_a_parent`, and the constraint was right to
    # complain: a record carrying a ground of appeal and no parent is an appeal
    # against nothing. The parent's `APPEALED` status and the child's existence
    # are what say it was appealed.
    grievance.save(update_fields=["status", "updated_at"])

    child = Grievance(
        parent_grievance=grievance,
        tier=Tier.above(grievance.tier),
        appeal_ground=(ground or "").strip(),
        case=grievance.case,
        subject_youth=grievance.subject_youth,
        subject_group=grievance.subject_group,
        about_partner=grievance.about_partner,
        related_referral=grievance.related_referral,
        woreda=grievance.woreda,
        complaint_type=grievance.complaint_type,
        severity=grievance.severity,
        raised_by=grievance.raised_by,
        complainant_name=grievance.complainant_name,
        complainant_contact=grievance.complainant_contact,
        summary=grievance.summary,
        assigned_staff=grievance.assigned_staff,
        recorded_by=actor,
    )
    child.full_clean()
    child.save()
    return child


@transaction.atomic
def refer_out(grievance, *, to, actor=None):
    """Somebody else owns this now — a court, an agency, a safeguarding service.

    Recorded rather than worked. The clock stops and the reference is kept, so
    the case can be answered for without the platform pretending to be handling
    something it is not.
    """
    grievance.transition_to(GrievanceStatus.REFERRED_OUT, actor=actor, referred_to=to)
    grievance.referred_to = (to or "").strip()
    grievance.resolution_date = grievance.resolution_date or date.today()
    grievance.save(update_fields=["status", "referred_to", "resolution_date", "updated_at"])
    return grievance


def overturn_rate(grievances):
    """How often the tier above disagreed with the tier below.

    The number a supervision mission reads to decide whether the second tier is
    independent. **A zero overturn rate is a finding, not a success** — it means
    either that first-tier decisions are always right or that the second tier is
    not really reviewing them, and only somebody who knows the woreda can say
    which.

    Reported with its denominator, like every other rate in this platform: three
    appeals of which one was overturned is not 33%, it is one of three.
    """
    appeals = grievances.filter(parent_grievance__isnull=False).decided()
    total = appeals.count()
    overturned = appeals.filter(outcome__in=Outcome.in_the_complainant_favour()).exclude(
        parent_grievance__outcome__in=Outcome.in_the_complainant_favour()
    )
    return {"appeals_decided": total, "overturned": overturned.count()}


def decision_counts(grievances):
    """What the concluded files were decided to be.

    Replaces `resolution_inputs`, which returned `(resolved, concluded)` and
    called `GrievanceQuerySet.resolved()` — a method the eight-state rebuild
    removed, because `RESOLVED` had meant two things at once. Left as it was,
    the ratio it fed would now read "upheld / concluded" under the old label,
    so a complaint properly investigated and found unfounded would count
    against the channel that investigated it.

    Five numbers, because the enum draws the distinctions and a rate must not
    flatten them:

    * `concluded` — the file is shut, of any kind.
    * `upheld` / `not_upheld` — judged on the merits, either way.
    * `not_judged` — withdrawn or referred to another body. Concluded, but
      nobody ever ruled on it, so it belongs in neither half of a rate.
    * `no_outcome_recorded` — shut with no `Outcome` at all. Not a rounding
      error: migration `0005` deliberately wrote no outcome onto rows carried
      over from the four-status model, because the old value could not say
      which one it had been. It shrinks as those files are revisited, and
      hiding it inside `not_judged` would make it look settled.

    The denominator for an upheld rate is `upheld + not_upheld` and nothing
    else. One still open is neither upheld nor dismissed, and counting it as a
    failure would make the rate fall every time somebody files a complaint.
    """
    concluded = grievances.filter(status__in=GrievanceStatus.terminal())
    upheld = concluded.upheld().count()
    not_upheld = concluded.filter(outcome=Outcome.NOT_UPHELD).count()
    not_judged = concluded.filter(outcome__in=(Outcome.REFERRED, Outcome.WITHDRAWN)).count()
    total = concluded.count()
    return {
        "concluded": total,
        "upheld": upheld,
        "not_upheld": not_upheld,
        "not_judged": not_judged,
        "no_outcome_recorded": total - upheld - not_upheld - not_judged,
    }


def median_days_to_resolution(grievances):
    """How long a complaint sits, in days. None when nothing has concluded."""
    from apps.dashboard.rules import median

    days = [
        (grievance.resolution_date - grievance.date_raised).days
        for grievance in grievances.filter(status__in=GrievanceStatus.terminal())
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
