"""The six work queues behind the case manager dashboard — CM-1 to CM-6.

`CASE_MANAGER_DASHBOARD.md` §5. Two rules shape every function here:

* **Nothing bypasses `scoping`.** Every `<Model>.objects` expression names
  `scoped_cases(` or `scoped_referrals(` in the same statement, and a test walks
  this module's AST to prove it.
* **Every number is a list.** §2: "Nothing that cannot be clicked to produce a
  list of named youth. If a number does not link somewhere, delete it." Each
  queue returns rows, and the counts on the screen are counts *of* those rows.

No percentages anywhere on this tier — a caseload of 80-200 is far below the
n = 30 stability floor once disaggregated, and a rate is not an action.
"""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db.models import Count, DurationField, ExpressionWrapper, F, IntegerField, Max, Q, Value
from django.db.models.functions import ExtractDay
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.alerts.models import Alert, AlertStatus, AlertType
from apps.cases.models import CaseStatus
from apps.referrals.models import ConfirmationStatus, ReferralStatus

from .rules import confirmation_threshold_days
from .scoping import scoped_cases, scoped_referrals

# Workflow order, not size order. A status distribution sorted by count becomes
# unreadable across time because the rows swap places (§5, CM-3).
STATUS_ORDER = [
    CaseStatus.ACTIVE,
    CaseStatus.REFERRAL_PENDING,
    CaseStatus.STALLED,
    CaseStatus.PLACED,
    CaseStatus.EXITED,
]

# The one-line reason shown against each alert, so the row says what to do rather
# than naming an enum. Keyed by the alert's own type.
ALERT_REASON = {
    AlertType.STALL: _("Case stalled — no recent activity"),
    AlertType.REFERRAL_CONFIRMATION_OVERDUE: _("Referral unconfirmed — partner has not responded"),
    AlertType.FOLLOW_UP_DUE: _("Follow-up call due"),
    AlertType.ONWARD_REFERRAL_PROMPT: _("Referral completed — onward referral waiting on you"),
    AlertType.REPLACEMENT_REFERRAL_PROMPT: _("Referral failed — replacement not yet raised"),
    AlertType.RETENTION_CHECK_DUE: _("Retention check due"),
}


# ---------------------------------------------------------------------------
# CM-1 — Needs action today
# ---------------------------------------------------------------------------


def needs_action(user):
    """Open alerts assigned to me, past their own threshold, worst first.

    `threshold_days` is per alert type and configurable (§4.13) — the sort reads
    each alert's own recorded value, never a constant. An alert raised under a
    30-day rule is judged at 30 even if the setting has since moved.

    Two annotation steps, deliberately: `Value(today) - F("triggered_date")`
    compiles to an interval on Postgres, so subtracting the integer
    `threshold_days` from it raises "operator does not exist: interval -
    integer". `ExtractDay` converts to an integer first.
    """
    today = timezone.localdate()
    return (
        Alert.objects.filter(
            case__in=scoped_cases(user),
            status=AlertStatus.OPEN,
            assigned_to=user,
        )
        .annotate(elapsed=ExpressionWrapper(Value(today) - F("triggered_date"), output_field=DurationField()))
        .annotate(
            days_overdue=ExpressionWrapper(ExtractDay("elapsed") - F("threshold_days"), output_field=IntegerField())
        )
        .filter(days_overdue__gte=0)
        .select_related("case", "case__youth")
        .order_by("-days_overdue")
    )


# ---------------------------------------------------------------------------
# CM-2 — Referrals awaiting partner response
# ---------------------------------------------------------------------------


def awaiting_partner(user):
    """Referrals with no partner decision, oldest wait first.

    The Primero pattern: track acceptance state, not volume sent. "Referrals
    made" is the textbook vanity metric for a referral platform and appears
    nowhere on this screen — a referral costs nothing and produces nothing.

    Goes through `scoped_referrals`, not `case__in=scoped_cases()`: see that
    function for the shared-youth disclosure it prevents.
    """
    today = timezone.localdate()
    return (
        scoped_referrals(user)
        .filter(confirmation_status=ConfirmationStatus.PENDING, status=ReferralStatus.PENDING_CONFIRMATION)
        .annotate(waited=ExpressionWrapper(Value(today) - F("initiated_date"), output_field=DurationField()))
        .annotate(days_waiting=ExpressionWrapper(ExtractDay("waited"), output_field=IntegerField()))
        .order_by("-days_waiting")
    )


# ---------------------------------------------------------------------------
# CM-3 — My caseload by status
# ---------------------------------------------------------------------------


