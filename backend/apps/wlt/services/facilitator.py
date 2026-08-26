"""The facilitator's home screen — Tier 1 of `dashboard_handoff_wlt`.

Six queue cards, and one rule shapes all of them: **every count is a list**.
The handoff is explicit that anything which cannot be tapped to produce a named
list of groups, meetings or members gets deleted, so nothing here returns a bare
number. Each card carries its rows.

**Computed on request, not read from a materialised view**, which is a departure
from the handoff's §12 "reads a view, never an application table" and is the
same decision the readiness card already records. Two reasons:

* The handoff's own acceptance criterion 6 requires closing a meeting to move
  these rows without a page reload. A view refreshed nightly cannot do that, and
  the handoff half-concedes it by asking for `mv_gate_block_reasons` to be
  "recomputed on write for the facilitator card".
* The formulas live in `services.indicators` and `services.gates`. A view that
  recomputed them would be a second implementation of the definitions — which is
  exactly what has already happened to `wlt_mv_group_compliance`, whose savings
  column disagrees with the gate that reads the service. One more copy would not
  help.

Scoped through `scope_group_queryset` like every other group read, so a
facilitator sees her own kebeles and nobody else's.
"""

from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.translation import gettext as _

from .. import policy
from ..models import (
    Group,
    GroupStatus,
    Loan,
    LoanStatus,
    Meeting,
    MeetingStatus,
    RiskFlag,
    SyncConflict,
)

#: A formation clock turns gold under this many days. The handoff's FC-5 figure.
FORMATION_WARNING_DAYS = 14


@dataclass
class Card:
    """One queue card: a heading count, and the rows behind it.

    `total` is separate from `len(rows)` on purpose — a card may cap what it
    renders while still saying how many there are. A count that silently
    truncates its own list is how a queue stops being trusted.
    """

    id: str
    total: int = 0
    rows: list = field(default_factory=list)
    note: str = ""
    #: False when the figure has no source in this schema. **Not the same as
    #: zero**, and the screen must not render it as one: a zero is a finding, an
    #: unavailable card is an absence of evidence. Same `Maybe`-shaped rule the
    #: youth dashboard uses for figures whose entity does not exist yet.
    available: bool = True

    def as_dict(self):
        return {
            "id": self.id,
            "total": self.total,
            "rows": self.rows,
            "note": self.note,
            "available": self.available,
        }


def _days(from_date, to_date):
    return (to_date - from_date).days


def meetings_to_record(groups, as_of):
    """FC-1 — the default landing card.

    Open meetings and meetings whose scheduled date has passed without one being
    held. Sorted by how late they are, because that is the order the work should
    be done in and not the order they were created.

    **Queued-but-unsynced meetings appear here too, marked.** A facilitator who
    cannot see that last Tuesday's meeting is still on her phone records it a
    second time, and two meetings on one date is the conflict `SyncConflict`
    exists to hold.
    """
    # There is no SCHEDULED status: a meeting is OPEN from the moment it is
    # created until it closes, and `scheduled_for` is what says whether it is
    # late. So "to record" is every open meeting, and the overdue ones sort
    # first rather than forming a separate query.
    open_meetings = (
        Meeting.objects.filter(group__in=groups, status=MeetingStatus.OPEN)
        .select_related("group")
        .order_by("scheduled_for")
    )

    rows = []
    for meeting in open_meetings:
        rows.append(
            {
                "meeting": str(meeting.pk),
                "group": str(meeting.group_id),
                "group_name": meeting.group.name,
                "scheduled_for": meeting.scheduled_for.isoformat(),
                "days_late": max(0, _days(meeting.scheduled_for, as_of)),
                "status": meeting.status,
                # Recorded on a device and not yet through. Marked rather than
                # hidden: she has to know it exists to not record it twice.
                "unsynced": bool(meeting.device_id and meeting.synced_at is None),
            }
        )
    rows.sort(key=lambda row: (-row["days_late"], row["group_name"]))
    return Card(id="FC-1", total=len(rows), rows=rows)


