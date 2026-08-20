"""Training enrolment operations — spec §4.5, §6.2.

Thin, because most of §4.5 is fields rather than behaviour. What is here is the
part with consequences: completing a training is what raises the onward-referral
prompt (§4.5's `triggers_onward_referral`, §6.2's last row), and a dropout has to
carry its reason or the record says nothing anybody can act on.

Every write goes through here rather than through the serializer so the case
activity stamp (§4.2 `last_activity_date`) cannot be forgotten — a youth who
started a course last week is not a stalled case, and the stall detector reads
that field.
"""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from .models import CompletionStatus, TrainingEnrolment, training_referral_error


class TrainingError(ValidationError):
    """A refused training operation."""


@transaction.atomic
def enrol(*, case, training_type, training_provider, start_date, end_date, recorded_by, **fields):
    """Put a youth into a course.

    A youth may hold more than one open enrolment — life skills and a trade
    course run together often enough that refusing it would be wrong — so there
    is no cap here. The §6.3 parallel cap governs *referrals*, which is a
    different constraint about a different thing.
    """
    # §4.5 enrolments come from a referral, and which referrals qualify is a
    # flag on the category row. One predicate, shared with the serializer and
    # with `TrainingEnrolment.clean`.
    problem = training_referral_error(fields.get("source_referral"), case)
    if problem:
        raise TrainingError({"source_referral": problem})

    enrolment = TrainingEnrolment(
        case=case,
        training_type=training_type,
        training_provider=training_provider,
        start_date=start_date,
        end_date=end_date,
        recorded_by=recorded_by,
        **fields,
    )
    enrolment.full_clean()
    enrolment.save()
    case.touch()
    return enrolment


@transaction.atomic
def complete(enrolment, *, completion_date=None, assessment_result="", certificate_status="", actor=None):
    """Finish a course.

    Sets `triggers_onward_referral`, which is what puts this youth in front of a
    case manager. The prompt itself is a **condition**, not a row — the alert job
    materialises `awaiting_onward_prompt()` — so nothing is created here beyond
    the completion.
    """
    if enrolment.completion_status != CompletionStatus.ENROLLED:
        raise TrainingError(
            _("This enrolment is already %(status)s.") % {"status": enrolment.get_completion_status_display().lower()}
        )

    enrolment.completion_status = CompletionStatus.COMPLETED
    enrolment.completion_date = completion_date or date.today()
    if assessment_result:
        enrolment.assessment_result = assessment_result
    if certificate_status:
        enrolment.certificate_status = certificate_status
    enrolment.full_clean()
    enrolment.save()
    enrolment.case.touch()
    return enrolment


@transaction.atomic
def fail_assessment(enrolment, *, assessment_result, completion_date=None, actor=None):
    """Attended to the end and did not pass.

    Deliberately not a dropout. She came; the course or the assessment did not
    work for her, and a programme that files that as a dropout will look for the
    fault in the wrong place.
    """
    if enrolment.completion_status != CompletionStatus.ENROLLED:
        raise TrainingError(_("This enrolment has already concluded."))
    if not assessment_result:
        raise TrainingError({"assessment_result": _("Record what the assessment found.")})

    enrolment.completion_status = CompletionStatus.FAILED_ASSESSMENT
    enrolment.completion_date = completion_date or date.today()
    enrolment.assessment_result = assessment_result
    enrolment.full_clean()
    enrolment.save()
    enrolment.case.touch()
    return enrolment


@transaction.atomic
def drop_out(enrolment, *, reason, dropout_date=None, actor=None):
    """Leave a course before the end, with the reason on the record."""
    if enrolment.completion_status != CompletionStatus.ENROLLED:
        raise TrainingError(_("This enrolment has already concluded."))
    if not (reason or "").strip():
        raise TrainingError({"dropout_reason": _("Record why the youth left the training.")})

    enrolment.completion_status = CompletionStatus.DROPPED_OUT
    enrolment.dropout_date = dropout_date or date.today()
    enrolment.dropout_reason = reason
    enrolment.full_clean()
    enrolment.save()
    enrolment.case.touch()
    return enrolment


@transaction.atomic
def record_attendance_rate(enrolment, *, attendance_rate, actor=None):
    """The provider's attendance figure, as a percentage.

    A number, not a register: §4.5 asks for a rate, and the platform has no
    session-level attendance. That is why CM-4's "three consecutive absences"
    condition stays uninstrumented — a rate cannot answer it, and pretending
    otherwise would put a wrong name on a right number.
    """
    enrolment.attendance_rate = attendance_rate
    enrolment.full_clean()
    enrolment.save(update_fields=["attendance_rate", "updated_at"])
    return enrolment


def completion_rate_inputs(queryset):
    """`(completed, concluded)` — the two numbers the §8.3 rate is built from.

    Returned as a pair rather than as a percentage so the caller applies the
    dashboard's banding rules to it. A completion rate over four enrolments is
    as unstable as any other rate over four, and `rules.rate` is what knows that.
    """
    return queryset.completed().count(), queryset.concluded().count()
