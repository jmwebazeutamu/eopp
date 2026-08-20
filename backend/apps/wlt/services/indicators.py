"""Indicator formulas — the whole of `DEFINITIONS.md`, in one place.

**None of these formulas exist in the source handbook.** It names the indicators
and leaves them undefined. These are the definitions the module implements, and
the reason they live in one module is the reason the handoff wrote them down: a
rule applied in four places is four rules, and the one that drifts is always the
one nobody is looking at. Do not let a reporting request quietly introduce a
second version of any of them — change it here, and every consumer moves.

Two properties run through all of it:

* **Denominators are historical.** Attendance and compliance measure against the
  roster as it stood on each meeting date (`Group.roster_on`), never the roster
  today. A woman who joined in month 6 does not make months 1 to 5 look worse.
* **Bylaws are historical too.** The contribution a meeting is measured against
  is the one in force on that meeting's date, not the one in force now.

A value above 100% is a **data-quality alarm**, not a rounding artefact: it means
something was recorded for someone off the roster on that date. It is reported as
it comes out, never clamped.
"""

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .. import policy
from ..models import (
    AttendanceStatus,
    EntryType,
    GroupStatus,
    LedgerAccount,
    LinkageStatus,
    Loan,
    LoanStatus,
    MeetingCadence,
    MeetingStatus,
    RiskReason,
)

ZERO = Decimal("0")


def _pct(numerator, denominator):
    """A percentage to one decimal place, or None when there is nothing to divide.

    None is not zero. A group with no closed meetings has no attendance rate;
    reporting 0% would say its members stopped coming, which is a different and
    much worse claim than "not measurable yet".
    """
    if not denominator:
        return None
    value = (Decimal(numerator) * 100) / Decimal(denominator)
    return value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


@dataclass
class GroupIndicators:
    """Everything the gates, the readiness card and the reporting views read.

    Computed together because they share the same window, roster walk and ledger
    scan; computing them separately turned one query per group into nine.
    """

    group_id: str
    as_of: str

    meetings_held_total: int = 0
    meetings_held_in_window: int = 0
    meetings_due_in_window: int = 0
    meeting_adherence_pct: Decimal | None = None

    attendances_present: int = 0
    attendances_expected: int = 0
    attendance_pct: Decimal | None = None

    members_current: int = 0
    members_compliant: int = 0
    savings_compliance_pct: Decimal | None = None

    fund_etb: Decimal = ZERO
    social_fund_etb: Decimal = ZERO
    bank_balance_etb: Decimal = ZERO
    cash_balance_etb: Decimal = ZERO

    loans_outstanding_etb: Decimal = ZERO
    loans_at_risk_etb: Decimal = ZERO
    par30_pct: Decimal | None = None
    completed_loan_cycles: int = 0
    loans_delinquent: int = 0

    fund_weeks_of_contribution: Decimal | None = None
    weeks_since_phase_entry: int | None = None
    last_meeting_on: str | None = None
    days_since_last_meeting: int | None = None
    is_dormant: bool = False
    has_treasurer: bool = False
    social_fund_active: bool = False
    risk_reasons: list = field(default_factory=list)

    def as_snapshot(self):
        """JSON-safe, for freezing into a decision record."""
        return {key: (str(value) if isinstance(value, Decimal) else value) for key, value in asdict(self).items()}


