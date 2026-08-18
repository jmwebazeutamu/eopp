"""Reporting rules that stop the dashboard lying.

From `docs/Youth_Employment_Dashboard_Prototype_v1.html`, panel 5. They are here
rather than in each panel because a rule applied in four places is four rules,
and the one that gets forgotten is always the disaggregated cell nobody looked
at — which is exactly where denominators collapse.

Two rules, both about denominators:

* **A percentage never appears without the counts it came from.** Not on a tile,
  not in a tooltip, not in the donor PDF. The API therefore has no field that
  carries a bare percentage; `rate()` returns the numerator and denominator with
  it, and the screen renders all three.
* **A rate on too few cases is marked or withheld.** Below 30 it is provisional
  and must never be used in a comparison or a ranking; below 10 it is not shown
  at all. Ranking on unstable rates sorts by luck, and once published that
  ranking is politically hard to withdraw.

Worth knowing before reading a dashboard built on this: the pilot is 500-1,000
youth across two or three woredas (spec §1). Applied honestly, these thresholds
suppress a great deal of what a donor will ask for — every partner-level rate
early on, and most of the sex × age × woreda × disability disaggregation
throughout. That is the correct answer rather than a defect, but it needs saying
out loud before someone reads a screen of dashes as a broken report.
"""

from django.utils.translation import gettext_lazy as _

# OQ-8, settled 2026-08-18: 30 and 10, following the NCHS Data Presentation
# Standards for Proportions the handoff cites. No reason to depart from a
# published standard, and the World Bank task team can still prescribe its own —
# named constants so that is a one-line change rather than a hunt through panels.
REPORT_MIN_DENOMINATOR = 30
PROVISIONAL_MIN_DENOMINATOR = 10

REPORT = "report"
PROVISIONAL = "provisional"
SUPPRESSED = "suppressed"

BAND_NOTE = {
    REPORT: "",
    PROVISIONAL: str(_("Provisional — fewer than %(n)s cases. Not for comparison or ranking.")),
    SUPPRESSED: str(_("Too few to assess.")),
}


def band_for(denominator):
    """Which of the three bands a denominator falls in."""
    if denominator is None or denominator < PROVISIONAL_MIN_DENOMINATOR:
        return SUPPRESSED
    if denominator < REPORT_MIN_DENOMINATOR:
        return PROVISIONAL
    return REPORT


def rate(numerator, denominator):
    """A percentage that carries its own counts and its confidence band.

    `percent` is None when the band suppresses it — which the screen must render
    as "too few to assess", never as 0%. Zero placements from forty referrals and
    a denominator too small to judge are opposite findings.

    Whole percentage points only: 49%, never 48.81%. The extra digit implies a
    precision the denominator does not support.
    """
    band = band_for(denominator)
    return {
        "percent": None if band == SUPPRESSED else round(numerator * 100 / denominator),
        "n": numerator,
        "d": denominator,
        "band": band,
        "note": BAND_NOTE[band] % {"n": REPORT_MIN_DENOMINATOR} if band == PROVISIONAL else BAND_NOTE[band],
    }


def mean_days(value, observations):
    """An average with the same banding as a rate.

    A mean over four referrals is as unstable as a rate over four, and the
    partner comparison it feeds is the one the prototype warns hardest about.
    """
    band = band_for(observations)
    return {
        "days": None if band == SUPPRESSED else round(value),
        "n": observations,
        "band": band,
        "note": BAND_NOTE[band] % {"n": REPORT_MIN_DENOMINATOR} if band == PROVISIONAL else BAND_NOTE[band],
    }


def quarter_elapsed_fraction(today, start, end):
    """How far through the quarter we are, as 0-1.

    Progress against a quarterly target has to be read against elapsed time, or
    every quarter opens with a card that says the programme is failing. Day three
    of ninety at 3% of target is on track; the same figure on day eighty is not.
    """
    span = (end - start).days
    if span <= 0:
        return 1.0
    return min(1.0, max(0.0, (today - start).days / span))


# ---------------------------------------------------------------------------
# Comparison — ported from sql/002_helper_functions.sql
# ---------------------------------------------------------------------------

# 3.09 ≈ 99.8% control limits, 1.96 ≈ 95% confidence interval.
FUNNEL_Z = 3.09
CI_Z = 1.96


def median(values):
    """Median of a list, or None. Whole numbers out.

    The handoff is specific that partner response time is a **median, not a
    mean** (WS-4, PM-4): one partner that sat on a referral for nine months
    drags a mean somewhere no individual referral ever was.
    """
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle])
    return round((ordered[middle - 1] + ordered[middle]) / 2)


def wilson_bounds(numerator, denominator, z=CI_Z):
    """Wilson score interval, as whole percentage points.

    Preferred over the normal approximation because it behaves correctly at
    proportions near 0 and 1 and at small n — which is most of this dataset.
    """
    if not denominator:
        return None
    n = float(denominator)
    p = numerator / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    margin = (z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5) / (1 + z * z / n)
    return {"lower": round(100 * max(centre - margin, 0)), "upper": round(100 * min(centre + margin, 1))}


def funnel_verdict(numerator, denominator, overall_rate):
    """Spiegelhalter funnel-plot logic, reduced to a three-state flag.

    Control limits are computed around the **overall programme rate**, not
    around a target, and they widen as the denominator shrinks — which is
    exactly why a partner with 27 closed referrals cannot be called an outlier
    and one with 180 can.

    Returns `too_few` for anything outside the *report* band, not merely below
    the suppression floor: a verdict is a comparison, and the provisional band
    is defined as never compared or ranked. Returning `as_expected` for n = 20
    would smuggle that comparison back in.

    What this is not: a ranking. Everything returning `as_expected` is
    indistinguishable on the evidence available.
    """
    if band_for(denominator) != REPORT or overall_rate is None or not denominator:
        return "too_few"
    spread = FUNNEL_Z * ((overall_rate * (1 - overall_rate)) / denominator) ** 0.5
    observed = numerator / denominator
    if observed < overall_rate - spread:
        return "below"
    if observed > overall_rate + spread:
        return "above"
    return "as_expected"


# Symbol *and* word, never colour alone (WCAG 1.4.1).
VERDICT_LABEL = {
    "above": "▲ above expected",
    "below": "▼ below expected",
    "as_expected": "▬ as expected",
    "too_few": "· too few to assess",
}


def age_band(born, as_of):
    """Ethiopia defines youth as 15-29, not the international 15-24.

    The 15-17 / 18-24 splits are the ILO-recommended subgroups, carried for
    international comparability.
    """
    if born is None:
        return "unknown"
    years = as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))
    if years < 15:
        return "under 15"
    if years < 18:
        return "15-17"
    if years < 25:
        return "18-24"
    if years < 30:
        return "25-29"
    return "30+"