def tills_that_did_not_balance(groups, as_of):
    """FC-2 — and **the state it looks for cannot exist in this build.**

    The handoff asks for closed meetings where the count and the book disagree,
    with the discrepancy in birr. In this module that meeting cannot close: the
    `wlt_meeting_close_requires_reconciliation` trigger in migration
    `0002_ledger_invariants` refuses the update outright, comparing
    `counted_cash_etb` against the cash entries and raising if they differ by any
    amount. The invariant is deliberate — members sign the paper register, so the
    digital record has to be defensible against it — and it is older than this
    dashboard.

    So the card reports `available: false` with the reason rather than a
    permanent zero. **A zero here would be a lie of the most expensive kind**: it
    reads as "every till balanced", which is exactly what a supervision mission
    would want evidenced, and the true statement is that a till which did not
    balance was never recorded at all.

    What the handoff was reaching for is real and is elsewhere: a meeting that
    *cannot* be closed because the cash does not agree. That is a discrepancy
    somebody is standing in front of right now, and it surfaces as an open
    meeting on FC-1 with the service-layer error. Making it a queue of its own
    needs the meeting to be closable in a discrepant state, which is a change to
    the invariant and a programme decision, not a dashboard one.
    """
    return Card(
        id="FC-2",
        total=0,
        rows=[],
        available=False,
        note=str(
            _(
                "A meeting cannot be closed unless the till reconciles, so a "
                "closed meeting never carries a discrepancy. An unbalanced count "
                "keeps its meeting open — look for it on Meetings to record."
            )
        ),
    )


def repayments_overdue(groups, as_of):
    """FC-3 — two labelled blocks, never one "overdue" count.

    Delinquent is a conversation at the next meeting. Default is a PAR30 event
    that blocks a phase gate. Collapsing them into one number loses the only
    thing that decides what the facilitator does.

    Measured from `first_unpaid_due_on`, the earliest instalment the repayments
    have not covered — not the loan's final due date, which would call a loan
    current until the day it matures.
    """
    settings = policy.PolicySet()
    delinquent_at = settings.get_int("loan.delinquent_days_past_due", 1)
    default_at = settings.get_int("loan.default_days_past_due", 30)

    delinquent, defaulted = [], []
    loans = (
        Loan.objects.filter(group__in=groups, status__in=LoanStatus.owing())
        .select_related("group", "person")
        .prefetch_related("schedule", "repayments")
    )
    for loan in loans:
        outstanding = loan.outstanding_principal_etb
        if outstanding <= 0:
            continue
        past_due = _days(loan.first_unpaid_due_on, as_of)
        if past_due < delinquent_at:
            continue
        row = {
            "loan": str(loan.pk),
            "group": str(loan.group_id),
            "group_name": loan.group.name,
            "borrower": loan.person.full_name if loan.person_id else "",
            "outstanding_etb": str(outstanding),
            "days_past_due": past_due,
            "due_on": loan.first_unpaid_due_on.isoformat(),
        }
        (defaulted if past_due >= default_at else delinquent).append(row)

    for block in (delinquent, defaulted):
        block.sort(key=lambda row: -row["days_past_due"])

    return Card(
        id="FC-3",
        total=len(delinquent) + len(defaulted),
        rows=[
            {"class": "DELINQUENT", "threshold_days": delinquent_at, "loans": delinquent},
            {"class": "DEFAULT", "threshold_days": default_at, "loans": defaulted},
        ],
    )


def groups_at_risk(groups, as_of):
    """FC-4 — one row per open flag, oldest first, reason in words.

    Six reason codes exist and they are **not** collapsed into a count: "no
    treasurer since 12 May" and "attendance 54%" are different problems with
    different fixes, and a count of two says neither.

    At risk is a warning, not a demotion. The screen must not style it as
    failure — it is gold, never red, and the group has not moved backwards.
    """
    flags = (
        RiskFlag.objects.open()
        .filter(subject_type="GROUP", subject_id__in=[group.pk for group in groups])
        .order_by("raised_on")
    )
    names = {group.pk: group.name for group in groups}
    rows = [
        {
            "flag": str(flag.pk),
            "group": str(flag.subject_id),
            "group_name": names.get(flag.subject_id, ""),
            "reason_code": flag.reason_code,
            "reason": flag.get_reason_code_display(),
            "raised_on": flag.raised_on.isoformat(),
            "days_open": _days(flag.raised_on, as_of),
            # The value that raised it, so the row reads "Attendance 54%
            # (floor 60%)" rather than naming a condition and stopping.
            "detail": flag.detail or {},
        }
        for flag in flags
    ]
    return Card(id="FC-4", total=len(rows), rows=rows)


