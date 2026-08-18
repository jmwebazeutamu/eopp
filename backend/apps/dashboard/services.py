"""The programme dashboard's numbers — the handoff's screen 8.

This app has no models. It answers one question — *is the programme putting
young people into work?* — by aggregating the entities that already exist.

Two rules run through it:

* **Every figure is scoped before it is counted.** `scope_queryset` narrows each
  base queryset to the rows the caller could have listed for themselves (§7), so
  a woreda supervisor's dashboard is their woredas and nobody else's. An
  aggregate is a disclosure like any other: "4,812 registered" told to someone
  entitled to see 300 is still a leak.
* **A figure with no source is absent, not zero.** Retention at six months needs
  the Placement entity and its 30/60/90-day checkpoints (§4.7, Sprint 5). Until
  that lands the panel says so. A donor-facing 0% that means "not built yet" is
  worse than an empty panel, and a plausible invented number is worse again.

The distinction between *placed* and *completed* is configuration, not code:
`OutcomeType.counts_as_placement` is an admin flag (§9), so an outcome added
after go-live can join the headline figure without a deploy.
"""

from datetime import date

from django.conf import settings
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Min, Q
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case
from apps.referrals.models import Referral, ReferralStatus
from apps.users.models import Scope
from apps.users.permissions import scope_queryset
from apps.youth.models import Sex, Youth

from .rules import mean_days, quarter_elapsed_fraction, rate

# §4.7 Placement, with the 30/60/90-day retention checkpoints, is Sprint 5.
# Everything the funnel's last row and the retention card need comes from it.
SERVICE_START_PENDING = _("Not measurable yet: nothing has recorded the date a youth presented to the partner.")

# OQ-9 settled 2026-08-18. Two anchors, one reportable.
#
#   Operations: 30/60/90 days from PLACEMENT. Drives case manager follow-up.
#   Reporting:  3 months from programme EXIT, unsubsidised only. This is the
#               anchor UPSNJP's "wage-employed 3 months after completion"
#               indicator uses, so it rolls up without reconciliation.
#
# The build previously showed a third, "retained at 6 months", taken from a
# design mockup with no framework behind it. Dropped: three anchors produce
# three different retention rates that nobody can reconcile, and the donor
# number has to match the parent operation's definition or it cannot be quoted.
RETENTION_LABEL = _("Retained 3 months after exit")

RETENTION_PENDING = _(
    "Not measurable yet: nothing records whether a youth is still employed three months after leaving the programme."
)


# The confirmation standard, read from the one place it is configured. It used
# to be a literal 14 here while the alert engine used 7, so a referral could be
# on time on the dashboard and overdue in the work queue at the same time.
def confirmation_standard_days():
    return settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS


def _percent(part, whole):
    """Whole-number percent, guarding the empty programme."""
    return round(part * 100 / whole) if whole else 0


# ---------------------------------------------------------------------------
# Scoped bases
# ---------------------------------------------------------------------------


def scoped_bases(user):
    """The three querysets every figure is built from, already narrowed to §7.

    Youth and Case scope on their own woreda column; a case manager's caseload is
    defined by the Case either way. Referrals scope through their case, and
    deliberately use the *case* scope rather than the referral scope: this is a
    case-population dashboard, and mixing the two would let a partner-staff
    account read programme totals off their own referral list.
    """
    cases = scope_queryset(
        Case.objects.all(),
        user,
        scope_kind="case",
        woreda_field="woreda",
        case_manager_field="case_manager_id",
    )
    youth = scope_queryset(
        Youth.objects.all(),
        user,
        scope_kind="case",
        woreda_field="woreda",
        case_manager_field="case__case_manager_id",
    )
    referrals = scope_queryset(
        Referral.objects.all(),
        user,
        scope_kind="case",
        woreda_field="case__woreda",
        case_manager_field="case__case_manager_id",
    )
    return youth, cases, referrals


def scope_label(user):
    """What the reader should understand these numbers to cover."""
    scope = user.case_scope()
    if scope == Scope.ALL:
        return str(_("All woredas"))
    if scope == Scope.OWN_WOREDA:
        return ", ".join(user.woreda_assignment) or str(_("No woreda assigned"))
    if scope == Scope.OWN_CASELOAD:
        return str(_("Your caseload"))
    return str(_("No case records in scope"))


# ---------------------------------------------------------------------------
# Quarter
# ---------------------------------------------------------------------------


