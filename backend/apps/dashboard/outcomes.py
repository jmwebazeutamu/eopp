"""The Sprint 5 figures — retention, training completion, placement coverage.

Four cards on the dashboards have read `available: false` since they were built,
because §4.5 Training Enrolment and §4.7 Placement did not exist. They exist now,
and this module is the one place their figures are computed. It is separate from
`services.py` for the same reason `rules.py` is: a rule applied in four places is
four rules, and the one that drifts is the disaggregated cell nobody checks.

Three things carry through every figure here:

* **A percentage never travels without its counts**, and everything goes through
  `rules.rate`, so the suppression bands apply. A retention rate over four
  answered checks is as unstable as any other rate over four.
* **Absent is not zero.** A programme with no placements recorded yet gets
  `available: false` with a reason, exactly as before. What changes is that the
  reason is now "nothing has been recorded" rather than "this is not built".
* **Coverage is stated, never assumed.** A placement record is written by a
  person, and a referral that ended in a job does not create one. The gap
  between the two is reported (`placement_coverage`) rather than hidden, because
  a retention rate over the placements somebody remembered to write up is not a
  retention rate over the programme.
"""

from django.utils.translation import gettext_lazy as _

from apps.placements.models import CHECKPOINT_DAYS, Placement, RetentionCheck
from apps.placements.services import exit_disposition, retention_inputs
from apps.training.models import TrainingEnrolment
from apps.users.permissions import scope_queryset

from .rules import rate

# OQ-9, settled 2026-08-18. Two anchors, and only one of them is reportable.
#
#   Operations: 30/60/90 days from PLACEMENT. Drives the follow-up call.
#   Reporting:  3 months after programme exit, unsubsidised. The anchor the
#               parent operation's "wage-employed 3 months after completion"
#               indicator uses, so woreda figures roll up without reconciliation.
RETENTION_LABEL = _("Retained 3 months after exit")

NO_PLACEMENTS_YET = _("Not measurable yet: no placement has been recorded.")
NO_CHECKS_YET = _("Not measurable yet: no retention check has been answered.")
NO_TRAINING_YET = _("Not measurable yet: no training enrolment has concluded.")


def scoped_outcomes(user):
    """Placements and training enrolments, narrowed to §7 before anything counts.

    An aggregate is a disclosure: "214 placements" told to somebody entitled to
    see 30 is still a leak. Scoped through the same `scope_queryset` every other
    figure uses, on the case scope, so a supervisor reads her woreda and a
    LINKED role reads what she recorded.
    """
    placements = scope_queryset(
        Placement.objects.all(),
        user,
        scope_kind="case",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    )
    trainings = scope_queryset(
        TrainingEnrolment.objects.all(),
        user,
        scope_kind="case",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
        linked_case_prefix="case__",
    )
    return placements, trainings


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def retention_card(placements, today=None):
    """The reportable retention figure, with everything it excludes stated.

    The denominator is **answered checks**, not placements. A checkpoint nobody
    has made yet is not a youth who left, and dividing by every placement would
    make the rate fall each time a new placement is recorded — a figure that
    drops when the programme succeeds.
    """
    if not placements.exists():
        return {"available": False, "reason": str(NO_PLACEMENTS_YET), "label": str(RETENTION_LABEL)}

    unsubsidised = placements.unsubsidised()
    retained, answered, unreachable, _due = retention_inputs(unsubsidised, 90, as_of=today)

    if not answered:
        return {
            "available": False,
            "reason": str(NO_CHECKS_YET),
            "label": str(RETENTION_LABEL),
            "placements": placements.count(),
        }

    return {
        "available": True,
        "label": str(RETENTION_LABEL),
        "rate": rate(retained, answered),
        # Reported beside the rate rather than folded into it. A youth nobody
        # could reach is not a youth who left, and burying her in the
        # denominator would report a loss the programme has not established.
        "unreachable": unreachable,
        "excluded_subsidised": placements.filter(is_subsidised=True).count(),
        "note": str(
            _(
                "Unsubsidised placements only, at the 90-day check. Youth who could not be reached are "
                "counted separately, not as losses."
            )
        ),
    }


