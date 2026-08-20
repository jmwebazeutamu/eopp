"""Placement operations — spec §4.7.

Recording a placement does three things beyond writing the row:

1. **Opens the three checkpoints.** All three, immediately, as `PENDING` rows.
   A checkpoint that exists only as arithmetic cannot be listed, counted or
   assigned, and every screen would have to recompute it.
2. **Moves the case to Placed.** One-way, and by the same rule the referral
   engine already uses — removing a placement does not demote a case, because
   `PLACED` is also a judgement a case manager may make by hand (§4.2).
3. **Stamps case activity.** A youth who started work last week is not a stalled
   case.

Recording an *exit* closes the outstanding checkpoints rather than leaving them
pending forever: once the youth has left, "is she still there at 90 days" has an
answer, and it is no.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import (
    CHECKPOINT_DAYS,
    ExitReason,
    placement_referral_error,
    Placement,
    RetentionCheck,
    RetentionStatus,
)


class PlacementError(ValidationError):
    """A refused placement operation."""


@transaction.atomic
def record_placement(
    *, case, employer_name, sector, placement_type, placement_date, recorded_by, source_referral=None, **fields
):
    """Record a youth into work, and open her retention checkpoints."""
    # §4.7 placements come from a referral, and which referrals is a flag on the
    # category row. One predicate, shared with the serializer and `clean()`.
    problem = placement_referral_error(source_referral, case)
    if problem:
        raise PlacementError({"source_referral": problem})

    placement = Placement(
        case=case,
        employer_name=employer_name,
        sector=sector,
        placement_type=placement_type,
        placement_date=placement_date,
        recorded_by=recorded_by,
        source_referral=source_referral,
        **fields,
    )
    placement.full_clean()
    placement.save()

    open_checkpoints(placement)
    _mark_case_placed(placement)
    case.touch()
    return placement


def open_checkpoints(placement):
    """The three §4.7 checks, dated from the placement.

    Idempotent — `get_or_create` on (placement, checkpoint), backed by a unique
    constraint — so a backfill over existing placements cannot double the queue.
    """
    created = []
    for checkpoint in CHECKPOINT_DAYS:
        check, made = RetentionCheck.objects.get_or_create(
            placement=placement,
            checkpoint=checkpoint,
            defaults={"due_date": placement.due_date_for(checkpoint)},
        )
        if made:
            created.append(check)
    return created


def _mark_case_placed(placement):
    """Derive the case status from the placement.

    Same one-way rule the referral state machine applies, and for the same
    reason: `PLACED` is also a judgement a case manager may set by hand (§4.2),
    and a cascade that could clear it would lose a human decision.
    """
    from apps.cases.models import CaseStatus

    case = placement.case
    if case.case_status != CaseStatus.PLACED:
        case.case_status = CaseStatus.PLACED
        case.save(update_fields=["case_status", "last_activity_date", "updated_at"])


@transaction.atomic
def record_check(check, *, status, actor, checked_on=None, note=""):
    """Answer one checkpoint.

    `UNREACHABLE` is a real answer and is recorded as one. Reporting it as "not
    retained" would overstate loss; reporting it as retained would overstate
    success. The dashboards band it separately.
    """
    if status == RetentionStatus.PENDING:
        raise PlacementError({"status": _("Say what the check found.")})
    if actor is None:
        raise PlacementError({"checked_by": _("A retention check needs the name of whoever made it.")})

    check.status = status
    check.checked_on = checked_on or date.today()
    check.checked_by = actor
    check.note = note
    check.full_clean()
    check.save()

    # An exited answer is a fact about the placement, not only about the check.
    # Leaving the placement open would keep the later checkpoints in the queue
    # and count her as employed in the retention figure.
    if status == RetentionStatus.EXITED and check.placement.exit_date is None:
        raise PlacementError(
            _("Record the exit on the placement itself — the date and the reason — and the checks will close with it.")
        )

    check.placement.case.touch()
    return check


@transaction.atomic
def record_exit(placement, *, exit_date, exit_reason, actor, note=""):
    """The youth has left the placement.

    Closes the checkpoints that have not been answered: once she has left,
    "still there at 90 days" is answered, and leaving them pending would keep
    calling somebody about a job that ended.
    """
    if placement.exit_date is not None:
        raise PlacementError(_("This placement already has an exit recorded."))
    if not exit_reason:
        raise PlacementError({"exit_reason": _("Record why the youth left the placement.")})

    placement.exit_date = exit_date
    placement.exit_reason = exit_reason
    placement.exit_note = note
    placement.full_clean()
    placement.save()

    for check in placement.retention_checks.pending():
        # A checkpoint that fell due *before* she left was genuinely retained at
        # that point and is answered as such; one that had not yet fallen due is
        # answered from the exit. Both are inferences the exit date supports, and
        # the actor recorded is whoever entered the exit.
        check.status = RetentionStatus.RETAINED if placement.held_at(check.checkpoint) else RetentionStatus.EXITED
        check.checked_on = exit_date
        check.checked_by = actor
        check.note = str(_("Answered from the recorded exit."))
        check.save()

    placement.case.touch()
    return placement


def retention_inputs(placements, checkpoint, as_of=None):
    """`(retained, answered, unreachable, due)` at one checkpoint.

    Four numbers rather than a rate, so the caller applies the dashboard's
    banding. The denominator is **answered** checks, not placements: a
    checkpoint nobody has made yet is not a youth who left, and dividing by
    every placement would report a retention rate that falls every time a new
    placement is recorded.
    """
    as_of = as_of or date.today()
    checks = RetentionCheck.objects.filter(placement__in=placements, checkpoint=checkpoint, due_date__lte=as_of)
    retained = checks.filter(status=RetentionStatus.RETAINED).count()
    unreachable = checks.filter(status=RetentionStatus.UNREACHABLE).count()
    answered = checks.exclude(status=RetentionStatus.PENDING).count()
    return retained, answered, unreachable, checks.count()


def reportable_retention_inputs(placements, as_of=None):
    """The anchor the parent operation reports on — OQ-9, settled 2026-08-18.

    "Wage-employed three months after programme exit, unsubsidised."

    Two things separate it from the 90-day operational check: subsidised
    placements are excluded, and the clock runs from **programme exit** rather
    than from the placement. Where a case has no closed date the placement date
    stands in, and the figure says so — an approximation that is named is worth
    more than a blank, but only if it is named.
    """
    as_of = as_of or date.today()
    eligible = placements.unsubsidised()
    retained, answered, unreachable, _due = retention_inputs(eligible, 90, as_of=as_of)
    return {
        "retained": retained,
        "answered": answered,
        "unreachable": unreachable,
        "excluded_subsidised": placements.filter(is_subsidised=True).count(),
    }


def exit_disposition(placements):
    """Where youth went when they left, grouped by whether it was a step up.

    §4.7's exit reason as an enum (OQ-5) exists for this: "left for a better
    job" and "dismissed" are opposite results, and a text field could not tell
    a report which had happened.
    """
    exited = placements.exclude(exit_date__isnull=True)
    by_reason = {}
    for reason, label in ExitReason.choices:
        count = exited.filter(exit_reason=reason).count()
        if count:
            by_reason[reason] = {"label": str(label), "count": count}
    upward = sum(by_reason.get(reason, {}).get("count", 0) for reason in ExitReason.voluntary_upward())
    return {"total_exits": exited.count(), "by_reason": by_reason, "upward": upward}


def backfill_from_referral_outcomes(queryset=None, actor=None):
    """Report which placement outcomes have no placement record yet.

    Deliberately a **report, not a write**. §4.7 marks employer, sector,
    placement type and date all required, and a referral outcome carries none of
    them: a row created here would be four invented fields wearing the authority
    of a record. The same rule the alert engine follows — detection never
    creates case data.
    """
    from apps.referrals.models import Referral

    referrals = queryset if queryset is not None else Referral.objects.youth_side()
    outcomes = referrals.placements()
    with_record = set(
        Placement.objects.filter(source_referral__in=outcomes).values_list("source_referral_id", flat=True)
    )
    missing = [referral for referral in outcomes if referral.pk not in with_record]
    return {"outcomes": outcomes.count(), "with_record": len(with_record), "missing": missing}
