"""Meetings, the cashbook and the loan ledger — handoff README §5, stages 3 and 5.

Everything a facilitator does in a kebele has to work with no signal, so nothing
in here requires a round trip: ids are client-generated, entries are appended,
and the only operation that needs the server is an approval, which is not a
facilitator's to give.

Three rules the whole module rests on:

* **A meeting cannot close on an unbalanced till.** The error names the
  discrepancy in birr — "counted 5,000, computed 5,200" — because a facilitator
  can find 200 birr and cannot find "a validation error".
* **Corrections are reversals.** A new row pointing at the original with a
  mandatory reason, never an edit. Members sign the paper register and the
  digital record has to be defensible against it.
* **The charge is frozen at disbursement.** Basis and rate are copied onto the
  loan, never read live from the bylaw, so a rate change in month 9 cannot
  change what an existing borrower owes.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .. import policy
from ..models import (
    Attendance,
    EntryType,
    LedgerAccount,
    LedgerEntry,
    Loan,
    LoanStatus,
    Meeting,
    MeetingStatus,
    RiskFlag,
    RiskReason,
    RiskSubjectType,
    ServiceChargeBasis,
    SyncConflict,
)

ZERO = Decimal("0.00")

# How each entry type moves the cash box. Mirrors the trigger in migration
# 0002 exactly — if one of these changes, both change, and the reconciliation
# test that runs a meeting through both paths is what says so.
CASH_EFFECT = {
    EntryType.SAVINGS: 1,
    EntryType.FINE: 1,
    EntryType.SOCIAL_FUND: 1,
    EntryType.LOAN_PRINCIPAL_REPAYMENT: 1,
    EntryType.LOAN_CHARGE_REPAYMENT: 1,
    EntryType.LOAN_DISBURSEMENT: -1,
    EntryType.BANK_DEPOSIT: -1,
    EntryType.BANK_WITHDRAWAL: 1,
    EntryType.ADJUSTMENT: 1,  # carries its own sign
    EntryType.WRITE_OFF: 0,  # moves the loan book, not the box
}


class LedgerError(ValidationError):
    """A refused ledger or meeting operation."""


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------


@transaction.atomic
def open_meeting(group, *, held_on=None, scheduled_for=None, recorded_by=None, device_id="", meeting_id=None):
    """Start a meeting record.

    Meeting numbers are sequential per group. Where two devices both record
    "meeting 13", the second is not merged and not discarded: it is kept as a
    `SyncConflict` for a facilitator to resolve with both versions in front of
    her. Financial records are never auto-merged.
    """
    held_on = held_on or timezone.localdate()
    scheduled_for = scheduled_for or held_on

    last = group.meetings.order_by("-meeting_no").values_list("meeting_no", flat=True).first()
    meeting_no = (last or 0) + 1

    fields = {"pk": meeting_id} if meeting_id else {}
    return Meeting.objects.create(
        **fields,
        group=group,
        meeting_no=meeting_no,
        scheduled_for=scheduled_for,
        held_on=held_on,
        bylaw_version=group.bylaw_on(held_on),
        opening_cash_etb=cash_balance(group),
        recorded_by=recorded_by,
        device_id=device_id,
    )


def record_conflict(group, *, entity, natural_key, payload, device_id="", detail=""):
    """Keep a record two devices disagree about, unresolved and visible."""
    return SyncConflict.objects.create(
        group=group,
        entity=entity,
        natural_key=str(natural_key),
        payload=payload,
        device_id=device_id,
        detail=detail,
    )


@transaction.atomic
def record_attendance(meeting, rows):
    """`rows` is an iterable of (person, status)."""
    if meeting.status != MeetingStatus.OPEN:
        raise LedgerError(_("This meeting is closed."))
    created = []
    for person, status in rows:
        attendance, _created = Attendance.objects.update_or_create(
            meeting=meeting, person=person, defaults={"status": status}
        )
        created.append(attendance)
    return created


def expected_cash(meeting):
    """What should be in the box when this meeting closes."""
    total = meeting.opening_cash_etb or ZERO
    for entry in meeting.ledger_entries.filter(account=LedgerAccount.CASH):
        total += Decimal(CASH_EFFECT.get(entry.entry_type, 0)) * entry.amount_etb
    return total


def cash_balance(group):
    """The group's current cash position, from the ledger alone."""
    total = ZERO
    for entry in group.ledger_entries.filter(account=LedgerAccount.CASH):
        total += Decimal(CASH_EFFECT.get(entry.entry_type, 0)) * entry.amount_etb
    return total


