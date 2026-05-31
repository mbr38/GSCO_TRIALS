"""M-GHG-REDESIGN-A1 — VIIRS persistence-weighted ring-relative sustained
contrast: §2.3 behavioural cases + pure-math unit tests.

All tests use SYNTHETIC per-timestep `(iso, site_mean, ring_mean)` series so
they are independent of live satellite data (spec §5). The five §2.3 cases
encode the intended behaviour the redesign must preserve.
"""

from __future__ import annotations

import pytest

from engine.constants import (
    VIIRS_LIT_CONTRAST_THRESHOLD,
    VIIRS_PERSISTENCE_FLOOR,
    VIIRS_PERSISTENCE_FLOOR_DISCOUNT,
)
from engine.ghg import (
    _michelson_contrast,
    _percentile,
    _persistence_factor,
    viirs_sustained_contrast_from_series,
)
from ui.components.severity import severity_score_band


def _series(pairs: list[tuple[float, float]]) -> list[tuple[str, float, float]]:
    """Build a (iso, site, ring) series from (site, ring) pairs."""
    return [(f"2024-01-{i + 1:02d}", s, r) for i, (s, r) in enumerate(pairs)]


# ---------------------------------------------------------------------------
# Pure-math building blocks
# ---------------------------------------------------------------------------

class TestMichelsonContrast:
    def test_bounded_zero_one(self) -> None:
        assert _michelson_contrast(50.0, 5.0) == pytest.approx(45 / 55)
        assert 0.0 <= _michelson_contrast(50.0, 5.0) <= 1.0

    def test_site_below_ring_is_zero(self) -> None:
        # Site dimmer than its surroundings → not brighter → 0 (clamped).
        assert _michelson_contrast(3.0, 5.0) == 0.0

    def test_equal_site_ring_is_zero(self) -> None:
        # Attributability: equally-bright cluster → no ring-relative contrast.
        assert _michelson_contrast(40.0, 40.0) == 0.0

    def test_degenerate_zero_zero(self) -> None:
        assert _michelson_contrast(0.0, 0.0) == 0.0


class TestPersistenceFactor:
    def test_saturates_to_one_at_floor(self) -> None:
        assert _persistence_factor(VIIRS_PERSISTENCE_FLOOR) == pytest.approx(1.0)
        assert _persistence_factor(1.0) == pytest.approx(1.0)

    def test_never_zeroes_floor_discount_at_zero(self) -> None:
        # spec §2.3 — intermittent emitter discounted toward, never to, zero.
        assert _persistence_factor(0.0) == pytest.approx(
            VIIRS_PERSISTENCE_FLOOR_DISCOUNT,
        )
        assert _persistence_factor(0.0) > 0.0

    def test_monotonic_non_decreasing(self) -> None:
        vals = [_persistence_factor(p / 10) for p in range(0, 11)]
        assert vals == sorted(vals)


class TestPercentile:
    def test_single_value(self) -> None:
        assert _percentile([0.5], 75.0) == 0.5

    def test_linear_interpolation_matches_numpy(self) -> None:
        # numpy.percentile([0,1,2,3], 75) == 2.25 (linear method).
        assert _percentile([0.0, 1.0, 2.0, 3.0], 75.0) == pytest.approx(2.25)

    def test_empty_is_zero(self) -> None:
        assert _percentile([], 75.0) == 0.0


# ---------------------------------------------------------------------------
# §2.3 — the five behavioural cases (the spec's load-bearing expectations)
# ---------------------------------------------------------------------------