def quarter_bounds(today):
    """The calendar quarter `today` falls in, as (start, end_exclusive, label)."""
    quarter = (today.month - 1) // 3 + 1
    start = date(today.year, 3 * (quarter - 1) + 1, 1)
    end = date(today.year + 1, 1, 1) if quarter == 4 else date(today.year, 3 * quarter + 1, 1)
    return start, end, f"Q{quarter} {today.year}"


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------


def _placements(referrals):
    """Delegates to the one definition. See `ReferralQuerySet.placements`."""
    return referrals.placements()


def metric_cards(youth, referrals, today):
    start, end, _label = quarter_bounds(today)

    placed = _placements(referrals)
    this_quarter = (
        placed.filter(outcome_date__gte=start, outcome_date__lt=end).values("case__youth_id").distinct().count()
    )
    target = settings.PLACEMENT_TARGET_PER_QUARTER

    # Gender split of placements, over the whole programme rather than the
    # quarter: a quarter of placements in a 500-youth pilot is too few to read a
    # parity trend off. The registration split sits beside it as the baseline
    # the handoff asks for — a placement split only means something against it.
    # Distinct youth, not referrals. This counted referrals, so a youth placed
    # twice appeared twice and the card totalled 63 while the woreda table
    # beneath it totalled 59 — two placement figures contradicting each other on
    # one screen. Every placement figure is denominated in youth.
    by_sex = dict(
        placed.values("case__youth__sex")
        .annotate(n=Count("case__youth_id", distinct=True))
        .values_list("case__youth__sex", "n")
    )
    placed_total = len(referrals.placed_youth_ids())
    registered_female = youth.filter(sex=Sex.FEMALE).count()
    registered_total = youth.count()

    return {
        "placements_this_quarter": {
            "available": True,
            "value": this_quarter,
            "unit": str(UNIT_YOUTH),
            # 0 means "no target agreed" (§11), not "a target of zero" — the UI
            # drops the progress bar rather than drawing 100% of nothing.
            "target": target or None,
            "percent": _percent(this_quarter, target) if target else None,
            # Read the percentage against elapsed time, not against the whole
            # quarter, or every quarter opens with a card saying the programme
            # is failing. Day 3 of 90 at 3% of target is on track.
            "quarter_elapsed_percent": round(quarter_elapsed_fraction(today, start, end) * 100),
        },
        "retained_six_months": {"available": False, "reason": str(RETENTION_PENDING)},
        "gender_split": {
            "available": placed_total > 0,
            "placed_total": placed_total,
            "unit": str(UNIT_YOUTH),
            # Banded: a 67/33 split off three placements is noise, and printing
            # it beside a registration baseline invites exactly the parity
            # conclusion the numbers cannot support.
            "female": rate(by_sex.get(Sex.FEMALE, 0), placed_total),
            "male": rate(by_sex.get(Sex.MALE, 0), placed_total),
            "registration_female": rate(registered_female, registered_total),
        },
    }


def _median(values):
    """Whole days. No numpy for one statistic on a few hundred rows."""
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return round((ordered[middle - 1] + ordered[middle]) / 2)


# The pipeline, as one row per stage. `date_field` is the annotation that says
# when a youth reached that stage — stage *dates*, not booleans, because the
# median time spent in the previous stage is the most actionable number on the
# card and a count cannot produce it.
# `gating` marks a stage a youth must pass to reach the next one. Profiling and
# pathway assignment are not prerequisites — the referral engine will raise a
# referral without either — so they are *coverage*, not gates. Counting them as
# funnel stages would put "Referred 168" above "Profiled 0" and read as a broken
# programme rather than as a profiling gap, so no drop-off is annotated across
# them and the nesting invariant is only claimed where it holds.
STAGES = [
    ("registered", _("Registered"), _("Youth record created"), "registered_on", True),
    ("case_opened", _("Case opened"), _("Case file opened"), "case_opened_on", True),
    ("profiled", _("Profiled and eligible"), _("Profiling record complete"), "profiled_on", False),
    ("pathway", _("Pathway assigned"), _("Current pathway set"), "pathway_on", False),
    ("referred", _("Referred"), _("First referral raised"), "referred_on", True),
    ("partner_confirmed", _("Partner confirmed"), _("Referral accepted"), "confirmed_on", True),
    ("service_attended", _("Service attended"), _("Youth presented to the partner"), "attended_on", True),
    # Named for what it measures, not for an outcome. "Placed" appears three
    # times on this screen with three different denominators otherwise, and this
    # is the one a programme manager quotes in a meeting.
    (
        "closed_successfully",
        _("First referral closed successfully"),
        _("An outcome was recorded"),
        "completed_on",
        True,
    ),
]

