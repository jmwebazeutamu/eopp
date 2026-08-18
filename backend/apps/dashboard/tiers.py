"""Tiers 2, 3 and 4 — the supervisor, programme manager and donor dashboards.

`dashboard_handoff_youth_employment/README.md` §4-§6. The handoff puts these in
Metabase; they are built here instead, in the app. That keeps the §7 boundary in
the ORM where it is tested rather than in a BI tool's row-level security, and it
means every rate goes through `rules.py` — the handoff's own requirement that
"a question that computes a percentage inline is a review-blocking defect" is
easier to hold when there is only one place a percentage can be made.

Each tier answers one question, and the handoff's "what must NOT appear" list is
as load-bearing as the card list:

* **Tier 2, supervisor — which staff, which cases need me?** Counts, never
  per-staff rates: a rate over one case manager's caseload is noise, and it
  creates cream-skimming pressure with no compensating information.
* **Tier 3, programme manager — where is the process breaking, and for whom?**
  No live case detail, no PII.
* **Tier 4, donor — are we hitting targets?** The smallest of the four. Nothing
  that needs more than a sentence to define.

Cards whose source entity does not exist report `available: false` with a
reason. Placement (§4.7) and Training Enrolment (§4.5) are Sprint 5, and between
them they carry retention, the 90-day disposition and training completion.
"""

from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.alerts.models import Alert, AlertStatus
from apps.cases.models import CaseStatus
from apps.referrals.models import ConfirmationStatus, ReferralStatus
from apps.referrals.taxonomy import OutcomeType, ReferralCategory
from apps.youth.models import DisabilityStatus, PsnpStatus, SettlementType, Sex

from .rules import VERDICT_LABEL, age_band, band_for, funnel_verdict, median, rate, wilson_bounds

PLACEMENT_PENDING = _("Not measurable yet: placements and their follow-up checks are not recorded in the system.")
TRAINING_PENDING = _("Not measurable yet: training enrolments are not recorded in the system.")

# WS-2. §4.2 makes `case_manager` required, so "registered but never assigned"
# is not a state this schema can hold.
UNASSIGNED_PENDING = _("Not measurable yet: every case must have a case manager, so a youth cannot be left unassigned.")


def absent(reason):
    return {"available": False, "reason": str(reason)}


# ---------------------------------------------------------------------------
# Tier 2 — woreda supervisor
# ---------------------------------------------------------------------------

# WS-1: the statuses collapse to four for display. Four stacks is the practical
# ceiling — six adjacent segments cannot hold WCAG 1.4.11's 3:1 non-text
# contrast against each other.
#
# Which four matters as much as how many. The first version of this folded
# Referral Pending into "in progress" and spent two segments on terminal states
# (Placed, Closed), leaving none for the one live state a supervisor can act on.
# Awaiting partner is precisely the segment that surfaces a stranded referral
# cohort, so Placed and Exited share a segment and it gets its own.
DISPLAY_SEGMENT = {
    CaseStatus.ACTIVE: "on_track",
    CaseStatus.REFERRAL_PENDING: "awaiting_partner",
    CaseStatus.STALLED: "stalled",
    CaseStatus.PLACED: "closed",
    CaseStatus.EXITED: "closed",
}
SEGMENT_ORDER = ["on_track", "awaiting_partner", "stalled", "closed"]
SEGMENT_LABEL = {
    "on_track": _("On track"),
    "awaiting_partner": _("Awaiting partner"),
    "stalled": _("Stalled"),
    "closed": _("Placed or exited"),
}


