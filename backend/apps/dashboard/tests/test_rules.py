"""The reporting rules, tested as pure functions.

From `docs/Youth_Employment_Dashboard_Prototype_v1.html`, panel 5. No database:
these are the arithmetic and the thresholds, and they are the part that has to be
right in every panel at once.
"""

from datetime import date

import pytest

from apps.dashboard.rules import (
    PROVISIONAL,
    PROVISIONAL_MIN_DENOMINATOR,
    REPORT,
    REPORT_MIN_DENOMINATOR,
    SUPPRESSED,
    band_for,
    mean_days,
    quarter_elapsed_fraction,
    rate,
)


class TestBands:
    @pytest.mark.parametrize(
        "denominator,expected",
        [
            (0, SUPPRESSED),
            (9, SUPPRESSED),
            (PROVISIONAL_MIN_DENOMINATOR, PROVISIONAL),
            (29, PROVISIONAL),
            (REPORT_MIN_DENOMINATOR, REPORT),
            (4812, REPORT),
        ],
    )
    def test_the_three_bands(self, denominator, expected):
        assert band_for(denominator) == expected

    def test_a_missing_denominator_is_suppressed_not_reported(self):
        assert band_for(None) == SUPPRESSED


class TestRate:
    def test_a_percentage_never_travels_without_its_counts(self):
        """Not on a tile, not in a tooltip, not in the donor PDF."""
        result = rate(15, 60)
        assert result["percent"] == 25
        assert (result["n"], result["d"]) == (15, 60)

    def test_whole_percentage_points_only(self):
        # 48.81% implies a precision 41 cases cannot support.
        assert rate(20, 41)["percent"] == 49

    def test_a_provisional_rate_is_marked_and_still_shown(self):
        result = rate(6, 12)
        assert result["band"] == PROVISIONAL
        assert result["percent"] == 50
        assert "comparison" in result["note"]

    def test_a_rate_below_the_floor_is_withheld_entirely(self):
        result = rate(1, 3)
        assert result["band"] == SUPPRESSED
        assert result["percent"] is None
        assert result["note"] == "Too few to assess."

    def test_suppressed_is_not_zero(self):
        """Zero placements from forty referrals and 'too few to judge' are
        opposite findings, and must not arrive at the screen looking alike."""
        none_placed = rate(0, 40)
        too_few = rate(0, 4)
        assert none_placed["percent"] == 0 and none_placed["band"] == REPORT
        assert too_few["percent"] is None

    def test_a_full_rate_is_a_hundred_not_a_rounding_artefact(self):
        assert rate(30, 30)["percent"] == 100


class TestMeanDays:
    def test_an_average_is_banded_like_a_rate(self):
        """A mean over four referrals is as unstable as a rate over four."""
        assert mean_days(6.4, 4)["days"] is None
        assert mean_days(6.4, 40)["days"] == 6

    def test_the_observation_count_always_travels_with_the_mean(self):
        assert mean_days(11.2, 55) == {"days": 11, "n": 55, "band": REPORT, "note": ""}


class TestQuarterElapsed:
    def test_progress_is_read_against_elapsed_time(self):
        """Day three of ninety at 3% of target is on track, not failing."""
        start, end = date(2026, 7, 1), date(2026, 10, 1)
        # Q3 is 92 days, so mid-August is day 45 of 92 — not quite half way.
        assert quarter_elapsed_fraction(date(2026, 7, 3), start, end) == pytest.approx(2 / 92, abs=0.001)
        assert quarter_elapsed_fraction(date(2026, 8, 15), start, end) == pytest.approx(45 / 92, abs=0.001)

    def test_it_never_leaves_the_zero_to_one_range(self):
        start, end = date(2026, 7, 1), date(2026, 10, 1)
        assert quarter_elapsed_fraction(date(2026, 6, 1), start, end) == 0.0
        assert quarter_elapsed_fraction(date(2026, 11, 1), start, end) == 1.0

    def test_a_zero_length_period_does_not_divide_by_zero(self):
        assert quarter_elapsed_fraction(date(2026, 7, 1), date(2026, 7, 1), date(2026, 7, 1)) == 1.0
