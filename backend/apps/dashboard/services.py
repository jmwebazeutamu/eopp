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
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.utils.translation import gettext_lazy as _

from apps.cases.models import Case
from apps.referrals.models import Referral, ReferralStatus
from apps.users.models import Scope
from apps.users.permissions import scope_queryset
from apps.youth.models import Sex, Youth

# §4.7 Placement, with the 30/60/90-day retention checkpoints, is Sprint 5.
# Everything the funnel's last row and the retention card need comes from it.
RETENTION_PENDING = _("Retention needs the Placement record and its 30/60/90-day checkpoints (spec §4.7, Sprint 5).")

# The handoff's note under the confirmation-lag panel. Days from referral sent to
# partner decision.
CONFIRMATION_STANDARD_DAYS = 14


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
    """Completed referrals whose outcome the admin has flagged as a placement."""
    return referrals.filter(status=ReferralStatus.COMPLETED, outcome_type__counts_as_placement=True)


def metric_cards(youth, referrals, today):
    start, end, _label = quarter_bounds(today)

    placed = _placements(referrals)
    this_quarter = placed.filter(outcome_date__gte=start, outcome_date__lt=end).count()
    target = settings.PLACEMENT_TARGET_PER_QUARTER

    # Gender split of placements, over the whole programme rather than the
    # quarter: a quarter of placements in a 500-youth pilot is too few to read a
    # parity trend off. The registration split sits beside it as the baseline
    # the handoff asks for — a placement split only means something against it.
    by_sex = dict(
        placed.values_list("case__youth__sex")
        .annotate(n=Count("id", distinct=True))
        .values_list("case__youth__sex", "n")
    )
    placed_total = sum(by_sex.values())
    registered_female = youth.filter(sex=Sex.FEMALE).count()
    registered_total = youth.count()

    return {
        "placements_this_quarter": {
            "available": True,
            "value": this_quarter,
            # 0 means "no target agreed" (§11), not "a target of zero" — the UI
            # drops the progress bar rather than drawing 100% of nothing.
            "target": target or None,
            "percent": _percent(this_quarter, target) if target else None,
        },
        "retained_six_months": {"available": False, "reason": str(RETENTION_PENDING)},
        "gender_split": {
            "available": placed_total > 0,
            "placed_total": placed_total,
            "female": _percent(by_sex.get(Sex.FEMALE, 0), placed_total),
            "male": _percent(by_sex.get(Sex.MALE, 0), placed_total),
            "registration_female_percent": _percent(registered_female, registered_total),
        },
    }


def funnel(youth, cases, referrals):
    """Registration → placement, one row per stage the data can carry.

    Each stage counts *youth*, not events, so the rows nest: a youth referred
    three times is one youth referred. Counting referrals instead would let a
    later stage exceed an earlier one, which reads as a bug in the programme
    rather than in the query.
    """
    registered = youth.count()

    # Youth ids rather than case ids, so every row is denominated the same way.
    referred = youth.filter(case__referrals__isnull=False).distinct().count()
    confirmed = (
        youth.filter(
            case__referrals__status__in=[
                ReferralStatus.ACTIVE,
                ReferralStatus.COMPLETED,
                ReferralStatus.REPLACED,
            ]
        )
        .distinct()
        .count()
    )
    completed = youth.filter(case__referrals__status=ReferralStatus.COMPLETED).distinct().count()

    rows = [
        ("registered", _("Registered"), registered, True, ""),
        ("case_opened", _("Case opened"), cases.values("youth_id").distinct().count(), True, ""),
        ("referred", _("Referred"), referred, True, ""),
        ("partner_confirmed", _("Partner confirmed"), confirmed, True, ""),
        ("completed", _("Placed or completed"), completed, True, ""),
        ("retained", _("Retained at 6 months"), None, False, str(RETENTION_PENDING)),
    ]
    return [
        {
            "key": key,
            "label": str(label),
            "count": count,
            "percent": _percent(count, registered) if available else None,
            "available": available,
            "reason": reason,
        }
        for key, label, count, available, reason in rows
    ]


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
        "standard_days": CONFIRMATION_STANDARD_DAYS,
        "partners": [
            {
                "partner": row["receiving_partner__partner_name"],
                "days": round(row["mean"].days + row["mean"].seconds / 86400),
                "referrals": row["n"],
            }
            for row in rows
            if row["mean"] is not None
        ],
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
        .values_list("case__woreda")
        .annotate(n=Count("case__youth_id", distinct=True))
        .values_list("case__woreda", "n")
    )
    rows = [
        {
            "woreda": woreda,
            "registered": count,
            "placed": placed.get(woreda, 0),
            "rate": _percent(placed.get(woreda, 0), count),
        }
        for woreda, count in registered.items()
    ]
    # Best first, then by size, so an equal rate off three youth does not lead a
    # woreda that achieved it off three hundred.
    return sorted(rows, key=lambda row: (-row["rate"], -row["registered"]))


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