def team_caseload(cases):
    """WS-1 / WS-3 — one row per case manager: caseload, mix, and overdue count.

    Counts, never rates. The handoff is explicit that a per-staff rate at
    caseload size is noise and creates cream-skimming pressure, so the overdue
    column sits *beside* the caseload rather than being divided by it.
    """
    rows = {}
    for row in cases.values("case_manager_id", "case_manager__full_name", "case_status").annotate(n=Count("pk")):
        key = row["case_manager_id"]
        entry = rows.setdefault(
            key,
            {
                "case_manager": str(key) if key else None,
                "name": row["case_manager__full_name"] or str(_("Unassigned")),
                "total": 0,
                "segments": {segment: 0 for segment in SEGMENT_ORDER},
                "overdue": 0,
            },
        )
        entry["total"] += row["n"]
        entry["segments"][DISPLAY_SEGMENT[row["case_status"]]] += row["n"]

    # CASELOAD_CEILING was configured and nothing read it, so every case manager
    # could sit above it unremarked. §11 leaves the number unagreed, which is a
    # reason to surface the flag, not to ignore the parameter.
    ceiling = settings.CASELOAD_CEILING
    for entry in rows.values():
        entry["over_ceiling"] = entry["total"] > ceiling

    overdue = (
        Alert.objects.filter(case__in=cases, status=AlertStatus.OPEN)
        .values("case__case_manager_id")
        .annotate(n=Count("pk"))
    )
    for row in overdue:
        entry = rows.get(row["case__case_manager_id"])
        if entry:
            entry["overdue"] = row["n"]

    # Heaviest caseload first — the supervisor's question is who needs help.
    return sorted(rows.values(), key=lambda entry: -entry["total"])


def data_completeness(youth, referrals):
    """WS-6 / PM-8 — a programme widget, not an IT widget.

    Missing `failure_reason_code` is the highest-cost gap: it breaks the
    replacement-referral prompt and the partner failure breakdown at once.
    """
    total_youth = youth.count()
    closed_failed = referrals.filter(status=ReferralStatus.FAILED)
    completed = referrals.filter(status=ReferralStatus.COMPLETED)

    def row(field, missing, of, cost):
        return {
            "field": str(field),
            "missing": missing,
            "of": of,
            # Zero missing of 147 and "no records to check" are different
            # findings, and "Complete" over an empty denominator is the second
            # dressed up as the first.
            "has_records": of > 0,
            "cost": str(cost),
        }

    return [
        row(
            _("Phone number"),
            youth.filter(Q(phone_number="") | Q(phone_number__isnull=True)).count(),
            total_youth,
            _("Follow-up calls cannot be made."),
        ),
        row(
            _("Consent date"),
            youth.filter(Q(consent_date__isnull=True) | Q(consent_given=False)).count(),
            total_youth,
            _("Consent is the basis for holding the record at all."),
        ),
        row(
            _("Profiling record"),
            youth.filter(case__profiling_records__isnull=True).distinct().count(),
            total_youth,
            _("No pathway can be justified without it."),
        ),
        row(
            _("Outcome type on a completed referral"),
            completed.filter(outcome_type__isnull=True).count(),
            completed.count(),
            _("The outcome breakdown loses the referral."),
        ),
        row(
            _("Failure reason on a failed referral"),
            closed_failed.filter(failure_reason_code__isnull=True).count(),
            closed_failed.count(),
            _("Breaks the replacement prompt and the partner failure breakdown at once."),
        ),
    ]