class TestSpec23BehaviouralCases:
    def test_case1_steady_bright_high(self) -> None:
        """Steady, clearly-lit-vs-background → high score (full contrast,
        persistence ≥ floor)."""
        out = viirs_sustained_contrast_from_series(_series([(50.0, 5.0)] * 20))
        assert out["persistence"] == pytest.approx(1.0)
        assert out["score"] >= 0.66                 # High band
        assert severity_score_band(out["score"], 0.7, None) == "High"

    def test_case2_intermittent_flarer_mid(self) -> None:
        """Intermittent but intense flarer (lit a minority of the window, very
        bright when lit) → mid score: real, discounted, still surfaced."""
        # Lit 6/20 nights very bright; dark 14/20 (site below ring).
        out = viirs_sustained_contrast_from_series(
            _series([(80.0, 5.0)] * 6 + [(4.0, 5.0)] * 14),
        )
        assert out["persistence"] == pytest.approx(0.30)
        # Real and surfaced (not erased), but discounted below a steady emitter.
        assert 0.33 <= out["score"] < 0.66
        assert severity_score_band(out["score"], 0.7, None) == "Concern"

    def test_case3_always_on_barely_above_low(self) -> None:
        """Always-on but barely-above-background → low score (persistence high,
        but little contrast to pass through)."""
        out = viirs_sustained_contrast_from_series(_series([(5.4, 5.0)] * 20))
        assert out["persistence"] == pytest.approx(1.0)   # lit every night
        assert out["score"] < 0.33                        # but tiny contrast
        assert severity_score_band(out["score"], 0.7, None) == "Normal"

    def test_case4_brief_blip_then_dark_low(self) -> None:
        """Brief bright blip then dark → low score (contrast discounted by low
        persistence)."""
        out = viirs_sustained_contrast_from_series(
            _series([(80.0, 5.0)] + [(3.0, 5.0)] * 19),
        )
        assert out["persistence"] == pytest.approx(0.05)
        assert out["score"] < 0.33
        # discounted, but NOT erased — the intense night still leaves a trace.
        assert out["score"] > 0.0

    def test_case5_bright_inside_bright_cluster_low(self) -> None:
        """Bright site inside an equally-bright industrial cluster → low score
        (low ring-relative contrast). ATTRIBUTABILITY CHECK."""
        out = viirs_sustained_contrast_from_series(_series([(40.0, 40.0)] * 20))
        assert out["persistence"] == 0.0
        assert out["score"] == 0.0
        assert severity_score_band(out["score"], 0.7, None) == "Normal"


# ---------------------------------------------------------------------------
# Edge cases / contract
# ---------------------------------------------------------------------------

class TestContract:
    def test_no_timesteps_is_none(self) -> None:
        out = viirs_sustained_contrast_from_series([])
        assert out["score"] is None
        assert out["n_valid"] == 0

    def test_score_clamped_unit_interval(self) -> None:
        out = viirs_sustained_contrast_from_series(_series([(1e6, 1.0)] * 30))
        assert 0.0 <= out["score"] <= 1.0

    def test_persistence_is_lit_fraction(self) -> None:
        # 10 lit (bright) + 10 dark → persistence 0.5.
        out = viirs_sustained_contrast_from_series(
            _series([(50.0, 5.0)] * 10 + [(2.0, 5.0)] * 10),
        )
        assert out["persistence"] == pytest.approx(0.5)
        assert out["n_valid"] == 20
        assert out["n_lit"] == 10

    def test_lit_threshold_respected(self) -> None:
        # A contrast just above the lit threshold counts as lit; one just
        # below does not. (Avoids float-exact-equality fragility at the bound.)
        ring = 5.0
        c_hi = VIIRS_LIT_CONTRAST_THRESHOLD + 0.01
        c_lo = VIIRS_LIT_CONTRAST_THRESHOLD - 0.01
        site_hi = ring * (1 + c_hi) / (1 - c_hi)   # invert michelson
        site_lo = ring * (1 + c_lo) / (1 - c_lo)
        out_hi = viirs_sustained_contrast_from_series(_series([(site_hi, ring)] * 5))
        out_lo = viirs_sustained_contrast_from_series(_series([(site_lo, ring)] * 5))
        assert out_hi["n_lit"] == 5
        assert out_lo["n_lit"] == 0