def compute(group, as_of=None, policy_set=None):
    """Every indicator for one group, as at `as_of`.

    Deliberately one function rather than nine: the gates need all of them, the
    readiness card shows all of them, and each one on its own would re-walk the
    same meetings.
    """
    as_of = as_of or timezone.localdate()
    policy_set = policy_set or policy.PolicySet(location=group.kebele, on_date=as_of)

    window = policy_set.get_int("indicator.rolling_meetings", 12)
    bylaw = group.bylaw_on(as_of) or group.current_bylaw
    cadence_days = bylaw.cadence_days if bylaw else MeetingCadence.days(MeetingCadence.WEEKLY)

    result = GroupIndicators(group_id=str(group.pk), as_of=as_of.isoformat())

    closed = list(
        group.meetings.filter(status=MeetingStatus.CLOSED, held_on__lte=as_of)
        .order_by("-held_on")
        .prefetch_related("attendance")
    )
    result.meetings_held_total = len(closed)
    # The attendance and compliance window is the last N *meetings*, per
    # DEFINITIONS.md: those rates describe who turned up when the group met, and
    # a group that met four times this quarter should be judged on those four.
    recent = closed[:window]

    if closed:
        result.last_meeting_on = closed[0].held_on.isoformat()
        result.days_since_last_meeting = (as_of - closed[0].held_on).days

    # -- meeting adherence -------------------------------------------------
    #
    # "Due" comes from the group's own bylaw cadence in force at the time, not
    # from a global default: a weekly group and a monthly group are measured
    # against their own schedules, and comparing them against one number would
    # make every monthly group look derelict.
    if group.activated_on:
        window_span_days = window * cadence_days
        window_start = max(group.activated_on, as_of - timedelta(days=window_span_days))
        elapsed_days = (as_of - window_start).days
        result.meetings_due_in_window = max(0, elapsed_days // cadence_days)
        # Counted by *date*, not by taking the last twelve meetings whenever
        # they happened. Those are different numbers the moment a group stops
        # meeting: its last twelve are still twelve, so adherence would read
        # 100% for a group that has not met since March. Adherence is held over
        # due within a period, and the numerator has to live in that period.
        held_in_window = sum(1 for meeting in closed if meeting.held_on >= window_start)
        result.meetings_held_in_window = held_in_window
        result.meeting_adherence_pct = _pct(held_in_window, result.meetings_due_in_window)

    # -- attendance --------------------------------------------------------
    expected = 0
    present = 0
    roster_by_meeting = {}
    for meeting in recent:
        roster = set(group.roster_on(meeting.held_on).values_list("person_id", flat=True))
        roster_by_meeting[meeting.pk] = roster
        expected += len(roster)
        present += sum(1 for row in meeting.attendance.all() if row.status in AttendanceStatus.counts_as_attending())
    result.attendances_expected = expected
    result.attendances_present = present
    result.attendance_pct = _pct(present, expected)

    # -- savings compliance ------------------------------------------------
    #
    # Per member first, then the share of members who cleared the bar. A group
    # mean was rejected on purpose: one strong saver can carry a mean while half
    # the group has stopped contributing, which is exactly the failure the
    # indicator exists to catch.
    contributions = {}
    if recent:
        rows = (
            group.ledger_entries.filter(
                entry_type=EntryType.SAVINGS,
                meeting_id__in=[meeting.pk for meeting in recent],
                person_id__isnull=False,
            )
            .values("meeting_id", "person_id")
            .annotate(total=Sum("amount_etb"))
        )
        for row in rows:
            contributions[(row["meeting_id"], row["person_id"])] = row["total"]

    expected_by_member = {}
    met_by_member = {}
    for meeting in recent:
        meeting_bylaw = group.bylaw_on(meeting.held_on) or bylaw
        required = meeting_bylaw.contribution_etb if meeting_bylaw else ZERO
        for person_id in roster_by_meeting.get(meeting.pk, ()):
            expected_by_member[person_id] = expected_by_member.get(person_id, 0) + 1
            paid = contributions.get((meeting.pk, person_id), ZERO)
            if paid >= required:
                met_by_member[person_id] = met_by_member.get(person_id, 0) + 1

    member_threshold = policy_set.get_int("indicator.member_compliance_pct", 90)
    compliant = 0
    for person_id, due in expected_by_member.items():
        rate = _pct(met_by_member.get(person_id, 0), due)
        if rate is not None and rate >= member_threshold:
            compliant += 1

    result.members_current = group.current_members.count()
    result.members_compliant = compliant
    result.savings_compliance_pct = _pct(compliant, len(expected_by_member))

    # -- the fund ----------------------------------------------------------
    ledger = group.ledger_entries.filter(created_at__date__lte=as_of)
    totals = ledger.aggregate(
        into_fund=Sum("amount_etb", filter=Q(entry_type__in=EntryType.into_the_fund())),
        disbursed=Sum("amount_etb", filter=Q(entry_type=EntryType.LOAN_DISBURSEMENT)),
        social=Sum("amount_etb", filter=Q(entry_type=EntryType.SOCIAL_FUND)),
        deposits=Sum("amount_etb", filter=Q(entry_type=EntryType.BANK_DEPOSIT)),
        withdrawals=Sum("amount_etb", filter=Q(entry_type=EntryType.BANK_WITHDRAWAL)),
        cash_in=Sum("amount_etb", filter=Q(account=LedgerAccount.CASH)),
    )
    into_fund = totals["into_fund"] or ZERO
    disbursed = totals["disbursed"] or ZERO
    result.fund_etb = into_fund - disbursed
    result.social_fund_etb = totals["social"] or ZERO
    result.social_fund_active = result.social_fund_etb > 0
    result.bank_balance_etb = (totals["deposits"] or ZERO) - (totals["withdrawals"] or ZERO)
    result.cash_balance_etb = result.fund_etb - result.bank_balance_etb

    # -- the loan book -----------------------------------------------------
    default_days = policy_set.get_int("loan.default_days_past_due", 30)
    delinquent_days = policy_set.get_int("loan.delinquent_days_past_due", 1)
    outstanding_total = ZERO
    at_risk = ZERO
    delinquent = 0
    for loan in Loan.objects.filter(group=group, status=LoanStatus.DISBURSED).prefetch_related(
        "repayments", "schedule"
    ):
        outstanding = loan.outstanding_principal_etb
        if outstanding <= 0:
            continue
        outstanding_total += outstanding
        days_late = (as_of - loan.first_unpaid_due_on).days
        if days_late >= delinquent_days:
            delinquent += 1
        if days_late > default_days:
            at_risk += outstanding
    result.loans_outstanding_etb = outstanding_total
    result.loans_at_risk_etb = at_risk
    result.loans_delinquent = delinquent
    # PAR30 is zero when there is nothing outstanding, not undefined: a group
    # with no loans has a clean book, and the P1 gate asks exactly that.
    result.par30_pct = _pct(at_risk, outstanding_total) if outstanding_total else Decimal("0.0")

    result.completed_loan_cycles = _completed_cycles(group)

    # -- fund adequacy -----------------------------------------------------
    #
    # A duration rather than a birr amount, so it stays comparable across regions
    # and needs no re-indexing for inflation. Converted to weeks by the group's
    # own cadence: twelve monthly contributions are not twelve weeks of cover,
    # and a threshold stated in weeks has to mean weeks for every group.
    #
    # This replaces the handbook's Phase 2 target of "2 to 3 months' worth of
    # total member contributions", which sits below the natural accumulation
    # floor — a weekly group of 20 at 50% compliance already holds about six
    # months' worth by month 12, so that target screens nothing.
    if bylaw and result.members_current and bylaw.contribution_etb:
        periods = result.fund_etb / (bylaw.contribution_etb * result.members_current)
        weeks = periods * Decimal(cadence_days) / Decimal(7)
        result.fund_weeks_of_contribution = weeks.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    if group.phase_entered_on:
        result.weeks_since_phase_entry = (as_of - group.phase_entered_on).days // 7

    # -- dormancy and risk -------------------------------------------------
    result.has_treasurer = group.has_treasurer
    result.is_dormant = is_dormant(group, as_of=as_of, policy_set=policy_set, cadence_days=cadence_days)
    result.risk_reasons = risk_reasons(group, result, policy_set)

    return result


def _completed_cycles(group):
    """Cycles in which every loan is fully repaid.

    A cycle is not complete because one loan closed. `sql/004` counts distinct
    `cycle_batch` among repaid loans, which credits a cycle whose other loans are
    still outstanding; this counts a cycle only when nothing in it is owing.
    """
    batches = {}
    for loan in Loan.objects.filter(group=group).values("cycle_batch", "status"):
        batches.setdefault(loan["cycle_batch"], []).append(loan["status"])
    complete = 0
    for statuses in batches.values():
        if statuses and all(status in {LoanStatus.REPAID, LoanStatus.WRITTEN_OFF} for status in statuses):
            complete += 1
    return complete


def is_dormant(group, as_of=None, policy_set=None, cadence_days=None):
    """No meeting for three times the group's own cadence, floored at 60 days.

    Weekly group: 60 days. Monthly group: 90. Computed from the group's cadence
    rather than a single number, for the same reason adherence is.
    """
    as_of = as_of or timezone.localdate()
    policy_set = policy_set or policy.PolicySet(location=group.kebele, on_date=as_of)
    if cadence_days is None:
        bylaw = group.bylaw_on(as_of) or group.current_bylaw
        cadence_days = bylaw.cadence_days if bylaw else MeetingCadence.days(MeetingCadence.WEEKLY)

    if group.status not in GroupStatus.operating():
        return False

    multiple = policy_set.get_int("risk.dormant_cadence_multiple", 3)
    floor = policy_set.get_int("risk.dormant_floor_days", 60)
    threshold = max(cadence_days * multiple, floor)

    last = group.meetings.filter(status=MeetingStatus.CLOSED).order_by("-held_on").values_list("held_on", flat=True)
    anchor = last[0] if last else group.activated_on
    if anchor is None:
        return False
    return (as_of - anchor).days > threshold


def risk_reasons(group, indicators, policy_set):
    """The at-risk trigger list from DEFINITIONS.md.

    At risk is an early warning. It is visible to the facilitator and it does
    **not** by itself move the group backwards — de-graduation is a decision with
    an approver behind it, and conflating the two would let a bad month undo a
    year of governance.
    """
    reasons = []

    floor = policy_set.get_int("risk.attendance_floor_pct", 60)
    if indicators.attendance_pct is not None and indicators.attendance_pct < floor:
        reasons.append(RiskReason.LOW_ATTENDANCE)

    ceiling = policy_set.get_int("risk.par30_ceiling_pct", 20)
    if indicators.par30_pct is not None and indicators.par30_pct > ceiling:
        reasons.append(RiskReason.HIGH_PAR)

    if not indicators.has_treasurer and group.status in GroupStatus.operating():
        reasons.append(RiskReason.NO_TREASURER)

    if _missed_two_consecutive(group, indicators, policy_set):
        reasons.append(RiskReason.MISSED_MEETINGS)

    if group.linkages.distressed().exists():
        reasons.append(RiskReason.EXTERNAL_DISTRESS)

    return reasons


def _missed_two_consecutive(group, indicators, policy_set):
    """Two cadence periods with no meeting in them.

    Inferred from the gap since the last meeting rather than from a schedule
    table: the module records meetings that happened, and a group that meets
    weekly and has not met for 15 days has missed two.
    """
    if indicators.days_since_last_meeting is None:
        return False
    bylaw = group.current_bylaw
    cadence_days = bylaw.cadence_days if bylaw else MeetingCadence.days(MeetingCadence.WEEKLY)
    return indicators.days_since_last_meeting > cadence_days * 2


def linkage_distress_reasons(group):
    """Whether any linkage on this group is distressed or defaulted.

    Kept separate from `risk_reasons` because it also runs on the cascade path,
    where the distress belongs to a CLA or a federation above the group rather
    than to the group's own linkages.
    """
    return group.linkages.filter(status__in=[LinkageStatus.DISTRESSED, LinkageStatus.DEFAULTED]).exists()