def woreda_supervisor(youth, cases, referrals):
    from apps.alerts.models import AlertType

    team = team_caseload(cases)
    response = partner_response_times(referrals)
    medians = [row["median_days"] for row in response if row["median_days"] is not None]
    today = timezone.localdate()

    return {
        # W-5. Four of the five were already computed on the page and only
        # needed surfacing; the fifth is the ceiling flag nobody was reading.
        "tiles": {
            "open_cases": cases.filter(case_status__in=CaseStatus.open_statuses()).count(),
            "registered_without_case": youth.filter(case__isnull=True).count(),
            "overdue_actions": sum(row["overdue"] for row in team),
            "median_days_to_confirm": median(medians),
            # Externally verified, not merely recorded — the tile read 50 where
            # only 34 had anyone but the youth behind them. Both are carried so
            # the card can show what it is a subset of.
            "outcomes_verified": referrals.externally_verified().filter(outcome_date__gte=today.replace(day=1)).count(),
            "outcomes_recorded": referrals.with_recorded_outcome()
            .filter(outcome_date__gte=today.replace(day=1))
            .count(),
            "over_ceiling": sum(1 for row in team if row["over_ceiling"]),
            "caseload_ceiling": settings.CASELOAD_CEILING,
        },
        "awaiting_partner_alerts": Alert.objects.filter(
            case__in=cases, status=AlertStatus.OPEN, alert_type=AlertType.REFERRAL_CONFIRMATION_OVERDUE
        ).count(),
        # W-11. Tier 2 is live here rather than a 05:30 refresh, but a screen
        # that does not state its age invites the reader to assume it is current.
        "as_of": timezone.now().isoformat(),
        "team_caseload": team,
        "segments": [{"key": key, "label": str(SEGMENT_LABEL[key])} for key in SEGMENT_ORDER],
        "unassigned_youth": absent(UNASSIGNED_PENDING),
        # Real, and the nearest true thing to WS-2: registered with no case yet.
        "registered_without_case": youth.filter(case__isnull=True).count(),
        "partner_response": response,
        "confirmation_threshold": settings.REFERRAL_CONFIRMATION_OVERDUE_DAYS,
        "data_completeness": data_completeness(youth, referrals),
    }


# ---------------------------------------------------------------------------
# Tier 3 — programme manager
# ---------------------------------------------------------------------------


def partner_response_times(referrals):
    """WS-4 — median days from referral sent to partner decision, per partner.

    Median, not mean, and every row carries its n.
    """
    rows = {}
    for partner, initiated, confirmed, recorded_by in referrals.filter(confirmed_date__isnull=False).values_list(
        "receiving_partner__partner_name", "initiated_date", "confirmed_date", "confirmation_recorded_by_id"
    ):
        entry = rows.setdefault(partner, {"partner_answered": [], "staff_recorded": 0})
        if recorded_by is None:
            # The partner answered through their own login. Only these measure
            # partner responsiveness.
            entry["partner_answered"].append((confirmed - initiated).days)
        else:
            entry["staff_recorded"] += 1

    # A case manager may record a partner's confirmation on their behalf
    # (decided 2026-08-18). That keeps the queue moving, and it would quietly
    # destroy this card if the two were averaged together: a partner who never
    # answers would score identically to one who answers in a day, because staff
    # kept things moving for them. The median is computed over the partner's own
    # answers, and the staff-recorded count sits beside it so the reader can see
    # how much of the traffic is being carried by staff.
    out = [
        {
            "partner": partner,
            "median_days": (
                median(entry["partner_answered"]) if band_for(len(entry["partner_answered"])) != "suppressed" else None
            ),
            "n": len(entry["partner_answered"]),
            "staff_recorded": entry["staff_recorded"],
            "band": band_for(len(entry["partner_answered"])),
        }
        for partner, entry in rows.items()
    ]
    # Slowest first among those with enough evidence to judge, so the partner a
    # supervisor needs to chase is at the top. Anything the bands withheld sinks
    # to the bottom rather than being ranked on a median it does not have.
    return sorted(out, key=lambda row: (row["median_days"] is None, -(row["median_days"] or 0), -row["n"]))


