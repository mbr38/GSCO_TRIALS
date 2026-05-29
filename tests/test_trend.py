"""Synthetic-payload tests for the trend drill-down engine (M-TREND-A1).

Pure-function only — `engine/core/trend.py`'s maths + assembly layer has no
EE side effects, so the floor behaviour, the Theil–Sen robustness, the
Mann–Kendall p-value, the confidence invariant and the seasonal flag are all
exercised on synthetic series. The EE reducer (`_server_side_day_means`) is
covered by the integration path, not here (spec §11).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine.constants import (
    TREND_HARD_FLOOR_POINTS,
    TREND_SEASONAL_FLAG_MIN_DAYS,
    TREND_SOFT_FLOOR_POINTS,
)
from engine.core import trend


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_START = date(2025, 1, 1)


def _series(values, *, step_days=10, start=_START):
    """Build a [(iso, value), …] series at a fixed daily cadence."""
    return [
        ((start + timedelta(days=i * step_days)).isoformat(), float(v))
        for i, v in enumerate(values)
    ]


def _ordinals(n, step_days=10, start=_START):
    return [(start + timedelta(days=i * step_days)).toordinal() for i in range(n)]


# ---------------------------------------------------------------------------
# Theil–Sen slope
# ---------------------------------------------------------------------------

class TestTheilSen:
    def test_recovers_known_linear_slope_per_year(self) -> None:
        # +1 unit per 10 days = +36.525 units / year.
        n = 20
        days = _ordinals(n)
        values = [float(i) for i in range(n)]
        slope = trend.theil_sen_slope_per_year(days, values)
        assert slope == pytest.approx(36.525, rel=1e-6)

    def test_robust_to_outliers(self) -> None:
        # A clean +1/10-day line with two wild outlier days. OLS would be
        # dragged; Theil–Sen (median of pairwise slopes) should not.
        n = 21
        days = _ordinals(n)
        values = [float(i) for i in range(n)]
        values[5] = 500.0
        values[15] = -500.0
        slope = trend.theil_sen_slope_per_year(days, values)
        assert slope == pytest.approx(36.525, rel=1e-6)

    def test_none_below_two_distinct_x(self) -> None:
        assert trend.theil_sen_slope_per_year([10], [1.0]) is None
        # all-same x → no slope defined
        assert trend.theil_sen_slope_per_year([10, 10, 10], [1.0, 2.0, 3.0]) is None


# ---------------------------------------------------------------------------
# Mann–Kendall p-value
# ---------------------------------------------------------------------------

class TestMannKendall:
    def test_strict_monotonic_is_highly_significant(self) -> None:
        p = trend.mann_kendall_two_sided_p([float(i) for i in range(15)])
        assert p is not None and p < 0.001

    def test_flat_series_is_not_significant(self) -> None:
        p = trend.mann_kendall_two_sided_p([5.0] * 15)
        # all-tied → variance non-positive → undefined
        assert p is None

    def test_noisy_no_trend_is_not_significant(self) -> None:
        # Alternating up/down has S≈0 → p near 1.
        vals = [1.0, 0.0] * 8
        p = trend.mann_kendall_two_sided_p(vals)
        assert p is not None and p > 0.10

    def test_none_below_three_points(self) -> None:
        assert trend.mann_kendall_two_sided_p([1.0, 2.0]) is None


# ---------------------------------------------------------------------------
# Significance bucket
# ---------------------------------------------------------------------------

class TestSignificanceBucket:
    @pytest.mark.parametrize("p,expected", [
        (0.0, "significant"),
        (0.049, "significant"),
        (0.05, "weak_emerging"),
        (0.099, "weak_emerging"),
        (0.10, "none"),
        (0.5, "none"),
        (None, "unavailable"),
    ])
    def test_buckets(self, p, expected) -> None:
        assert trend.significance_bucket(p) == expected


# ---------------------------------------------------------------------------
# Seasonal flag
# ---------------------------------------------------------------------------

class TestSeasonalFlag:
    def test_fires_below_min_days(self) -> None:
        assert trend.seasonal_flag(TREND_SEASONAL_FLAG_MIN_DAYS - 1) is True

    def test_not_above_min_days(self) -> None:
        assert trend.seasonal_flag(TREND_SEASONAL_FLAG_MIN_DAYS) is False
        assert trend.seasonal_flag(TREND_SEASONAL_FLAG_MIN_DAYS + 100) is False


# ---------------------------------------------------------------------------
# Severity (direction-aware, bg-sigma/yr)
# ---------------------------------------------------------------------------

class TestTrendSeverity:
    def test_higher_is_worse_rising_is_severe(self) -> None:
        # slope = +1.0 unit/yr, bg_std = 1.0, k = 1.0 → severity 1.0
        sev = trend.trend_severity(1.0, 1.0, "higher_is_worse", k_trend=1.0)
        assert sev == pytest.approx(1.0)

    def test_higher_is_worse_falling_clamps_to_zero(self) -> None:
        sev = trend.trend_severity(-1.0, 1.0, "higher_is_worse", k_trend=1.0)
        assert sev == 0.0

    def test_lower_is_worse_inverts_direction(self) -> None:
        # NDVI: a declining (negative) slope is the worrying one.
        sev = trend.trend_severity(-1.0, 1.0, "lower_is_worse", k_trend=1.0)
        assert sev == pytest.approx(1.0)
        sev_up = trend.trend_severity(1.0, 1.0, "lower_is_worse", k_trend=1.0)
        assert sev_up == 0.0

    def test_partial_severity_scales_with_k(self) -> None:
        sev = trend.trend_severity(0.5, 1.0, "higher_is_worse", k_trend=1.0)
        assert sev == pytest.approx(0.5)

    def test_none_on_degenerate_bg(self) -> None:
        assert trend.trend_severity(1.0, 0.0, "higher_is_worse") is None
        assert trend.trend_severity(None, 1.0, "higher_is_worse") is None


# ---------------------------------------------------------------------------
# Confidence (sibling of M-TIER-A1; C-iii invariant)
# ---------------------------------------------------------------------------

class TestTrendConfidence:
    def test_increases_with_length(self) -> None:
        low = trend.trend_confidence(
            n_valid_days=TREND_HARD_FLOOR_POINTS, span_days=400,
            largest_gap_days=10, column_to_surface_uncertainty="strong",
        )
        high = trend.trend_confidence(
            n_valid_days=TREND_SOFT_FLOOR_POINTS, span_days=400,
            largest_gap_days=10, column_to_surface_uncertainty="strong",
        )
        assert high > low

    def test_length_term_zero_at_hard_floor(self) -> None:
        # At the hard floor the length term is 0; with a dense long window the
        # remaining base is span + coverage only.
        assert trend._length_term(TREND_HARD_FLOOR_POINTS) == 0.0
        assert trend._length_term(TREND_SOFT_FLOOR_POINTS) == pytest.approx(1.0)

    def test_clustered_series_has_lower_coverage_term(self) -> None:
        even = trend._coverage_term(span_days=300, largest_gap_days=30)
        clustered = trend._coverage_term(span_days=300, largest_gap_days=280)
        assert even > clustered

    def test_fallback_multipliers_reduce_confidence(self) -> None:
        base = trend.trend_confidence(
            n_valid_days=20, span_days=400, largest_gap_days=10,
            column_to_surface_uncertainty="strong",
        )
        sppy = trend.trend_confidence(
            n_valid_days=20, span_days=400, largest_gap_days=10,
            column_to_surface_uncertainty="strong",
            temporal_fallback_applied=True,
        )
        clim = trend.trend_confidence(
            n_valid_days=20, span_days=400, largest_gap_days=10,
            column_to_surface_uncertainty="strong",
            climatology_fallback_applied=True,
        )
        assert sppy < base
        assert clim < base

    def test_never_exceeds_snapshot_confidence(self) -> None:
        # C-iii invariant: a strong, dense trend capped at a weak snapshot.
        capped = trend.trend_confidence(
            n_valid_days=50, span_days=400, largest_gap_days=5,
            column_to_surface_uncertainty="strong",
            snapshot_confidence=0.2,
        )
        assert capped <= 0.2

    def test_unknown_column_to_surface_raises(self) -> None:
        with pytest.raises(KeyError):
            trend.trend_confidence(
                n_valid_days=20, span_days=400, largest_gap_days=10,
                column_to_surface_uncertainty="bogus",
            )


# ---------------------------------------------------------------------------
# Assembly + floor behaviour (TR4)
# ---------------------------------------------------------------------------

class TestAssembleFloors:
    def _assemble(self, n):
        return trend.assemble_trend_result(
            "air.no2",
            _series([float(i) for i in range(n)]),
            bg_median=10.0, bg_std=2.0, direction="higher_is_worse",
            window=("2025-01-01", "2025-12-31"),
            column_to_surface_uncertainty="moderate",
            snapshot_confidence=0.9,
        )

    def test_below_hard_floor_unavailable(self) -> None:
        out = self._assemble(TREND_HARD_FLOOR_POINTS - 1)
        assert out["significance_bucket"] == "unavailable"
        assert out["trend"] is None
        assert out["trend_p"] is None
        assert out["trend_severity"] is None
        assert out["trend_confidence"] is None
        # series + coverage still returned so the UI can show "too few points"
        assert len(out["series"]) == TREND_HARD_FLOOR_POINTS - 1
        assert out["coverage"]["n_valid_days"] == TREND_HARD_FLOOR_POINTS - 1

    def test_at_hard_floor_emits_slope(self) -> None:
        out = self._assemble(TREND_HARD_FLOOR_POINTS)
        assert out["trend"] is not None
        assert out["significance_bucket"] != "unavailable"
        # length term is 0 at the hard floor → confidence is pinned low
        assert out["trend_confidence"] is not None

    def test_confidence_rises_hard_to_soft(self) -> None:
        at_hard = self._assemble(TREND_HARD_FLOOR_POINTS)
        at_soft = self._assemble(TREND_SOFT_FLOOR_POINTS)
        assert at_soft["trend_confidence"] > at_hard["trend_confidence"]

    def test_contract_shape(self) -> None:
        out = self._assemble(TREND_SOFT_FLOOR_POINTS)
        for key in (
            "indicator_id", "trend", "trend_p", "trend_severity",
            "trend_confidence", "significance_bucket", "seasonal_flag",
            "series", "coverage", "provenance",
        ):
            assert key in out
        assert out["indicator_id"] == "air.no2"
        assert out["provenance"]["bg_std"] == 2.0
        # confidence honours the C-iii cap even on the happy path
        assert out["trend_confidence"] <= 0.9

    def test_seasonal_flag_in_result(self) -> None:
        # 12 points × 10-day step = 110-day span → under a year → flagged.
        out = self._assemble(TREND_SOFT_FLOOR_POINTS)
        assert out["seasonal_flag"] is True