# Units, stated on the payload rather than left to the reader. Every card that
# carries a count carries one of these: a figure whose unit is ambiguous is how
# one screen came to show three different placement totals, each defensible.
UNIT_YOUTH = _("youth")
UNIT_CASES = _("cases")
UNIT_REFERRALS = _("referrals")

PIPELINE_UNIT = UNIT_YOUTH


def funnel(youth, cases, referrals):
    """Registration → placement, with the loss at every transition.

    Each stage counts *youth*, not events, so the rows nest: a youth referred
    three times is one youth referred. Counting referrals instead would let a
    later stage exceed an earlier one, which reads as a bug in the programme
    rather than in the query.

    Drawn as a row chart on a shared left baseline rather than as a funnel, and
    annotated with the loss at each transition, because the question a programme
    manager is asking is where youth are *lost* — a funnel highlights the
    survivors and cannot show median days in stage at all.
    """
    confirmed_statuses = [ReferralStatus.ACTIVE, ReferralStatus.COMPLETED, ReferralStatus.REPLACED]

    # One pass. Each stage's date is the first time the youth reached it.
    rows = youth.annotate(
        registered_on=F("registration_date"),
        case_opened_on=Min("case__opened_date"),
        referred_on=Min("case__referrals__initiated_date"),
        confirmed_on=Min("case__referrals__confirmed_date", filter=Q(case__referrals__status__in=confirmed_statuses)),
        completed_on=Min("case__referrals__outcome_date", filter=Q(case__referrals__status=ReferralStatus.COMPLETED)),
        attended_on=Min("case__referrals__service_start_date"),
        profiled_on=Min("case__profiling_records__assessed_date"),
        pathway_on=Min(
            "case__pathway_assignments__assessment_date", filter=Q(case__pathway_assignments__is_current=True)
        ),
    ).values(
        "registered_on",
        "case_opened_on",
        "profiled_on",
        "pathway_on",
        "referred_on",
        "confirmed_on",
        "attended_on",
        "completed_on",
    )
    rows = list(rows)

    registered = len(rows)
    out = []
    previous_field = None
    last_gating = None

    for index, (key, label, sub, field, gating) in enumerate(STAGES):
        reached = [row for row in rows if row[field] is not None]
        count = len(reached)

        # Days spent in the previous stage, over the youth who cleared both.
        median_days = None
        if previous_field:
            spans = [
                (row[field] - row[previous_field]).days
                for row in reached
                if row[previous_field] is not None and row[field] >= row[previous_field]
            ]
            median_days = _median(spans)

        # OQ-1 is settled and the column exists, but nothing has written to it
        # yet. An empty column is "not instrumented", never a 100% loss.
        if key == "service_attended" and count == 0 and registered:
            out.append(
                {
                    "key": key,
                    "label": str(label),
                    "sublabel": str(sub),
                    "count": None,
                    "share": None,
                    "median_days_in_prev_stage": None,
                    "available": False,
                    "reason": str(SERVICE_START_PENDING),
                    "lost": None,
                    "gating": False,
                    "unit": str(PIPELINE_UNIT),
                }
            )
            previous_field = field
            continue

        entry = {
            "key": key,
            "label": str(label),
            "sublabel": str(sub),
            "count": count,
            # The count is always shown; the share is banded on the registration
            # denominator every row is measured against. A funnel drawn off
            # fourteen youth still draws — it just does not claim percentages.
            "share": rate(count, registered),
            "median_days_in_prev_stage": median_days,
            "available": True,
            "reason": "",
            "lost": None,
            "gating": gating,
            "unit": str(PIPELINE_UNIT),
        }
        # The loss is annotated on the row it leaves, so the reader sees where
        # the programme is losing people rather than only who survived. Only
        # between gates: a youth referred without a profiling record has not
        # been "lost" at profiling.
        if gating and last_gating is not None:
            lost = last_gating["count"] - count
            last_gating["lost"] = {"count": lost, "share": rate(lost, last_gating["count"])}
        out.append(entry)
        if gating:
            last_gating = entry
        previous_field = field

    out.append(
        {
            "key": "retained",
            "label": str(RETENTION_LABEL),
            "sublabel": str(_("Still in the same placement")),
            "count": None,
            "share": None,
            "median_days_in_prev_stage": None,
            "available": False,
            "reason": str(RETENTION_PENDING),
            "lost": None,
            "gating": True,
            "unit": str(PIPELINE_UNIT),
        }
    )
    return out


