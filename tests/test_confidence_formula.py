"""Unit tests for the M-TIER-A1 confidence formula.

Pins the per-indicator additive form `0.30·QA + 0.30·N_valid +
0.25·anomaly_strength + 0.15·spatial_context` × column-to-surface
multiplier, the strict-None behaviour, and the per-term helper math.

Synthesised fixtures (locked decision Q8) — no EE required.

Added by M-TIER-A1 per the spec's §6/§7.
"""

from __future__ import annotations

import math

import pytest

from engine.constants import (
    COLUMN_TO_SURFACE_MULTIPLIER,
    CONFIDENCE_FORMULA_WEIGHTS,
    HANSEN_LOOKBACK_YEARS,
    QA_PER_INDICATOR,
)
from engine.core.confidence import (
    compute_anomaly_strength_term,
    compute_indicator_confidence,
    compute_n_valid_term,
    compute_qa_term,
    compute_spatial_context_term,
)


class TestUniversalWeights:
    def test_weights_sum_to_one(self) -> None:
        # The formula is documented as an additive composition over [0,1]
        # terms; weights summing to anything other than 1.0 would make
        # the result range drift.
        assert sum(CONFIDENCE_FORMULA_WEIGHTS.values()) == pytest.approx(1.0)


class TestComputeIndicatorConfidence:
    def test_perfect_data_with_n_a_multiplier_yields_one(self) -> None:
        # KBA: all four terms 1.0; n_a multiplier (no penalty).
        c = compute_indicator_confidence(
            indicator_id="nature.kba",
            qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty="n_a",
        )
        assert c == pytest.approx(1.0)

    def test_no2_perfect_data_yields_moderate_multiplier(self) -> None:
        # NO₂: moderate column-to-surface tag → 0.95 multiplier.
        c = compute_indicator_confidence(
            indicator_id="air.no2",
            qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty="moderate",
        )
        assert c == pytest.approx(0.95)

    def test_co_perfect_data_yields_weak_multiplier(self) -> None:
        # CO: weak column-to-surface tag → 0.80 multiplier. The visible
        # NO₂ > CO ranking on identical data is the audit §1.5 fold-in.
        c = compute_indicator_confidence(
            indicator_id="air.co",
            qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty="weak",
        )
        assert c == pytest.approx(0.80)

    def test_any_missing_term_returns_none(self) -> None:
        # Strict-None at indicator level — any term missing → None.
        for missing in ("qa", "n_valid", "anomaly_strength", "spatial_context"):
            kwargs = {
                "indicator_id": "air.no2",
                "qa": 0.9, "n_valid": 0.9,
                "anomaly_strength": 0.9, "spatial_context": 0.9,
                "column_to_surface_uncertainty": "moderate",
            }
            kwargs[missing] = None
            c = compute_indicator_confidence(**kwargs)
            assert c is None, f"missing {missing!r} should collapse confidence to None"

    def test_zero_hf_drags_anomaly_strength_contribution(self) -> None:
        # HF = 0 zeroes the 0.25 anomaly_strength contribution. With the
        # other three terms at 1.0 and n_a multiplier, c = 0.30 + 0.30 + 0 + 0.15 = 0.75.
        c = compute_indicator_confidence(
            indicator_id="nature.kba",
            qa=1.0, n_valid=1.0, anomaly_strength=0.0, spatial_context=1.0,
            column_to_surface_uncertainty="n_a",
        )
        assert c == pytest.approx(0.75)

    def test_unknown_multiplier_raises_keyerror(self) -> None:
        # Strict on enum: audit §1.5 fixes the value set; typos must trip.
        with pytest.raises(KeyError, match="column_to_surface_uncertainty"):
            compute_indicator_confidence(
                indicator_id="air.no2",
                qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
                column_to_surface_uncertainty="bogus_tag",
            )


