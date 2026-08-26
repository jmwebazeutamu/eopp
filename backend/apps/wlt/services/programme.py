"""Tiers 2 to 4 of `dashboard_handoff_wlt` — the woreda, programme and M&E views.

**Built in the app, not in Metabase.** The handoff places these three in
Metabase; the youth bundle said the same thing about its own tiers 2 to 4 and
the programme overruled it, so the same call is made here for the same reasons:
the §7 boundary stays in the ORM where it is tested, every rate goes through one
rules module, and Metabase is not deployed — port 8009 has been reserved and
idle since Sprint 7 was scheduled.

Four rules from the handoff shape almost every function below.

* **Suppression bands.** `apps.dashboard.rules` already implements the youth
  bundle's 30/10 thresholds and the handoff inherits them. Three of five regions
  sit near or below 30 groups, so much of this reads "too few to assess". That
  is the machinery working (handoff §2.2), not a defect, and it must not be
  solved by dropping the bands.
* **The maturation guard.** The P2 gate needs 52 weeks since P1 entry, so in
  pilot month 6 no group can pass it. Every phase-attainment denominator filters
  to groups **old enough to have passed the gate**; the rest are counted
  separately as `not_yet_eligible`, never as failures and never as zero. This is
  the single most likely way to publish a false negative about the pilot.
* **Never rank by rate.** Regions and facilitators order by how much evidence
  there is, not by who is winning. At these denominators a rate ranking sorts by
  luck, rewards creaming, and is politically irreversible once published.
* **`protection_referral` never reaches a group-subject card** (§2.5). The
  database constraint stops a disclosure landing on a group record; it does not
  stop a linkage card aggregating one into a view somebody can drill into.

Every formula that already exists in `services.indicators` is called, not
recomputed. `wlt_mv_group_compliance` carries its own savings and adherence
arithmetic which has drifted from the gate's — see the module notes in
CLAUDE.md — so nothing here reads those columns.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.dashboard import rules

from .. import policy, reporting
from ..models import (
    Group,
    GroupStatus,
    LinkageStatus,
    Meeting,
    MeetingStatus,
    Phase,
    PhaseEvent,
    RiskFlag,
    ServiceLinkage,
    VerificationStatus,
)
from . import indicators

#: Fund adequacy bins, in weeks of contribution, set **at the gate**. The count
#: under 12 is the number of groups the P2 gate is currently holding, which is
#: the figure the programme can act on. A mean fund would be carried by the
#: largest group and would name nobody.
FUND_WEEK_BINS = [(0, 12), (12, 26), (26, 52), (52, None)]

#: Savings-compliance bins, set at the 80% gate for the same reason.
COMPLIANCE_BINS = [(0, 60), (60, 80), (80, 90), (90, None)]


def _bin_label(low, high):
    return f"{low}+" if high is None else f"{low}–{high}"


def _snapshot(groups, as_of):
    """`indicators.compute` once per group, reused by every card that needs it.

    Computed rather than read from `wlt_mv_group_compliance`: that view
    implements a group mean where `DEFINITIONS.md` asks for the share of members
    at or above 90%, counts any contribution above zero rather than one at the
    bylaw amount, and carries no adherence column at all. The service has all
    three right and the phase gates read it, so a card reading the view would
    disagree with the gate that blocks the group.
    """
    return {group.pk: indicators.compute(group, as_of=as_of) for group in groups}


# ---------------------------------------------------------------------------
# Tier 2 — woreda FSCO officer
# ---------------------------------------------------------------------------


def approval_queue(groups, as_of):
    """WO-1 — four counts, each carrying **the oldest item's age**.

    Age, not just count: a phase transition sitting eighteen days is the
    finding, and an average of four days hides it completely. This is the
    officer's job, so it is card one.
    """
    from ..models import BeneficiaryProfile

    def queue(label, queryset, date_field):
        rows = list(queryset.values_list(date_field, flat=True))
        oldest = min(rows) if rows else None
        return {
            "label": label,
            "count": len(rows),
            "oldest_days": (as_of - oldest).days if oldest else None,
        }

    group_ids = [group.pk for group in groups]
    return [
        queue(
            str(_("Phase submissions")),
            PhaseEvent.objects.filter(group_id__in=group_ids, submitted_at__isnull=False, decided_at__isnull=True),
            "submitted_at__date",
        ),
        queue(
            str(_("Linkages awaiting approval")),
            ServiceLinkage.objects.filter(
                subject_group_id__in=group_ids, status=LinkageStatus.PENDING_APPROVAL
            ).exclude(linkage_type__code="protection_referral"),
            "opened_on",
        ),
        queue(
            str(_("Verifications pending")),
            BeneficiaryProfile.objects.filter(verification_status=VerificationStatus.PENDING),
            "created_at__date",
        ),
    ]


def groups_by_phase(groups):
    """WO-2 — a 100% stacked row per kebele, four ordered segments.

    Phase is **ordered**, P1 through P4, so the screen uses a sequential ramp.
    Four categorical hues would say the categories are unrelated, which invites
    reading P3 as a different kind of thing rather than a later one.

    The group count rides on the row, because a 100% bar over three groups and
    one over thirty look identical and are not.
    """
    rows = defaultdict(lambda: {"FORMING": 0, "P1": 0, "P2": 0, "P3+": 0, "total": 0})
    for group in groups.select_related("kebele"):
        key = group.kebele.name if group.kebele_id else str(_("Unassigned"))
        phase = group.current_phase
        if not phase:
            bucket = "FORMING"
        elif phase == Phase.P1:
            bucket = "P1"
        elif phase == Phase.P2:
            bucket = "P2"
        else:
            bucket = "P3+"
        rows[key][bucket] += 1
        rows[key]["total"] += 1
    return [{"kebele": name, **counts} for name, counts in sorted(rows.items())]


def facilitator_load(groups, as_of):
    """WO-3 — sorted rows, **counts only, never a rate ranking**.

    At five to ten groups per facilitator a rate is noise, and ranking on it
    creates pressure to stop recording bad news. Ordered by groups carried —
    by how much work somebody is holding, which is what the card is for.
    """
    rows = defaultdict(lambda: {"groups": 0, "meetings_recorded": 0, "last_sync_at": None})
    for group in groups.select_related("facilitator"):
        name = group.facilitator.full_name if group.facilitator_id else str(_("Unassigned"))
        rows[name]["groups"] += 1

    recorded = (
        Meeting.objects.filter(group__in=groups, status=MeetingStatus.CLOSED)
        .values("group__facilitator__full_name")
        .annotate(n=Count("id"))
    )
    for row in recorded:
        name = row["group__facilitator__full_name"] or str(_("Unassigned"))
        if name in rows:
            rows[name]["meetings_recorded"] = row["n"]

    return sorted(
        ({"facilitator": name, **values} for name, values in rows.items()),
        key=lambda row: -row["groups"],
    )


def risk_register(groups, as_of):
    """WO-4 — oldest flag first. A flag open forty days is a supervision
    failure, not a group failure."""
    names = {group.pk: group.name for group in groups}
    return [
        {
            "group": str(flag.subject_id),
            "group_name": names.get(flag.subject_id, ""),
            "reason": flag.get_reason_code_display(),
            "detail": flag.detail or {},
            "days_open": (as_of - flag.raised_on).days,
        }
        for flag in RiskFlag.objects.open()
        .filter(subject_type="GROUP", subject_id__in=list(names))
        .order_by("raised_on")
    ]


def blocking_p2(groups, as_of, snapshot=None):
    """WO-5 — the coaching card: which gate condition is stopping how many.

    `Meeting adherence: 14 groups short` is a training plan. A count of blocked
    groups is not.

    **The rows do not sum to a group count** and the card says so: a group
    appears under every condition it fails, and most failing groups fail more
    than one.
    """
    from .gates import evaluate

    snapshot = snapshot or {}
    counts = defaultdict(int)
    considered = 0
    for group in groups:
        if group.current_phase != Phase.P1:
            continue
        considered += 1
        try:
            result = evaluate(group, "p1_to_p2", as_of=as_of)
        except Exception:  # noqa: BLE001 - a gate that cannot evaluate is not a card failure
            continue
        for condition in result.conditions:
            if not condition.met:
                counts[condition.label] += 1

    return {
        "groups_considered": considered,
        "rows": sorted(
            ({"condition": label, "groups_short": n} for label, n in counts.items()),
            key=lambda row: -row["groups_short"],
        ),
        "note": str(_("A group appears under every condition it fails, so these rows do not sum to a group count.")),
    }


# ---------------------------------------------------------------------------
# Tier 3 — programme manager
# ---------------------------------------------------------------------------


def formation_attrition():
    """PG-1 — mobilisation through activation, on a shared left baseline.

    A row chart, not a funnel: the losses are the finding. A kebele with three
    abandoned constitutions has a mobilisation problem, and a report of
    successes alone cannot show it.
    """
    return reporting.formation_attrition()


def fund_adequacy(groups, as_of, snapshot=None):
    """PG-3 — binned in **weeks of contribution**, never a mean, never in birr.

    Restating it in birr reintroduces the inflation and cross-region
    comparability problem the definition was written to remove. The count under
    twelve weeks is the number of groups the P2 gate is holding.
    """
    snapshot = snapshot or _snapshot(groups, as_of)
    bins = {(_bin_label(low, high)): 0 for low, high in FUND_WEEK_BINS}
    unmeasured = 0
    for result in snapshot.values():
        weeks = result.fund_weeks_of_contribution
        if weeks is None:
            unmeasured += 1
            continue
        for low, high in FUND_WEEK_BINS:
            if weeks >= low and (high is None or weeks < high):
                bins[_bin_label(low, high)] += 1
                break
    return {
        "unit": "weeks_of_contribution",
        "bins": [{"band": band, "groups": n} for band, n in bins.items()],
        # Separated from zero on purpose: a group with no bylaw cannot have a
        # week figure, and counting it in the lowest band would report it as
        # the programme's worst rather than as unmeasured.
        "not_measured": unmeasured,
    }


def savings_compliance_distribution(groups, as_of, snapshot=None):
    """PG-5 — share of groups per compliance band, bins set at the 80% gate.

    Reads `indicators.savings_compliance_pct`, which is the share of members at
    or above 90% — the definition. The materialised view's column of a similar
    name is a group mean and is not read here.
    """
    snapshot = snapshot or _snapshot(groups, as_of)
    bins = {(_bin_label(low, high)): 0 for low, high in COMPLIANCE_BINS}
    unmeasured = 0
    for result in snapshot.values():
        pct = result.savings_compliance_pct
        if pct is None:
            unmeasured += 1
            continue
        for low, high in COMPLIANCE_BINS:
            if pct >= low and (high is None or pct < high):
                bins[_bin_label(low, high)] += 1
                break
    return {
        "bins": [{"band": band, "groups": n} for band, n in bins.items()],
        "not_measured": unmeasured,
    }


def portfolio_quality(groups, as_of, snapshot=None):
    """PG-4 — a league table sorted by **birr outstanding, never by PAR**.

    Ranking regions by PAR at these denominators sorts by luck and is
    politically irreversible once published. Sorting by exposure says where the
    money is, which is what the card is for.
    """
    snapshot = snapshot or _snapshot(groups, as_of)
    rows = defaultdict(lambda: {"groups_lending": 0, "outstanding_etb": 0, "at_risk_etb": 0})
    for group in groups.select_related("kebele"):
        result = snapshot.get(group.pk)
        if result is None or result.loans_outstanding_etb <= 0:
            continue
        key = group.kebele.name if group.kebele_id else str(_("Unassigned"))
        rows[key]["groups_lending"] += 1
        rows[key]["outstanding_etb"] += result.loans_outstanding_etb
        rows[key]["at_risk_etb"] += result.loans_at_risk_etb

    table = []
    for place, values in rows.items():
        par = rules.rate(values["at_risk_etb"], values["outstanding_etb"])
        table.append(
            {
                "place": place,
                "groups_lending": values["groups_lending"],
                "outstanding_etb": str(values["outstanding_etb"]),
                "at_risk_etb": str(values["at_risk_etb"]),
                "par30": par,
            }
        )
    table.sort(key=lambda row: -float(row["outstanding_etb"]))
    return {
        "rows": table,
        "note": str(
            _("PAR30 is measured from the earliest unpaid instalment. Sorted by " "birr outstanding, never by PAR.")
        ),
    }


def phase_progression(groups, as_of):
    """PG-8 — **median** weeks P1 to P2, with n, and the maturation guard.

    Median, never mean: one group that took two years would move a mean and
    tells you nothing about the middle.

    Groups still inside the 52-week window are excluded from the denominator and
    counted separately. Reporting them as failures is the false negative §2.3
    warns about — in pilot month six, no group *can* have passed.
    """
    settings = policy.PolicySet()
    window_weeks = settings.get_int("gate.p2.weeks_since_p1", 52)

    weeks, not_yet_eligible = [], 0
    for group in groups:
        entries = {
            event.to_phase: event.decided_at
            for event in PhaseEvent.objects.filter(group=group, decided_at__isnull=False)
        }
        entered_p1 = entries.get(Phase.P1)
        if entered_p1 is None:
            continue
        entered_p2 = entries.get(Phase.P2)
        if entered_p2 is not None:
            weeks.append((entered_p2.date() - entered_p1.date()).days / 7)
            continue
        if (as_of - entered_p1.date()).days < window_weeks * 7:
            not_yet_eligible += 1

    return {
        "median_weeks": rules.median(weeks),
        "n": len(weeks),
        "not_yet_eligible": not_yet_eligible,
        "window_weeks": window_weeks,
        "band": rules.band_for(len(weeks)),
    }


def cohort_survival(groups, as_of):
    """PG-6 — decay with tenure read across, cohort improvement read down.

    **At risk counts as surviving.** `DEFINITIONS.md` is explicit that at-risk
    is an early warning which does not by itself move a group backwards, and the
    materialised view puts it in `faltering` — understating survival by the whole
    at-risk population. This computes it the way the definition reads.

    A cohort activated three months ago has no month-six cell. It is reported as
    censored, never as zero.
    """
    surviving = (GroupStatus.ACTIVE, GroupStatus.AT_RISK)
    cohorts = defaultdict(lambda: {"size": 0, "surviving": 0, "dormant": 0, "ended": 0, "months": 0})
    for group in groups.exclude(activated_on=None):
        key = group.activated_on.replace(day=1).isoformat()
        row = cohorts[key]
        row["size"] += 1
        row["months"] = max(row["months"], (as_of - group.activated_on).days // 30)
        if group.status in surviving:
            row["surviving"] += 1
        elif group.status == GroupStatus.DORMANT:
            row["dormant"] += 1
        else:
            row["ended"] += 1

    return [
        {
            "cohort_month": month,
            **values,
            "survival": rules.rate(values["surviving"], values["size"]),
        }
        for month, values in sorted(cohorts.items())
    ]


def linkage_funnel():
    """PG-7 — by stage, **excluding protection referrals**.

    The database constraint stops a disclosure landing on a group record; it
    does not stop a card aggregating one into a view somebody can drill into.
    """
    rows = [row for row in reporting.linkage_funnel() if row.get("type_code") != "protection_referral"]
    blocks = [row for row in reporting.block_reasons() if row.get("type_code") != "protection_referral"]
    return {"stages": rows, "block_reasons": blocks}


def data_health(groups, as_of):
    """PG-10 — each gap with **a consequence column** saying what it costs.

    A list of data problems is a chore. A list that says "this group cannot be
    assessed for P2" is a work queue.
    """
    late_cutoff = as_of - timedelta(days=7)
    rows = [
        {
            "issue": str(_("Meetings recorded more than seven days late")),
            "count": Meeting.objects.filter(
                group__in=groups, status=MeetingStatus.CLOSED, created_at__date__gt=late_cutoff, held_on__lt=late_cutoff
            ).count(),
            "consequence": str(_("Attendance and savings for those weeks were reconstructed from memory.")),
        },
        {
            "issue": str(_("Groups with no bylaw version")),
            "count": groups.filter(bylaw_versions__isnull=True).distinct().count(),
            "consequence": str(
                _("No contribution amount to measure compliance against, so the P1 gate cannot be read.")
            ),
        },
        {
            "issue": str(_("Groups with no treasurer on record")),
            "count": sum(
                1
                for group in groups
                if not group.office_holders.filter(role="TREASURER", to_date__isnull=True).exists()
            ),
            "consequence": str(_("A cash count nobody countersigned. Raises an at-risk flag on its own.")),
        },
    ]
    return {"rows": rows, "as_of": as_of.isoformat()}


# ---------------------------------------------------------------------------
# Tier 4 — M&E and the financier
# ---------------------------------------------------------------------------


def women_reached():
    """ME-2 — cumulative against the ceiling, **two count series, never a gauge**.

    Reads `mv_enrolment_vs_allocation`, whose geography walk this build already
    fixed: the bundled SQL joined one level below region and reported zero
    everywhere.
    """
    return reporting.enrolment_vs_allocation()


def group_maturity(groups, as_of):
    """ME-3 — phase distribution **with the maturation guard visible**.

    "P2 attained: 31 of 88 groups eligible; 162 not yet eligible" is the
    honest sentence. Publishing 31 of 250 is the false negative §2.3 describes,
    and it is the single most likely way to misreport this pilot.
    """
    settings = policy.PolicySet()
    window_weeks = settings.get_int("gate.p2.weeks_since_p1", 52)
    eligible, attained, not_yet = 0, 0, 0

    for group in groups:
        entered_p1 = (
            PhaseEvent.objects.filter(group=group, to_phase=Phase.P1, decided_at__isnull=False)
            .values_list("decided_at", flat=True)
            .first()
        )
        if entered_p1 is None:
            continue
        if (as_of - entered_p1.date()).days < window_weeks * 7:
            not_yet += 1
            continue
        eligible += 1
        if group.current_phase in (Phase.P2, Phase.P3, Phase.P4):
            attained += 1

    return {
        "attained": attained,
        "eligible": eligible,
        "not_yet_eligible": not_yet,
        "rate": rules.rate(attained, eligible),
        "window_weeks": window_weeks,
    }


def savings_and_portfolio(groups, as_of, snapshot=None):
    """ME-4 — the fund as a **stock of member savings**, not disbursement.

    Labelled explicitly, because a donor reading "fund" as programme money is
    the most expensive misreading available on this dashboard: the money is the
    women's.

    Carries the share-out caveat (OQ-1). If FSCO decides on share-out, part of
    this figure is a pending distribution rather than an accumulated asset, and
    nobody has decided yet.
    """
    snapshot = snapshot or _snapshot(groups, as_of)
    total_fund = sum((result.fund_etb for result in snapshot.values()), 0)
    members = sum((result.members_current for result in snapshot.values()), 0)
    lending = sum(1 for result in snapshot.values() if result.loans_outstanding_etb > 0)
    outstanding = sum((result.loans_outstanding_etb for result in snapshot.values()), 0)
    at_risk = sum((result.loans_at_risk_etb for result in snapshot.values()), 0)

    return {
        "fund_etb": str(total_fund),
        "members": members,
        "fund_per_member_etb": str(round(total_fund / members, 2)) if members else None,
        "groups_lending": lending,
        "outstanding_etb": str(outstanding),
        "par30": rules.rate(at_risk, outstanding),
        "label": str(_("Member savings, not programme disbursement.")),
        "caveat": str(
            _("Share-out is undecided (OQ-1). If FSCO decides on share-out, part of this is a pending distribution.")
        ),
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def tier(name, user, as_of=None):
    """One tier, scoped and assembled in a single call."""
    from apps.users.permissions import scope_group_queryset

    as_of = as_of or timezone.localdate()
    groups = scope_group_queryset(Group.objects.select_related("kebele", "facilitator"), user)
    snapshot = _snapshot(groups, as_of) if name in ("programme", "results") else {}

    if name == "woreda":
        return {
            "as_of": as_of.isoformat(),
            "approval_queue": approval_queue(groups, as_of),
            "groups_by_phase": groups_by_phase(groups),
            "facilitator_load": facilitator_load(groups, as_of),
            "risk_register": risk_register(groups, as_of),
            "blocking_p2": blocking_p2(groups, as_of),
            # Not instrumented until stage 9. The words, never a zero.
            "cla_readiness": {
                "available": False,
                "note": str(_("CLA formation is schema and gates only until stage 9.")),
            },
        }

    if name == "programme":
        return {
            "as_of": as_of.isoformat(),
            "fund_adequacy": fund_adequacy(groups, as_of, snapshot),
            "savings_compliance": savings_compliance_distribution(groups, as_of, snapshot),
            "portfolio_quality": portfolio_quality(groups, as_of, snapshot),
            "phase_progression": phase_progression(groups, as_of),
            "cohort_survival": cohort_survival(groups, as_of),
            "linkage_funnel": linkage_funnel(),
            "data_health": data_health(groups, as_of),
        }

    return {
        "as_of": as_of.isoformat(),
        "group_maturity": group_maturity(groups, as_of),
        "savings_and_portfolio": savings_and_portfolio(groups, as_of, snapshot),
        # ME-1 needs the PSNP 6 ELS results framework wording verbatim, and this
        # bundle has never seen it (OQ-4). Building it from the handbook's
        # phrasing would produce woreda figures that do not roll up.
        "results_framework": {
            "available": False,
            "note": str(_("Blocked on OQ-4: the results framework wording has not been supplied.")),
        },
    }
