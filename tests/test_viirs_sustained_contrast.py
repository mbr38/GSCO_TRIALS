"""Pure-math tests for the M-VIIRS-REDESIGN-A1 two-output VIIRS grammar.

Replaces the retired sustained-contrast (contrast·persistence) tests. Covers the
flaring (severity) and lit-contrast (attributability) pure-math cores + the
categorical attributability bucketing. No EE.
"""
from __future__ import annotations

import pytest

from engine.constants import (
    VIIRS_FLARING_SATURATION_FRAC,
    VIIRS_MIN_SITE_PIXELS,
    MIN_RING_LIT_PIXELS,
    VIIRS_ATTRIBUTABILITY_HIGH_PCT,
    VIIRS_ATTRIBUTABILITY_MOD_PCT,
)
from engine.ghg import (
    flaring_score_from_fraction,
    lit_contrast_percentile_from_counts,
)
from engine.core.attributability import compute_viirs_attributability


class TestFlaringScore:
    def test_sparse_below_min_pixels_is_none(self) -> None:
        assert flaring_score_from_fraction(0.05, VIIRS_MIN_SITE_PIXELS - 1) is None

    def test_none_fraction_is_none(self) -> None:
        assert flaring_score_from_fraction(None, 1000) is None

    def test_zero_fraction_is_zero(self) -> None:
        assert flaring_score_from_fraction(0.0, 1000) == 0.0

    def test_saturates_to_one_at_saturation_fraction(self) -> None:
        assert flaring_score_from_fraction(VIIRS_FLARING_SATURATION_FRAC, 1000) == 1.0
        assert flaring_score_from_fraction(VIIRS_FLARING_SATURATION_FRAC * 2, 1000) == 1.0

    def test_linear_below_saturation(self) -> None:
        val = flaring_score_from_fraction(VIIRS_FLARING_SATURATION_FRAC / 2, 1000)
        assert val == pytest.approx(0.5)

    def test_clamped_unit_interval(self) -> None:
        v = flaring_score_from_fraction(0.99, 1000)
        assert 0.0 <= v <= 1.0


class TestLitContrastPercentile:
    def test_empty_ring_is_none(self) -> None:
        assert lit_contrast_percentile_from_counts(0, 0) is None
        assert lit_contrast_percentile_from_counts(None, 100) is None

    def test_fraction_dimmer(self) -> None:
        assert lit_contrast_percentile_from_counts(90, 100) == pytest.approx(0.9)

    def test_site_brightest_is_one(self) -> None:
        assert lit_contrast_percentile_from_counts(100, 100) == pytest.approx(1.0)

    def test_site_dimmest_is_zero(self) -> None:
        assert lit_contrast_percentile_from_counts(0, 100) == pytest.approx(0.0)


class TestViirsAttributability:
    def test_high(self) -> None:
        assert compute_viirs_attributability(VIIRS_ATTRIBUTABILITY_HIGH_PCT, 100) == "high"
        assert compute_viirs_attributability(0.97, 100) == "high"

    def test_moderate(self) -> None:
        assert compute_viirs_attributability(VIIRS_ATTRIBUTABILITY_MOD_PCT, 100) == "moderate"
        assert compute_viirs_attributability(0.74, 100) == "moderate"

    def test_low(self) -> None:
        assert compute_viirs_attributability(0.40, 100) == "low"

    def test_sparse_few_ring_pixels(self) -> None:
        assert compute_viirs_attributability(0.97, MIN_RING_LIT_PIXELS - 1) == "sparse"

    def test_sparse_none_percentile(self) -> None:
        assert compute_viirs_attributability(None, 100) == "sparse"

    def test_sparse_out_of_range(self) -> None:
        assert compute_viirs_attributability(1.5, 100) == "sparse"