def caseload_by_status(user):
    """One query, workflow order, zero-count rows included.

    `Max(Now() - F(last_activity_date))` raises FieldError — `Now()` is a
    DateTimeField and `last_activity_date` is a DateField, so the expression has
    mixed types and no declared output_field. The local date as a `Value` avoids
    it and keeps the arithmetic in date space.
    """
    today = timezone.localdate()
    rows = (
        scoped_cases(user)
        .values("case_status")
        .annotate(
            n=Count("pk"),
            oldest=Max(ExpressionWrapper(Value(today) - F("last_activity_date"), output_field=DurationField())),
        )
    )
    by_status = {row["case_status"]: row for row in rows}
    # Stalled is the one status with a second, independent measure. §6.2 is
    # explicit that stall *detection* raises an alert and never sets the status
    # — moving a case to Stalled is a judgement, an observation about the clock
    # is not — so the two legitimately differ, and the screen showing 52 in this
    # table and 55 in the at-risk list beside it was a labelling defect rather
    # than an arithmetic one. Each row now says what it is counting.
    return [
        {
            "status": status,
            "label": CaseStatus(status).label,
            "n": by_status.get(status, {}).get("n", 0),
            "oldest_days": (by_status.get(status, {}).get("oldest") or timedelta()).days,
            "slug": status.lower(),
            "unit": str(_("cases")),
            "basis": str(_("recorded status")),
        }
        for status in STATUS_ORDER
    ]


# ---------------------------------------------------------------------------
# CM-4 — Youth at risk of dropping out
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskItem:
    case_id: UUID
    youth_name: str
    reason: str
    severity: int  # sort key, higher first
    badge: str


# §5 CM-4 lists four conditions. Three are now checkable and one is not, and the
# one that is not is named rather than quietly dropped — a card that silently
# checks three of four while calling itself the at-risk list is worse than one
# that says what it cannot see.
#
# "Left a placement with no exit reason" is now **unreachable rather than
# uninstrumented**: `placement_exit_needs_reason` is a check constraint, so a
# placement cannot be exited without one. The condition survives as a rule the
# database keeps, which is the better place for it.
UNINSTRUMENTED_RISK_CONDITIONS = [
    _("3 consecutive training absences — attendance is recorded as a rate, not per session"),
]


def caseload_basis(user):
    """Whose cases the caseload table is actually showing.

    "My caseload" is true for a case manager and false for anyone whose §7 scope
    is wider: an administrator saw 546 cases under that heading, none of which
    were theirs. The card reads this rather than assuming.
    """
    from apps.users.models import Scope

    scope = user.case_scope()
    if scope == Scope.OWN_CASELOAD:
        return {"own": True, "label": str(_("My caseload"))}
    if scope == Scope.OWN_WOREDA:
        woredas = ", ".join(user.woreda_assignment) or str(_("no woreda assigned"))
        return {"own": False, "label": str(_("Caseload in %(woredas)s") % {"woredas": woredas})}
    return {"own": False, "label": str(_("Caseload, all woredas"))}


def at_risk(user):
    """Youth who have gone quiet, worst first.

    Two of §5 CM-4's four conditions, in one query: a case with no activity past
    the stall threshold, **or** a youth nobody has managed to reach in four
    attempts. Sprint 6 added the second — the contact log is what makes a failed
    attempt a fact rather than a memory.

    Still one query rather than the contract's four-way UNION. The single
    round-trip budget is the reason, and an `OR` over two conditions on the same
    table costs one scan where a UNION costs two.
    """
    today = timezone.localdate()
    threshold = settings.STALL_ALERT_THRESHOLD_DAYS
    cutoff = today - timedelta(days=threshold)

    # CM-4's fourth condition, inlined into the scoped statement rather than
    # evaluated first. Two reasons, both enforced by tests in this app:
    #
    #  * As a subquery it compiles into the same statement, where a
    #    materialised `set()` cost a second round trip and broke the page's
    #    12-query budget.
    #  * The scoping guard walks this module's AST and refuses any `.objects`
    #    that is not narrowing a scoped base in the same statement. Here it
    #    plainly is: `scoped_cases(user)` is the base and this only narrows it.
    #
    # Bounded to the current episode: four failures last year and a
    # conversation last week is not a youth who has disappeared.
    from apps.followups.models import FollowUp

    return (
        scoped_cases(user)
        .filter(case_status__in=CaseStatus.open_statuses())
        .filter(
            Q(last_activity_date__lte=cutoff)
            | Q(
                pk__in=FollowUp.objects.cases_with_failed_attempts(
                    minimum=settings.FAILED_CONTACT_ATTEMPTS_AT_RISK, since=cutoff
                )
            )
        )
        .annotate(quiet=ExpressionWrapper(Value(today) - F("last_activity_date"), output_field=DurationField()))
        .annotate(quiet_days=ExpressionWrapper(ExtractDay("quiet"), output_field=IntegerField()))
        .order_by("-quiet_days")
    )