def partner_performance(referrals):
    """PM-4 — the constrained league table.

    Completed ÷ (Completed + Failed), with a Wilson interval and a funnel-plot
    verdict against the overall programme rate. **Sorted by n_closed, never by
    rate.** Ranking on unstable rates sorts by luck and is politically
    irreversible once published; sorting by evidence puts the partners we know
    most about at the top and removes the ranking incentive entirely.
    """
    closed = referrals.filter(status__in=[ReferralStatus.COMPLETED, ReferralStatus.FAILED])
    rows = closed.values(
        "receiving_partner_id", "receiving_partner__partner_name", "receiving_partner__partner_type"
    ).annotate(
        n_closed=Count("pk"),
        n_completed=Count("pk", filter=Q(status=ReferralStatus.COMPLETED)),
    )
    rows = list(rows)

    total_closed = sum(row["n_closed"] for row in rows)
    total_completed = sum(row["n_completed"] for row in rows)
    overall = (total_completed / total_closed) if total_closed else None

    out = []
    for row in rows:
        verdict = funnel_verdict(row["n_completed"], row["n_closed"], overall)
        out.append(
            {
                "partner": row["receiving_partner__partner_name"],
                "partner_type": row["receiving_partner__partner_type"],
                "closed": row["n_closed"],
                "completed": row["n_completed"],
                "rate": rate(row["n_completed"], row["n_closed"]),
                "ci": wilson_bounds(row["n_completed"], row["n_closed"]),
                "verdict": verdict,
                "verdict_label": VERDICT_LABEL[verdict],
            }
        )
    return {
        "overall_rate": rate(total_completed, total_closed),
        "partners": sorted(out, key=lambda row: -row["closed"]),
    }


def outcome_matrix(referrals):
    """PM-3 — referral category × outcome type, with the empty cells kept.

    Every combination gets a row, including the zeros, because the zeros are the
    finding: training referrals that convert to training completions and almost
    never to a job is the onward-referral gap the platform exists to close. A
    Sankey draws only the ribbons that exist, so a zero has no visual presence
    at all — which is the argument against one.

    Carries both `n_referrals` and `n_youth`: a youth with three completed
    referrals is one youth, and any person-level indicator must use the latter.
    """
    categories = list(ReferralCategory.objects.filter(is_active=True).order_by("sort_order", "label"))
    outcomes = list(OutcomeType.objects.filter(is_active=True).order_by("sort_order", "label"))

    counts = {
        (row["referral_category__code"], row["outcome_type__code"]): row
        for row in referrals.filter(status=ReferralStatus.COMPLETED)
        .values("referral_category__code", "outcome_type__code")
        .annotate(n_referrals=Count("pk"), n_youth=Count("case__youth_id", distinct=True))
    }

    # PM-3 exists to expose the onward-referral gap — training referrals that
    # complete and never become a job. That crossover cannot appear here unless
    # §5.3's `applies_to` permits it, and as seeded it does not: every category
    # admits exactly one specific outcome plus "Other". So a diagonal matrix is
    # not evidence about the programme, it is a restatement of the lookup table,
    # and the card has to say which of the two the reader is looking at.
    #
    # `applies_to` is admin-editable configuration (§9), so widening it is a
    # taxonomy decision rather than a code change.
    permitted = {
        (category.code, outcome.code)
        for category in categories
        for outcome in outcomes
        if outcome.is_valid_for(category)
    }
    off_diagonal_possible = any(
        len([o for o in outcomes if o.is_valid_for(category) and o.code != "OTHER"]) > 1 for category in categories
    )

    return {
        "categories": [{"code": c.code, "label": c.label} for c in categories],
        "outcomes": [{"code": o.code, "label": o.label} for o in outcomes],
        # A cell the taxonomy forbids is not the same as one nobody recorded.
        "permitted": sorted(f"{c}:{o}" for c, o in permitted),
        "crossovers_possible": off_diagonal_possible,
        "cells": [
            {
                "category": category.code,
                "outcome": outcome.code,
                "n_referrals": counts.get((category.code, outcome.code), {}).get("n_referrals", 0),
                "n_youth": counts.get((category.code, outcome.code), {}).get("n_youth", 0),
            }
            for category in categories
            for outcome in outcomes
        ],
        # A completed referral with no outcome recorded is a data-quality row,
        # not an outcome — kept separate so it cannot be read as one.
        "not_recorded": referrals.filter(status=ReferralStatus.COMPLETED, outcome_type__isnull=True).count(),
        # §5.3 requires a free-text note with "Other". Past a share of the
        # total it stops being a valid outcome and becomes a reporting failure:
        # every breakdown downstream, including the donor tier, loses those rows.
        "other": rate(
            referrals.filter(status=ReferralStatus.COMPLETED, outcome_type__code="OTHER").count(),
            referrals.filter(status=ReferralStatus.COMPLETED).count(),
        ),
    }