def formation_clock(groups, as_of):
    """FC-5 — drafts and constitutions running out of time.

    Both are silent deaths: a draft expires at 60 days and a constituted group
    that never held a savings meeting at 30, and nothing announces either.

    **Days remaining, not the expiry date.** "11 days left" is a decision; "18
    September" is arithmetic the reader has to do standing in a kebele.
    """
    settings = policy.PolicySet()
    windows = {
        GroupStatus.DRAFT: (settings.get_int("formation.draft_expiry_days", 60), "drafted_on"),
        GroupStatus.CONSTITUTED: (settings.get_int("formation.constituted_expiry_days", 30), "constituted_on"),
    }

    rows = []
    for status, (window, field_name) in windows.items():
        for group in groups.filter(status=status):
            started = getattr(group, field_name, None)
            if started is None:
                continue
            remaining = window - _days(started, as_of)
            rows.append(
                {
                    "group": str(group.pk),
                    "group_name": group.name,
                    "status": status,
                    "started_on": started.isoformat(),
                    "window_days": window,
                    "days_remaining": remaining,
                    # Gold under a fortnight. Expired rows are kept and marked
                    # rather than dropped: the sweep that closes them runs
                    # nightly, and until it does the group is still here.
                    "expiring_soon": remaining <= FORMATION_WARNING_DAYS,
                    "expired": remaining < 0,
                }
            )
    rows.sort(key=lambda row: row["days_remaining"])
    return Card(id="FC-5", total=len(rows), rows=rows)


def sync_and_conflicts(groups, as_of):
    """FC-6 — what is still on a device, and what arrived twice.

    **Never auto-merge financial records.** A duplicate `(group, held_on)` from
    two devices is held for a person to resolve, because the two rows are two
    accounts of the same cash count and only somebody who was there knows which
    is right.
    """
    conflicts = (
        SyncConflict.objects.filter(group__in=groups, resolved_at__isnull=True)
        .select_related("group")
        .order_by("created_at")
    )
    rows = [
        {
            "conflict": str(conflict.pk),
            "group": str(conflict.group_id),
            "group_name": conflict.group.name,
            # The duplicate's identity as the device sent it — a
            # `(group, held_on)` pair lives in `natural_key`, not in a column.
            "natural_key": conflict.natural_key,
            "entity": conflict.entity,
            "detail": conflict.detail,
            "device_id": conflict.device_id,
            "raised_at": conflict.created_at.isoformat(),
        }
        for conflict in conflicts
    ]
    return Card(
        id="FC-6",
        total=len(rows),
        rows=rows,
        note=str(_("Financial records are never merged automatically.")),
    )


def home(user, as_of=None):
    """The whole screen, in one call and one request.

    Assembled here rather than in six endpoints because the handoff's first
    acceptance criterion is one request under 100 KB — six round trips on a 3G
    connection in a woreda office is the difference between a screen that opens
    and one that does not.
    """
    from apps.users.permissions import scope_group_queryset

    as_of = as_of or timezone.localdate()
    groups = scope_group_queryset(Group.objects.select_related("kebele"), user)

    cards = [
        meetings_to_record(groups, as_of),
        tills_that_did_not_balance(groups, as_of),
        repayments_overdue(groups, as_of),
        groups_at_risk(groups, as_of),
        formation_clock(groups, as_of),
        sync_and_conflicts(groups, as_of),
    ]

    last_sync = (
        Meeting.objects.filter(group__in=groups, synced_at__isnull=False)
        .order_by("-synced_at")
        .values_list("synced_at", flat=True)
        .first()
    )

    return {
        "as_of": as_of.isoformat(),
        # On the page, always. A screen that does not say how stale it is
        # invites the reader to assume it is live — and this one is read in
        # places where it will not be.
        "last_sync_at": last_sync.isoformat() if last_sync else None,
        "groups_in_scope": groups.count(),
        "cards": [card.as_dict() for card in cards],
    }