def confirmation_lag(referrals):
    """Days from referral sent to partner decision, averaged per partner.

    Only referrals that actually got a decision are averaged. Including the ones
    still waiting would score a partner who has never replied as fast, because a
    null lag is not a short lag.
    """
    lag = ExpressionWrapper(F("confirmed_date") - F("initiated_date"), output_field=DurationField())
    rows = (
        referrals.filter(confirmed_date__isnull=False)
        .values("receiving_partner_id", "receiving_partner__partner_name")
        .annotate(mean=Avg(lag), n=Count("id"))
        .order_by("mean")
    )
    return {
        "standard_days": confirmation_standard_days(),
        # Ordered by the number of referrals each mean rests on, not by the mean
        # itself. Sorting by speed ranks partners by luck when the denominators
        # are this small, and a published ranking is hard to withdraw; ordering
        # by n puts the partners there is most evidence about at the top and
        # removes the ranking incentive.
        "partners": sorted(
            [
                {
                    "partner": row["receiving_partner__partner_name"],
                    "lag": mean_days(row["mean"].days + row["mean"].seconds / 86400, row["n"]),
                }
                for row in rows
                if row["mean"] is not None
            ],
            key=lambda entry: -entry["lag"]["n"],
        ),
    }


def woreda_comparison(youth, referrals):
    """Placement rate per woreda: placed youth ÷ registered youth.

    Denominated on registration rather than on referrals, because the question a
    supervisor is asking is what share of the young people they registered ended
    up in work — not how well the referrals they happened to make performed.
    """
    registered = dict(youth.values_list("woreda").annotate(n=Count("id")).values_list("woreda", "n"))
    placed = dict(
        _placements(referrals)
        .values("case__woreda")
        .annotate(n=Count("case__youth_id", distinct=True))
        .values_list("case__woreda", "n")
    )
    rows = [
        {
            "woreda": woreda,
            "unit": str(UNIT_YOUTH),
            "registered": count,
            "placed": placed.get(woreda, 0),
            "rate": rate(placed.get(woreda, 0), count),
        }
        for woreda, count in registered.items()
    ]
    # Ordered by how much evidence there is, not by who is winning. A raw
    # placement-rate ranking across woredas rewards creaming and penalises the
    # woreda taking the harder intake — and the platform holds no vulnerability
    # profile to adjust for that yet (§4.3's index is still undefined).
    return sorted(rows, key=lambda row: -row["registered"])


def alert_pressure(cases):
    """What is going wrong right now, alongside what has gone right.

    Not in the handoff's mockup, which was drawn before the Alert entity existed.
    It earns its place because the dashboard is otherwise entirely retrospective:
    a supervisor reading it should be able to see the open alerts that will
    decide next quarter's numbers, without changing screen.
    """
    from apps.alerts.models import Alert, AlertStatus, AlertType

    open_alerts = Alert.objects.filter(status=AlertStatus.OPEN, case__in=cases)
    by_type = open_alerts.values("alert_type").annotate(n=Count("id")).order_by("-n")
    return {
        "open_total": open_alerts.count(),
        "by_type": [{"type": row["alert_type"], "count": row["n"]} for row in by_type],
        "stalled_cases": cases.filter(alerts__alert_type=AlertType.STALL, alerts__status=AlertStatus.OPEN)
        .distinct()
        .count(),
    }


def programme_dashboard(user, today=None):
    """The whole screen in one response.

    One request rather than six: the brief's users are on 3G, where six round
    trips cost more than the payload does.
    """
    today = today or date.today()
    youth, cases, referrals = scoped_bases(user)
    start, end, label = quarter_bounds(today)

    return {
        "period": {"label": label, "start": start.isoformat(), "end": end.isoformat()},
        "scope_label": scope_label(user),
        "metrics": metric_cards(youth, referrals, today),
        "funnel": funnel(youth, cases, referrals),
        "confirmation_lag": confirmation_lag(referrals),
        "woredas": woreda_comparison(youth, referrals),
        "alerts": alert_pressure(cases),
    }


__all__ = [
    "programme_dashboard",
    "quarter_bounds",
    "scoped_bases",
    "scope_label",
    "funnel",
    "confirmation_lag",
    "woreda_comparison",
    "metric_cards",
    "alert_pressure",
]