def parallel_load(referrals):
    """PM-7 — cases running more than one active referral at once (§6.3).

    Counts both capped and exempt referrals, so the pending decision on whether
    Complementary Service sits outside the cap (OQ-7) can be evidenced rather
    than argued.
    """
    active = referrals.filter(status=ReferralStatus.ACTIVE)
    per_case = active.values("case_id").annotate(
        n_active=Count("pk"),
        n_capped=Count("pk", filter=Q(referral_category__exempt_from_parallel_cap=False)),
    )
    rows = [row for row in per_case if row["n_active"] > 1]
    return {
        "cases_with_parallel": len(rows),
        # Above the cap counting only the referrals that consume a slot.
        "breaches_cap": len([row for row in rows if row["n_capped"] > 2]),
        "cases_total": referrals.values("case_id").distinct().count(),
    }


def programme_manager(youth, cases, referrals):
    return {
        "as_of": timezone.now().isoformat(),
        "outcome_matrix": outcome_matrix(referrals),
        "partner_performance": partner_performance(referrals),
        "parallel_load": parallel_load(referrals),
        "data_completeness": data_completeness(youth, referrals),
        "cohort_retention": absent(PLACEMENT_PENDING),
        "disposition_90_day": absent(PLACEMENT_PENDING),
    }


# ---------------------------------------------------------------------------
# Tier 4 — M&E and donor
# ---------------------------------------------------------------------------

# §6.1. Wording is verbatim from the parent operations so woreda figures roll up
# without reconciliation — do not "improve" these strings.
INDICATORS = [
    {
        "code": "wage_or_business",
        "label": "Youth clients with business plans financed or enrolled in wage employment",
        "framework": "PSNP 5 / SEASN (P172479)",
    },
    {
        "code": "training_completion",
        "label": "Share of beneficiaries completing training",
        "framework": "World Bank Jobs M&E Toolkit (2017)",
    },
    {
        "code": "employed",
        "label": "Number of self- and/or wage employed beneficiaries",
        "framework": "Jobs M&E Toolkit, PDO-level",
    },
    {
        "code": "confirmed_within_threshold",
        "label": "Referrals confirmed within threshold",
        "framework": "Adapted from PSNP '% of transfers within 45 days'",
    },
    {
        "code": "loop_closure",
        "label": "Referral loop closure rate",
        "framework": "Adapted from CMS50 'Closing the Referral Loop'",
    },
]