class TestComputeQaTerm:
    def test_returns_static_lookup_when_indicator_known(self) -> None:
        assert compute_qa_term("air.no2") == pytest.approx(QA_PER_INDICATOR["air.no2"])
        assert compute_qa_term("ghg.co2") == pytest.approx(QA_PER_INDICATOR["ghg.co2"])

    def test_returns_none_for_unknown_indicator(self) -> None:
        # Strict-None propagation — caller surfaces the result as a
        # missing input and the confidence becomes None.
        assert compute_qa_term("air.imaginary_gas") is None


class TestComputeNValidTerm:
    def test_clamps_at_one_for_overcount(self) -> None:
        # 100 obs in a 90-day window at 1 obs/day expected → clamped to 1.0.
        v = compute_n_valid_term(
            "air.no2", n_observations=100, window_days=90,
        )
        assert v == pytest.approx(1.0)

    def test_partial_coverage(self) -> None:
        # Post-Step-8 recalibration: TROPOMI NO₂ expected_n = 0.3 obs/day,
        # so a 90-day window expects ~27 valid observations. 9 obs → 9/27 = 1/3.
        v = compute_n_valid_term(
            "air.no2", n_observations=9, window_days=90,
        )
        assert v == pytest.approx(1.0 / 3.0)

    def test_single_snapshot_passthrough_to_one_when_produced(self) -> None:
        # ODIAC: n=1 (or any positive) → 1.0; n=0 → 0.0.
        assert compute_n_valid_term(
            "ghg.co2", n_observations=1, window_days=None,
        ) == 1.0
        assert compute_n_valid_term(
            "ghg.co2", n_observations=0, window_days=None,
        ) == 0.0

    def test_returns_none_when_observations_missing(self) -> None:
        assert compute_n_valid_term(
            "air.no2", n_observations=None, window_days=90,
        ) is None

    def test_returns_none_when_window_days_invalid(self) -> None:
        assert compute_n_valid_term(
            "air.no2", n_observations=10, window_days=None,
        ) is None

    def test_live_revisit_zero_observations_returns_none_not_zero(self) -> None:
        # M-TIER-A1 Step 8 design lock: for live-revisit indicators,
        # n_observations=0 means "no information about coverage", which
        # collapses to None rather than 0.0 ("perfect-bad coverage").
        # Strict-None then propagates through compute_indicator_confidence
        # and the pillar rollup drops the indicator via survivor-renormalise.
        for live_id in ("air.no2", "air.co", "ghg.ch4", "ghg.viirs", "nature.ndvi"):
            v = compute_n_valid_term(
                live_id, n_observations=0, window_days=90,
            )
            assert v is None, (
                f"{live_id} with n=0 should return None (no information), "
                f"got {v!r}"
            )

    def test_single_snapshot_zero_observations_still_returns_zero(self) -> None:
        # SINGLE_SNAPSHOT_INDICATORS keep 0.0 for n=0 because "snapshot
        # attempted and failed" IS information — semantic is distinct
        # from the live-revisit branch above.
        for snap_id in ("ghg.co2", "nature.dw", "nature.habitat",
                        "nature.forest_loss", "nature.kba"):
            assert compute_n_valid_term(
                snap_id, n_observations=0, window_days=None,
            ) == 0.0, f"{snap_id} with n=0 should keep 0.0 (attempted-and-failed)"
        assert compute_n_valid_term(
            "air.no2", n_observations=10, window_days=0,
        ) is None


class TestComputeAnomalyStrengthTerm:
    def test_hf_passthrough(self) -> None:
        assert compute_anomaly_strength_term("air.no2", hf=0.42) == pytest.approx(0.42)

    def test_single_snapshot_indicator_emits_one_unconditionally(self) -> None:
        # KBA, DW, habitat, Hansen, ODIAC, regional_loss_evidence — no HF concept.
        for ind in (
            "nature.kba", "nature.dw", "nature.habitat",
            "nature.forest_loss", "ghg.co2",
            "nature.regional_loss_evidence",
        ):
            assert compute_anomaly_strength_term(ind, hf=None) == 1.0

    def test_live_indicator_with_no_hf_returns_none(self) -> None:
        # When a six_step path fails to compute HF (empty series, σ=0),
        # the formula falls through to None so the indicator confidence
        # itself becomes None at strict-None propagation.
        assert compute_anomaly_strength_term("air.no2", hf=None) is None