def close_meeting(meeting, *, counted_cash_etb, actor=None, social_time_minutes=None, social_topic=""):
    """Close on a balanced till, or refuse and say by how much.

    A failed reconciliation raises an at-risk flag: a till that does not balance
    is the earliest visible sign of a problem the indicators will not show for
    weeks.
    """
    if meeting.status != MeetingStatus.OPEN:
        raise LedgerError(_("This meeting is already closed."))

    computed = expected_cash(meeting)
    counted = Decimal(counted_cash_etb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if counted != computed:
        difference = counted - computed
        # Deliberately outside a transaction that is about to roll back. The
        # flag is the *record that this happened*, and it has to outlive the
        # refusal — wrapping the whole function in `atomic` would undo it along
        # with the close, and a till that failed to balance would leave no trace
        # at all.
        raise_risk_flag(
            meeting.group,
            RiskReason.UNBALANCED_TILL,
            detail={"meeting_no": meeting.meeting_no, "counted": str(counted), "computed": str(computed)},
        )
        raise LedgerError(
            _(
                "The till does not balance. Counted ETB %(counted)s, expected ETB %(computed)s — a difference of "
                "ETB %(difference)s. Find it before closing the meeting."
            )
            % {"counted": counted, "computed": computed, "difference": abs(difference)}
        )

    with transaction.atomic():
        if social_time_minutes is not None:
            meeting.social_time_minutes = social_time_minutes
        if social_topic:
            meeting.social_topic = social_topic

        meeting.closing_cash_etb = computed
        meeting.counted_cash_etb = counted
        meeting.status = MeetingStatus.CLOSED
        meeting.closed_at = timezone.now()
        meeting.save()

        clear_risk_flag(meeting.group, RiskReason.UNBALANCED_TILL)
    return meeting


def social_time_warning(meeting, policy_set=None):
    """Handbook 3.6 asks for 15 to 30 minutes of social discussion.

    A warning, never a block: the meeting happened, and refusing to record it
    because the discussion ran short would lose the savings too.
    """
    policy_set = policy_set or policy.PolicySet(location=meeting.group.kebele)
    minimum = policy_set.get_int("meeting.social_minutes_min", 15)
    if meeting.social_time_minutes is None or meeting.social_time_minutes >= minimum:
        return None
    return _("Social discussion ran %(actual)s minutes; the handbook asks for at least %(min)s.") % {
        "actual": meeting.social_time_minutes,
        "min": minimum,
    }


# ---------------------------------------------------------------------------
# Ledger entries
# ---------------------------------------------------------------------------


@transaction.atomic
def post_entry(
    group, *, entry_type, amount_etb, meeting=None, person=None, loan=None, account=LedgerAccount.CASH, actor=None
):
    """Append one line. There is no update path, by design."""
    amount = Decimal(amount_etb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == 0:
        raise LedgerError(_("A ledger entry cannot be for nothing."))
    if meeting is not None and meeting.status != MeetingStatus.OPEN:
        raise LedgerError(_("Entries can only be posted to an open meeting."))

    return LedgerEntry.objects.create(
        group=group,
        meeting=meeting,
        person=person,
        loan=loan,
        entry_type=entry_type,
        account=account,
        amount_etb=amount,
        created_by=actor,
    )


@transaction.atomic
def reverse_entry(entry, *, reason, actor=None, meeting=None):
    """Correct a mistake by posting its opposite, with the reason attached.

    Both rows stay. That is what makes the digital record defensible against the
    paper one a member signed: the correction is visible as a correction, not as
    a number that quietly changed.
    """
    if not reason.strip():
        raise LedgerError({"reason": _("Say what is being corrected and why.")})
    if entry.reversals.exists():
        raise LedgerError(_("This entry has already been reversed."))

    return LedgerEntry.objects.create(
        group=entry.group,
        meeting=meeting if meeting is not None else entry.meeting,
        person=entry.person,
        loan=entry.loan,
        entry_type=entry.entry_type,
        account=entry.account,
        amount_etb=-entry.amount_etb,
        reverses=entry,
        reversal_reason=reason,
        created_by=actor,
    )


@transaction.atomic
def record_savings(meeting, *, person, amount_etb, actor=None):
    """The most common operation in the module."""
    return post_entry(
        meeting.group,
        entry_type=EntryType.SAVINGS,
        amount_etb=amount_etb,
        meeting=meeting,
        person=person,
        actor=actor,
    )


# ---------------------------------------------------------------------------
# The service charge engine — backlog S5.2
# ---------------------------------------------------------------------------


def service_charge(principal_etb, basis, rate, *, months=1, outstanding_schedule=None):
    """What a loan costs the borrower, under each of the three bases.

    Open question Q4 is which basis a group uses. All three are implemented
    because the answer differs by group and the difference is large: a flat 5%
    per loan and 5% per month on a three-month loan differ by a factor of three.
    """
    principal = Decimal(principal_etb)
    rate = Decimal(rate)

    if basis == ServiceChargeBasis.FLAT_PER_LOAN:
        charge = principal * rate
    elif basis == ServiceChargeBasis.PER_MONTH:
        charge = principal * rate * Decimal(months)
    elif basis == ServiceChargeBasis.DECLINING_BALANCE:
        # Charged on what is still owed each period, which is why it needs the
        # schedule rather than the headline principal.
        balances = outstanding_schedule or [principal - (principal / Decimal(months)) * i for i in range(months)]
        charge = sum((Decimal(balance) * rate for balance in balances), ZERO)
    else:
        raise LedgerError({"basis": _("Choose how the service charge is calculated. There is no default.")})

    return charge.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def charge_label(group):
    """What this group calls it — "service charge" or "interest".

    Handbook 3.5 offers the alternative term for religious inclusivity while the
    annex loan ledger still says "Interest". The label is a per-group setting and
    applies in every surface and export; the annexes need fixing.
    """
    bylaw = group.current_bylaw
    return bylaw.service_charge_label if bylaw else str(_("service charge"))


# ---------------------------------------------------------------------------
# Loans
# ---------------------------------------------------------------------------


@transaction.atomic
def disburse_loan(
    group, *, person, principal_etb, purpose, due_on, meeting, actor=None, cycle_batch=None, purpose_note=""
):
    """Issue a loan from the group's own fund.

    Four refusals, all from the handbook and the bylaw rather than from anywhere
    in code: not before the group's tenth savings meeting, not beyond the
    concurrent-loan cap, not into the reserve buffer, and not more cash than the
    box holds.
    """
    policy_set = policy.PolicySet(location=group.kebele)
    bylaw = group.current_bylaw
    if bylaw is None:
        raise LedgerError(_("Record the group's bylaws before lending."))
    if not bylaw.service_charge_basis:
        raise LedgerError(_("The bylaws do not say how the service charge is calculated."))

    min_meetings = policy_set.get_int("loan.min_meetings_before_lending", 10)
    held = group.meetings.filter(status=MeetingStatus.CLOSED).count()
    if held < min_meetings:
        raise LedgerError(
            _("This group has held %(held)s savings meetings. Lending starts after %(needed)s.")
            % {"held": held, "needed": min_meetings}
        )

    if bylaw.max_concurrent_loans:
        outstanding = Loan.objects.filter(group=group, status=LoanStatus.DISBURSED).count()
        if outstanding >= bylaw.max_concurrent_loans:
            raise LedgerError(
                _("The bylaws allow %(max)s loans at a time and %(count)s are outstanding.")
                % {"max": bylaw.max_concurrent_loans, "count": outstanding}
            )

    principal = Decimal(principal_etb).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    available = cash_balance(group)
    reserve = ZERO
    if bylaw.reserve_buffer_pct:
        reserve = (available * Decimal(bylaw.reserve_buffer_pct) / Decimal(100)).quantize(Decimal("0.01"))
    if principal > available - reserve:
        raise LedgerError(
            _(
                "The group holds ETB %(available)s in cash, of which ETB %(reserve)s is the reserve buffer. "
                "It cannot lend ETB %(asked)s."
            )
            % {"available": available, "reserve": reserve, "asked": principal}
        )

    if cycle_batch is None:
        cycle_batch = (
            Loan.objects.filter(group=group).order_by("-cycle_batch").values_list("cycle_batch", flat=True).first() or 1
        )

    loan = Loan.objects.create(
        group=group,
        person=person,
        cycle_batch=cycle_batch,
        principal_etb=principal,
        # Frozen here, not read from the bylaw later.
        charge_basis=bylaw.service_charge_basis,
        charge_rate=bylaw.service_charge_rate or ZERO,
        purpose=purpose,
        purpose_note=purpose_note,
        due_on=due_on,
        disbursed_on=meeting.held_on,
        disbursed_at_meeting=meeting,
        approved_at_meeting=meeting,
        status=LoanStatus.DISBURSED,
    )
    post_entry(
        group,
        entry_type=EntryType.LOAN_DISBURSEMENT,
        amount_etb=principal,
        meeting=meeting,
        person=person,
        loan=loan,
        actor=actor,
    )
    return loan


@transaction.atomic
def record_repayment(loan, *, principal_etb=0, charge_etb=0, meeting=None, paid_on=None, actor=None):
    """Money back, split into principal and charge.

    Split because PAR30 is a statement about principal alone, and a repayment
    recorded as one number cannot be split afterwards.
    """
    from ..models import Repayment

    paid_on = paid_on or (meeting.held_on if meeting else timezone.localdate())
    principal = Decimal(principal_etb or 0).quantize(Decimal("0.01"))
    charge = Decimal(charge_etb or 0).quantize(Decimal("0.01"))
    if principal <= 0 and charge <= 0:
        raise LedgerError(_("A repayment has to be for something."))
    if principal > loan.outstanding_principal_etb:
        raise LedgerError(
            _("That is more principal than is outstanding (ETB %(outstanding)s).")
            % {"outstanding": loan.outstanding_principal_etb}
        )

    repayment = Repayment.objects.create(
        loan=loan, meeting=meeting, paid_on=paid_on, principal_etb=principal, charge_etb=charge
    )
    if principal:
        post_entry(
            loan.group,
            entry_type=EntryType.LOAN_PRINCIPAL_REPAYMENT,
            amount_etb=principal,
            meeting=meeting,
            person=loan.person,
            loan=loan,
            actor=actor,
        )
    if charge:
        post_entry(
            loan.group,
            entry_type=EntryType.LOAN_CHARGE_REPAYMENT,
            amount_etb=charge,
            meeting=meeting,
            person=loan.person,
            loan=loan,
            actor=actor,
        )

    if loan.outstanding_principal_etb <= 0:
        loan.status = LoanStatus.REPAID
        loan.save(update_fields=["status", "updated_at"])

    return repayment


@transaction.atomic
def write_off_loan(loan, *, approved_by, reason, on_date=None):
    """Give up on a loan, with a name against the decision."""
    on_date = on_date or timezone.localdate()
    if loan.status != LoanStatus.DISBURSED:
        raise LedgerError(_("Only a disbursed loan can be written off."))
    if approved_by is None:
        raise LedgerError(_("A write-off needs an approver."))

    outstanding = loan.outstanding_principal_etb
    loan.status = LoanStatus.WRITTEN_OFF
    loan.written_off_on = on_date
    loan.write_off_approved_by = approved_by
    loan.save(update_fields=["status", "written_off_on", "write_off_approved_by", "updated_at"])

    post_entry(
        loan.group,
        entry_type=EntryType.WRITE_OFF,
        amount_etb=outstanding,
        person=loan.person,
        loan=loan,
        actor=approved_by,
    )
    return loan


# ---------------------------------------------------------------------------
# Bank account, once a savings linkage is active — workflow W4
# ---------------------------------------------------------------------------


@transaction.atomic
def deposit_to_bank(group, *, amount_etb, meeting=None, actor=None):
    """Move cash to the bank. Two balances from here on.

    The lag between collecting at a meeting and reaching the bank branch is real
    — often days, in a woreda with one branch — so the deposit is its own dated
    entry rather than an adjustment to the closing position.
    """
    if not group.linkages.filter(linkage_type__code="savings_account", status="ACTIVE").exists():
        raise LedgerError(_("This group has no active savings account to deposit into."))
    return post_entry(group, entry_type=EntryType.BANK_DEPOSIT, amount_etb=amount_etb, meeting=meeting, actor=actor)


@transaction.atomic
def withdraw_from_bank(group, *, amount_etb, meeting=None, actor=None):
    return post_entry(group, entry_type=EntryType.BANK_WITHDRAWAL, amount_etb=amount_etb, meeting=meeting, actor=actor)


# ---------------------------------------------------------------------------
# Risk flags
# ---------------------------------------------------------------------------


def raise_risk_flag(group=None, reason_code=None, detail=None, subject_type=RiskSubjectType.GROUP, subject_id=None):
    """Idempotent: one open flag per subject and reason.

    Backed by a partial unique index rather than by trust, so a nightly sweep
    that runs twice does not double the inbox.
    """
    flag, _created = RiskFlag.objects.get_or_create(
        subject_type=subject_type,
        subject_id=subject_id or group.pk,  # a cascade names the subject directly, with no group in hand
        reason_code=reason_code,
        cleared_on=None,
        defaults={"raised_on": timezone.localdate(), "detail": detail or {}},
    )
    return flag


def clear_risk_flag(group=None, reason_code=None, subject_type=RiskSubjectType.GROUP, subject_id=None):
    return RiskFlag.objects.filter(
        subject_type=subject_type,
        subject_id=subject_id or group.pk,
        reason_code=reason_code,
        cleared_on__isnull=True,
    ).update(cleared_on=timezone.localdate())