def disaggregation(youth, referrals, today):
    """ME-3 — placement counts cut every way the frameworks ask for.

    The suppression rule is applied here and rendered visibly, because this is
    exactly where denominators collapse: female × disability × woreda is what
    donors ask for and what the pilot cannot support.

    OQ-11 settled 2026-08-18: `Youth.settlement_type` exists, so the cut both
    frameworks require is here. It is never proxied from woreda — an Ethiopian
    woreda routinely contains both rural and urban kebeles, so inferring it
    would produce a confident wrong number instead of an honest blank.
    """
    placed_youth = referrals.placed_youth_ids()

    rows = list(
        youth.values_list("id", "sex", "woreda", "date_of_birth", "disability_status", "psnp_status", "settlement_type")
    )

    def cut(label, key):
        buckets = {}
        for youth_id, sex, woreda, born, disability, psnp, settlement in rows:
            value = key(sex, woreda, born, disability, psnp, settlement)
            bucket = buckets.setdefault(value, {"registered": 0, "placed": 0})
            bucket["registered"] += 1
            bucket["placed"] += youth_id in placed_youth
        return {
            "label": str(label),
            "rows": sorted(
                (
                    {
                        "value": value,
                        "registered": b["registered"],
                        "placed": b["placed"],
                        "rate": rate(b["placed"], b["registered"]),
                    }
                    for value, b in buckets.items()
                ),
                key=lambda row: -row["registered"],
            ),
        }

    return [
        cut(_("Sex"), lambda sex, w, b, d, p, st: Sex(sex).label if sex in Sex.values else str(_("Unknown"))),
        cut(_("Age band"), lambda s, w, born, d, p, st: age_band(born, today)),
        cut(_("Woreda"), lambda s, woreda, b, d, p, st: woreda),
        cut(
            _("Disability"),
            lambda s, w, b, disability, p, st: (
                DisabilityStatus(disability).label if disability in DisabilityStatus.values else str(_("Not recorded"))
            ),
        ),
        cut(
            _("Settlement type"),
            lambda s, w, b, d, p, st: (
                SettlementType(st).label if st in SettlementType.values else str(_("Not recorded"))
            ),
        ),
        cut(
            _("PSNP status"),
            lambda s, w, b, d, psnp, st: (
                PsnpStatus(psnp).label if psnp in PsnpStatus.values else str(_("Not recorded"))
            ),
        ),
    ]


def results_framework(youth, referrals, today, confirmation_threshold, maturation_days=30):
    """ME-1 — the indicator table, each with its numerator and denominator."""
    placed_youth = len(referrals.placed_youth_ids())

    # Only referrals old enough to have been decided count in a timeliness rate.
    mature = referrals.filter(initiated_date__lte=today - timedelta(days=maturation_days))
    confirmed_in_time = (
        mature.filter(confirmed_date__isnull=False, confirmation_status=ConfirmationStatus.CONFIRMED).annotate(
            lag=ExpressionWrapper(F("confirmed_date") - F("initiated_date"), output_field=DurationField())
        )
        # `lte`: a partner who answers on the threshold day has met the
        # standard. Same rule the tiles and the alert engine now use.
        .filter(lag__lte=timedelta(days=confirmation_threshold))
    )

    closed = referrals.filter(status__in=[ReferralStatus.COMPLETED, ReferralStatus.FAILED])
    mature_closed = closed.filter(initiated_date__lte=today - timedelta(days=maturation_days))
    # Recorded is not verified, and the card used to conflate them: it tested
    # `outcome_verified_by IS NOT NULL`, which only says a staff member signed
    # the record off. 59 self-reported outcomes were inside that number, so the
    # rate read 50% where the externally-verified figure was 32%.
    #
    # Both are reported, and the verified one is primary — which is what the
    # page's own caveat has always said to do.
    recorded = mature_closed.with_recorded_outcome()
    externally_verified = mature_closed.externally_verified()

    return [
        {
            "code": "wage_or_business",
            "label": INDICATORS[0]["label"],
            "framework": INDICATORS[0]["framework"],
            "kind": "count",
            "value": placed_youth,
            "rate": None,
            "available": True,
            "reason": "",
        },
        {
            "code": "training_completion",
            "label": INDICATORS[1]["label"],
            "framework": INDICATORS[1]["framework"],
            "kind": "rate",
            "value": None,
            "rate": None,
            "available": False,
            "reason": str(TRAINING_PENDING),
        },
        {
            "code": "employed",
            "label": INDICATORS[2]["label"],
            "framework": INDICATORS[2]["framework"],
            "kind": "count",
            "value": placed_youth,
            "rate": None,
            "available": True,
            # §8.3: gross, not net. This platform cannot net out deadweight or
            # displacement, so the figure is not "jobs created".
            "reason": str(_("Gross, not net of deadweight or displacement. Not 'jobs created'.")),
        },
        {
            "code": "confirmed_within_threshold",
            "label": INDICATORS[3]["label"],
            "framework": INDICATORS[3]["framework"],
            "kind": "rate",
            "value": None,
            "rate": rate(confirmed_in_time.count(), mature.count()),
            "available": True,
            "reason": str(
                _("Referrals raised in the last %(d)s days are excluded — not yet decidable.") % {"d": maturation_days}
            ),
        },
        {
            "code": "loop_closure",
            "label": INDICATORS[4]["label"],
            "framework": INDICATORS[4]["framework"],
            "kind": "rate",
            "value": None,
            # The primary figure is the verified one.
            "rate": rate(externally_verified.count(), mature_closed.count()),
            "available": True,
            "reason": str(
                _(
                    "Outcome verified by someone other than the youth, over mature closed referrals. "
                    "The recorded rate beside it counts every outcome, verified or not."
                )
            ),
            "recorded": rate(recorded.count(), mature_closed.count()),
            "unit": str(_("referrals")),
        },
    ]