def retention_by_checkpoint(placements, today=None):
    """All three §4.7 checkpoints, for the operational view.

    The 30 and 60-day figures are not reportable — the programme reports one
    anchor — but they are what tells a supervisor whether placements are failing
    early or late, which is a different intervention.
    """
    rows = []
    for checkpoint in CHECKPOINT_DAYS:
        retained, answered, unreachable, due = retention_inputs(placements, checkpoint, as_of=today)
        rows.append(
            {
                "checkpoint": checkpoint,
                "label": str(_("%(days)s days") % {"days": checkpoint}),
                "rate": rate(retained, answered) if answered else None,
                "answered": answered,
                "due": due,
                "unreachable": unreachable,
                "outstanding": due - answered,
            }
        )
    return rows


def retention_queue_size(user):
    """How many checks are due and unanswered, in this user's scope.

    The same condition the alert job materialises, so the number on the
    dashboard and the number in the inbox cannot disagree.
    """
    checks = scope_queryset(
        RetentionCheck.objects.all(),
        user,
        scope_kind="case",
        woreda_field="placement__case__woreda",
        case_manager_field="placement__case__case_manager_id",
        linked_case_prefix="placement__case__",
    )
    return checks.filter(pk__in=RetentionCheck.objects.due().values("pk")).count()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------


def training_completion(trainings):
    """§8.3's training-completion rate: completed ÷ concluded.

    The denominator is enrolments that have **ended**, of any kind. An enrolment
    still running is neither a completion nor a failure, and counting it as
    either would move the rate every time a new cohort starts.

    A failed assessment sits in the denominator and not the numerator: she
    attended, and the course did not give her the qualification it exists to
    give. Filing that as a completion would hide an assessment problem that
    belongs to the provider.
    """
    concluded = trainings.concluded().count()
    if not concluded:
        return {"available": False, "reason": str(NO_TRAINING_YET)}

    completed = trainings.completed().count()
    return {
        "available": True,
        "rate": rate(completed, concluded),
        "dropped_out": trainings.dropped_out().count(),
        "still_enrolled": trainings.open().count(),
    }


def training_pipeline(trainings):
    """Counts by status, for the trainer's own queue and the funnel."""
    return {
        "enrolled": trainings.open().count(),
        "completed": trainings.completed().count(),
        "dropped_out": trainings.dropped_out().count(),
        "concluded": trainings.concluded().count(),
        "overdue": sum(1 for enrolment in trainings.open() if enrolment.is_overdue),
    }


# ---------------------------------------------------------------------------
# Coverage — the honest half of every figure above
# ---------------------------------------------------------------------------


def placement_coverage(placements, referrals):
    """How much of the placement story has actually been written up.

    Two counts that answer different questions and must not be confused:

    * `Referral.objects.placements()` — referrals that ended in a job. A
      statement about the referral engine, and what the funnel reads.
    * `Placement` rows — placement records, which include a youth who found work
      without a referral and exclude a placement outcome nobody has written up.

    Reporting the gap is the point. A retention rate computed over the
    placements somebody remembered to record is not a retention rate over the
    programme, and a screen that showed the rate without the coverage would
    invite exactly that reading.
    """
    outcomes = referrals.placements().count()
    linked = placements.exclude(source_referral__isnull=True).values("source_referral_id").distinct().count()
    unlinked = placements.filter(source_referral__isnull=True).count()

    return {
        "referral_outcomes": outcomes,
        "with_placement_record": linked,
        "missing_placement_record": max(0, outcomes - linked),
        # Placements the referral engine never saw: a youth who found work
        # herself. Not a gap — the opposite — but it is why the two counts will
        # never be equal, and the screen should say so rather than imply an error.
        "recorded_without_referral": unlinked,
        "coverage": rate(linked, outcomes) if outcomes else None,
    }


def exits(placements):
    """Where youth went when they left — OQ-5's whole purpose.

    "Left for a better job" and "dismissed" are opposite results, and until the
    exit reason became an enum a report could not tell which had happened.
    """
    disposition = exit_disposition(placements)
    disposition["open"] = placements.open().count()
    return disposition


def outcomes_panel(user, today=None):
    """Everything Sprint 5 adds to a dashboard, in one call."""
    placements, trainings = scoped_outcomes(user)
    from .services import scoped_bases

    _youth, _cases, referrals = scoped_bases(user)

    return {
        "retention": retention_card(placements, today=today),
        "retention_by_checkpoint": retention_by_checkpoint(placements, today=today),
        "retention_queue": retention_queue_size(user),
        "training_completion": training_completion(trainings),
        "training_pipeline": training_pipeline(trainings),
        "placement_coverage": placement_coverage(placements, referrals),
        "exits": exits(placements),
    }