class TestComputeSpatialContextTerm:
    def test_sub_pixel_buffer_returns_low_value(self) -> None:
        # 1 km buffer with TROPOMI's 1113 m grid:
        # buffer_area = π·1e6 ≈ 3.14e6 m²; pixel_area ≈ 1.24e6 m²
        # linear_pixels = sqrt(3.14e6/1.24e6) ≈ 1.59
        # ratio = 1.59 / 3.0 ≈ 0.53
        v = compute_spatial_context_term(
            "air.no2", buffer_area_m2=math.pi * 1_000_000.0,
        )
        assert v is not None
        assert v == pytest.approx(0.53, abs=0.05)

    def test_saturates_at_one_for_big_buffer(self) -> None:
        # 25 km buffer → much larger than any of the air pixels → 1.0.
        v = compute_spatial_context_term(
            "air.no2", buffer_area_m2=math.pi * (25_000.0 ** 2),
        )
        assert v == pytest.approx(1.0)

    def test_vector_indicator_emits_one_no_penalty(self) -> None:
        # KBA has native_pixel_area == 0 → spatial_context = 1.0.
        v = compute_spatial_context_term(
            "nature.kba", buffer_area_m2=math.pi * 1_000_000.0,
        )
        assert v == pytest.approx(1.0)

    def test_returns_none_for_unknown_indicator(self) -> None:
        assert compute_spatial_context_term(
            "air.imaginary_gas", buffer_area_m2=1.0,
        ) is None


class TestColumnToSurfaceMultiplierPerIndicator:
    """Mirror the audit §1.5 per-gas mapping. The multiplier values
    encode the same enum that the provenance constructor uses (one source
    of truth — engine/core/provenance._COLUMN_TO_SURFACE_UNCERTAINTY)."""

    @pytest.mark.parametrize("indicator,uncertainty,expected_multiplier", [
        ("air.no2",  "moderate",      0.95),
        ("air.so2",  "moderate_weak", 0.88),
        ("air.co",   "weak",          0.80),
        ("air.hcho", "moderate",      0.95),
        ("ghg.ch4",  "weak",          0.80),
        # n_a defaults — no penalty.
        ("air.o3",   "n_a",           1.00),
        ("air.aai",  "n_a",           1.00),
        ("nature.kba",          "n_a", 1.00),
        ("ghg.co2",             "n_a", 1.00),
        ("nature.forest_loss",  "n_a", 1.00),
    ])
    def test_multiplier_lookup_matches_audit_table(
        self, indicator, uncertainty, expected_multiplier,
    ) -> None:
        assert COLUMN_TO_SURFACE_MULTIPLIER[uncertainty] == pytest.approx(
            expected_multiplier
        )
        # And the multiplier flows through the formula end-to-end.
        c = compute_indicator_confidence(
            indicator_id=indicator,
            qa=1.0, n_valid=1.0, anomaly_strength=1.0, spatial_context=1.0,
            column_to_surface_uncertainty=uncertainty,
        )
        assert c == pytest.approx(expected_multiplier)


class TestRegionalLossEvidenceConfidence:
    """`nature.regional_loss_evidence` is a single-snapshot helper that
    uses HANSEN_LOOKBACK_YEARS observations. The fixed-window choice
    means N_valid passes through to 1.0 (audit §9.3 design)."""

    def test_n_valid_passthrough_one_for_hansen_lookback(self) -> None:
        v = compute_n_valid_term(
            "nature.regional_loss_evidence",
            n_observations=HANSEN_LOOKBACK_YEARS,
            window_days=None,
        )
        assert v == 1.0