def cumulative_placements(referrals, today, months=12):
    """ME-2 — youth placed to date, by month. One axis, counts, no dual axis.

    Two things this got wrong, and they compounded:

    * It counted **referrals**, so a youth placed twice moved the line twice
      while the headline above it counted them once.
    * It truncated to a rolling window but kept running a cumulative total
      labelled "to date", silently dropping every placement older than the
      window. The line closed below the headline by exactly the number of
      placements it had discarded.

    A youth enters the series on their **first** placement, so the running total
    is distinct youth and the last point equals the Results headline by
    construction — there is a test that asserts precisely that. Placements older
    than the window are carried in as an opening balance rather than lost.
    """
    first_placement = {}
    for youth_id, outcome_date in (
        referrals.placements()
        .filter(outcome_date__isnull=False)
        .values_list("case__youth_id", "outcome_date")
        .order_by("outcome_date")
    ):
        first_placement.setdefault(youth_id, outcome_date)

    start = date(today.year, today.month, 1) - timedelta(days=31 * (months - 1))
    start = date(start.year, start.month, 1)

    buckets = {}
    opening = 0
    for outcome_date in first_placement.values():
        if outcome_date < start:
            # Before the window. Carried in, never dropped: a total labelled
            # "to date" that omits the earliest placements is simply wrong.
            opening += 1
        else:
            key = date(outcome_date.year, outcome_date.month, 1)
            buckets[key] = buckets.get(key, 0) + 1

    series, running = [], opening
    cursor = start
    while cursor <= today:
        running += buckets.get(cursor, 0)
        series.append(
            {
                "month": cursor.isoformat(),
                "placed": buckets.get(cursor, 0),
                "cumulative": running,
                "unit": str(_("youth")),
            }
        )
        cursor = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)

    return {"series": series, "opening_balance": opening, "unit": str(_("youth"))}


def donor(youth, referrals, today, confirmation_threshold):
    return {
        "indicators": results_framework(youth, referrals, today, confirmation_threshold),
        "cumulative": cumulative_placements(referrals, today),
        "disaggregation": disaggregation(youth, referrals, today),
        "retention": absent(PLACEMENT_PENDING),
        # ME-5. A sentence beats another chart, and these two caveats are the
        # ones the handoff requires by name.
        "caveats": [
            str(
                _(
                    "Placements are gross. They are not 'jobs created' — that claim needs deadweight "
                    "and displacement netted out, which this platform cannot do."
                )
            ),
            str(
                _(
                    "The headline counts every recorded outcome. Report the externally-verified subset "
                    "separately; a self-reported placement rate is an aspiration."
                )
            ),
            str(_("Retention is not yet measurable: nothing records whether a youth stays in their placement.")),
        ],
        "as_of": timezone.now().isoformat(),
    }