def to_risk_items(cases):
    """Map the queryset to the contract's dataclass, deduplicated by case.

    Deduplication keeps the highest severity. With one condition implemented
    there is nothing yet to collide, but the shape is the one the four-condition
    version needs, and severity is already the sort key.
    """
    seen: dict[UUID, RiskItem] = {}
    for case in cases:
        item = RiskItem(
            case_id=case.pk,
            youth_name=case.youth.full_name,
            reason=str(_("No activity for %(days)s days") % {"days": case.quiet_days}),
            severity=case.quiet_days,
            badge=f"{case.quiet_days}d",
        )
        current = seen.get(item.case_id)
        if current is None or item.severity > current.severity:
            seen[item.case_id] = item
    return sorted(seen.values(), key=lambda item: -item.severity)


def open_alerts_in_scope(user):
    """Open alerts on cases this user can see, whoever they are assigned to.

    CM-1 shows alerts assigned to *me*, which is right — but for a supervisor or
    an administrator that is legitimately zero while hundreds sit open on cases
    they can see. "Nothing is overdue" is then a false claim about the
    programme; the honest line is that nothing is assigned to them. This is the
    number that lets the card tell those two apart.
    """
    return Alert.objects.filter(case__in=scoped_cases(user), status=AlertStatus.OPEN).count()


def awaiting_over_threshold(user):
    """How many of the waiting referrals are past the confirmation threshold.

    CM-2's tile subtitle. Computed from the configured threshold rather than
    written into the string, so moving the setting moves the number with it.
    """
    # `gt`, not `gte`: a wait of exactly the threshold has met the standard.
    # See rules.is_overdue_for_confirmation for the boundary rule. This used
    # `gte`, so it reported one more referral than the alert engine did over the
    # same set.
    return awaiting_partner(user).filter(days_waiting__gt=confirmation_threshold_days()).count()


# ---------------------------------------------------------------------------
# CM-5 / CM-6 — the two plain numbers
# ---------------------------------------------------------------------------


def active_referrals(user):
    """Referrals currently running, and how many youth they cover.

    Two numbers because they answer different questions: 63 active referrals
    across 41 youth says something a single count does not. Deliberately not
    "referrals made" — a referral costs nothing and produces nothing, which is
    why volume-sent appears nowhere on this tier.
    """
    active = scoped_referrals(user).filter(status=ReferralStatus.ACTIVE)
    return {
        "referrals": active.count(),
        "youth": active.values("case__youth_id").distinct().count(),
    }


def week_counts(user):
    """Cases opened and closed this week. Workload sense, nothing more.

    One aggregate, not two queries — the route's query budget is 12 and this is
    the cheapest place to save one.
    """
    today = timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    return scoped_cases(user).aggregate(
        opened=Count("pk", filter=Q(opened_date__gte=monday)),
        closed=Count("pk", filter=Q(closed_date__gte=monday)),
    )


def outcomes_verified(user):
    """Outcomes this month, split into recorded and externally verified.

    The one positively-framed number on the page, and it was overstated: it
    counted `outcome_verified_by IS NOT NULL`, which only says a staff member
    signed the record off. A self-reported outcome someone signed off is still
    self-reported, so the tile read 50 where 34 had anyone but the youth behind
    them.

    Both are returned. Relabelling alone would not have been enough — the same
    conflation drove the loop-closure rate on the donor tier.
    """
    today = timezone.localdate()
    first = today.replace(day=1)
    month = scoped_referrals(user).filter(outcome_date__gte=first)
    return {
        "verified": month.externally_verified().count(),
        "recorded": month.with_recorded_outcome().count(),
    }


__all__ = [
    "needs_action",
    "awaiting_partner",
    "caseload_by_status",
    "at_risk",
    "to_risk_items",
    "week_counts",
    "outcomes_verified",
    "active_referrals",
    "awaiting_over_threshold",
    "open_alerts_in_scope",
    "RiskItem",
    "STATUS_ORDER",
    "ALERT_REASON",
    "UNINSTRUMENTED_RISK_CONDITIONS",
]
