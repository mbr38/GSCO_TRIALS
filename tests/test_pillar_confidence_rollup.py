"""Pillar-level rollup canary tests for M-TIER-A1.

Tests the three rollup patterns the spec §4 commits to:
1. Air — uniform mean of survivors (no weight dict).
2. GHG — `GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS`-driven sub-score rollup,
   where three of four sub-scores re-derive from per-indicator A1 terms
   read from provenance.extra.confidence_terms.
3. Nature — `valid_pixel_coverage` re-derives from per-indicator A1 QA
   terms; other Nature sub-scores stay independent per spec §4.3.

Plus the universal survivor-renormalise / strict-None behaviour at the
pillar boundary (architectural rule M-FOLLOWUP-FALLBACK).

Added by M-TIER-A1 per the spec's §6/§7.
"""

from __future__ import annotations

import pytest

from engine.constants import GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS
from engine.core.confidence import compute_pillar_confidence
from engine.ghg import (
    compute_retrieval_inventory_quality,
    compute_spatial_resolution_suitability,
    compute_temporal_coverage,
)
from engine.nature import compute_nature_quality_sub_scores


# ---------------------------------------------------------------------------
# Universal pillar rollup
# ---------------------------------------------------------------------------

class TestComputePillarConfidence:
    def test_uniform_mean_when_no_weights_supplied(self) -> None:
        # Air-style rollup: per-pollutant confidences averaged uniformly.
        out = compute_pillar_confidence({
            "air.no2": 0.9, "air.so2": 0.7, "air.co": 0.6,
        })
        assert out == pytest.approx((0.9 + 0.7 + 0.6) / 3)

    def test_survivor_renormalise_drops_none_inputs(self) -> None:
        # 2 of 4 None → other 2 still produce a real value (survivor rule).
        out = compute_pillar_confidence({
            "air.no2": 0.9, "air.so2": None, "air.co": 0.6, "air.hcho": None,
        })
        assert out == pytest.approx((0.9 + 0.6) / 2)

    def test_all_none_returns_none(self) -> None:
        # Strict-None when every input is missing.
        out = compute_pillar_confidence({
            "air.no2": None, "air.so2": None,
        })
        assert out is None

    def test_empty_dict_returns_none(self) -> None:
        # No indicators selected → no rollup.
        assert compute_pillar_confidence({}) is None

    def test_weighted_rollup_renormalises_to_present_weights(self) -> None:
        # GHG-style: weight dict driven; only relevant keys participate.
        per_ind = {"a": 0.8, "b": 0.4, "c": 0.6}
        weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        # All present → weighted sum directly: 0.5·0.8 + 0.3·0.4 + 0.2·0.6 = 0.64
        out = compute_pillar_confidence(per_ind, weights=weights)
        assert out == pytest.approx(0.5 * 0.8 + 0.3 * 0.4 + 0.2 * 0.6)

    def test_weighted_rollup_survivor_renormalise(self) -> None:
        # When `b` is None, the remaining {a, c} renormalise:
        # weights_r["a"] = 0.5 / (0.5 + 0.2) = 5/7
        # weights_r["c"] = 0.2 / 0.7 = 2/7
        # out = (5/7)·0.8 + (2/7)·0.6
        per_ind = {"a": 0.8, "b": None, "c": 0.6}
        weights = {"a": 0.5, "b": 0.3, "c": 0.2}
        out = compute_pillar_confidence(per_ind, weights=weights)
        expected = (5 / 7) * 0.8 + (2 / 7) * 0.6
        assert out == pytest.approx(expected)


# ---------------------------------------------------------------------------
# GHG_DQA sub-scores recompute from per-indicator inputs
# ---------------------------------------------------------------------------

class TestGhgDqaSubScoreRecompute:
    """Pin spec §4.2 — three GHG sub-scores derive from per-indicator
    A1 inputs (`N_valid`, `spatial_context`, `QA`); the fourth
    (`nearby_source_isolation`) stays independent."""

    @staticmethod
    def _payload(**per_indicator) -> dict:
        return {
            f"_provenance.ghg.{ind}": {"extra": {"confidence_terms": terms}}
            for ind, terms in per_indicator.items()
        }

    def test_temporal_coverage_means_n_valid_across_indicators(self) -> None:
        payload = self._payload(
            ch4={"n_valid": 0.8},
            co2={"n_valid": 1.0},
            viirs={"n_valid": 0.6},
        )
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx((0.8 + 1.0 + 0.6) / 3),
        }

    def test_spatial_resolution_suitability_means_spatial_context(self) -> None:
        payload = self._payload(
            ch4={"spatial_context": 0.4},
            co2={"spatial_context": 1.0},
            viirs={"spatial_context": 1.0},
        )
        out = compute_spatial_resolution_suitability(payload)
        assert out["ghg.spatial_resolution_suitability"] == pytest.approx(
            (0.4 + 1.0 + 1.0) / 3
        )

    def test_retrieval_inventory_quality_means_per_indicator_qa(self) -> None:
        payload = self._payload(
            ch4={"qa": 0.85},
            co2={"qa": 1.0},
            viirs={"qa": 0.85},
        )
        out = compute_retrieval_inventory_quality(payload)
        assert out["ghg.retrieval_inventory_quality"] == pytest.approx(
            (0.85 + 1.0 + 0.85) / 3
        )

    def test_sub_scores_survive_when_only_some_indicators_emit(self) -> None:
        # Only ch4 emitted (ODIAC skipped via coverage_window; VIIRS not
        # selected) — temporal_coverage still produces a real value.
        payload = self._payload(ch4={"n_valid": 0.9, "qa": 0.85, "spatial_context": 0.5})
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx(0.9),
        }
        assert compute_retrieval_inventory_quality(payload) == {
            "ghg.retrieval_inventory_quality": pytest.approx(0.85),
        }
        assert compute_spatial_resolution_suitability(payload) == {
            "ghg.spatial_resolution_suitability": pytest.approx(0.5),
        }

    def test_sub_scores_are_none_when_no_indicators_emit_terms(self) -> None:
        assert compute_temporal_coverage({}) == {"ghg.temporal_coverage": None}
        assert compute_retrieval_inventory_quality({}) == {
            "ghg.retrieval_inventory_quality": None,
        }
        assert compute_spatial_resolution_suitability({}) == {
            "ghg.spatial_resolution_suitability": None,
        }

    def test_weight_dict_unchanged_by_a1(self) -> None:
        # Spec §4.2 preserves the sums-to-1.00 weighting; A1 only rewires
        # the four named sub-scores' derivation, not their pillar weights.
        assert sum(GHG_DATA_QUALITY_ATTRIBUTION_WEIGHTS.values()) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Nature valid_pixel_coverage recompute (spec §4.3)
# ---------------------------------------------------------------------------

class TestNatureValidPixelCoverageRecompute:
    """Pin spec §4.3 — `nature.valid_pixel_coverage` is the mean of
    per-indicator A1 QA across the Nature indicators that emitted terms.
    Replaces the pre-A1 echo of `dw.class_confidence`."""

    @staticmethod
    def _payload(**per_indicator) -> dict:
        return {
            f"_provenance.nature.{ind}": {"extra": {"confidence_terms": terms}}
            for ind, terms in per_indicator.items()
        }

    def test_valid_pixel_coverage_means_per_indicator_qa(self) -> None:
        payload = self._payload(
            kba={"qa": 1.0},
            dw={"qa": 0.9},
            habitat={"qa": 0.85},
            forest_loss={"qa": 1.0},
            ndvi={"qa": 0.9},
            water={"qa": 0.9},
            recovery={"qa": 0.85},
            regional_loss_evidence={"qa": 1.0},
        )
        out = compute_nature_quality_sub_scores(payload, aoi={"radius_km": 5})
        expected = (1.0 + 0.9 + 0.85 + 1.0 + 0.9 + 0.9 + 0.85 + 1.0) / 8
        assert out["nature.valid_pixel_coverage"] == pytest.approx(expected)

    def test_valid_pixel_coverage_skips_missing_indicators(self) -> None:
        # Only KBA + DW emitted → use the two we have.
        payload = self._payload(kba={"qa": 1.0}, dw={"qa": 0.9})
        out = compute_nature_quality_sub_scores(payload, aoi={"radius_km": 5})
        assert out["nature.valid_pixel_coverage"] == pytest.approx((1.0 + 0.9) / 2)

    def test_valid_pixel_coverage_none_when_no_indicators_emit(self) -> None:
        out = compute_nature_quality_sub_scores({}, aoi={"radius_km": 5})
        assert out["nature.valid_pixel_coverage"] is None

    def test_other_nature_sub_scores_unchanged_by_a1(self) -> None:
        # spec §4.3 explicitly preserves these — placeholders unchanged.
        out = compute_nature_quality_sub_scores({}, aoi={"radius_km": 5})
        assert out["nature.cloud_observation_quality"] == 0.8
        assert out["nature.seasonal_comparability"]    == 1.0
        assert out["nature.supplier_spatial_link"]     == 0.7

    def test_external_driver_screening_not_emitted_here(self) -> None:
        # Audit §9.3 — emitted by compute_regional_loss_evidence in
        # run_pillar, not by this function. The pre-A1 placeholder of
        # 1.0 was removed by M-V1x-RECONCILE.
        out = compute_nature_quality_sub_scores({}, aoi={"radius_km": 5})
        assert "nature.external_driver_screening" not in out


# ---------------------------------------------------------------------------
# D3.1 (M-TIER-A1 Step D) — re-derivation coverage with explicit "recomputes
# from per-indicator terms" framing + the missing strict-None edge cases.
#
# The TestGhgDqaSubScoreRecompute / TestNatureValidPixelCoverageRecompute
# classes above already cover the well-formed payload shape (indicator
# entirely absent ⇄ indicator present with full confidence_terms). The
# tests below extend coverage to *malformed* provenance — where the
# indicator's provenance exists but its `extra.confidence_terms` is
# missing or partially missing. This is the realistic in-engine case
# when an indicator's snapshot ran but the confidence helper hit
# strict-None on one of its inputs (e.g. anomaly_strength=None when
# six_step's HF computation returned None on a degenerate background).
# ---------------------------------------------------------------------------


class TestGhgDqaRederivationStrictNone:
    """D3.1 — strict-None propagation when an indicator's provenance is
    present but `extra.confidence_terms` is missing or partial.

    These cases were uncovered before D3.1 because the existing
    TestGhgDqaSubScoreRecompute tests use the "indicator entirely absent"
    shape, where the rollup never has to consult `extra.confidence_terms`.
    """

    @staticmethod
    def _payload_with_raw_provenance(**per_indicator_provenance) -> dict:
        # Caller supplies the entire provenance dict per indicator
        # (whatever shape we want to exercise).
        return {
            f"_provenance.ghg.{ind}": prov
            for ind, prov in per_indicator_provenance.items()
        }

    def test_ghg_temporal_coverage_recomputes_from_per_indicator_n_valid(
        self,
    ) -> None:
        # Explicit "recomputes from per-indicator" naming for
        # discoverability. Same shape as TestGhgDqaSubScoreRecompute's
        # equivalent, kept as a thin alias so a future grep on
        # "recomputes_from_per_indicator" surfaces all the rollup paths.
        payload = {
            f"_provenance.ghg.{ind}": {"extra": {"confidence_terms": {"n_valid": v}}}
            for ind, v in [("ch4", 0.6), ("co2", 0.9), ("viirs", 0.3)]
        }
        out = compute_temporal_coverage(payload)
        assert out["ghg.temporal_coverage"] == pytest.approx((0.6 + 0.9 + 0.3) / 3)

    def test_ghg_spatial_resolution_suitability_recomputes_from_per_indicator_spatial_context(
        self,
    ) -> None:
        payload = {
            f"_provenance.ghg.{ind}": {"extra": {"confidence_terms": {"spatial_context": v}}}
            for ind, v in [("ch4", 0.5), ("co2", 1.0), ("viirs", 0.8)]
        }
        out = compute_spatial_resolution_suitability(payload)
        assert out["ghg.spatial_resolution_suitability"] == pytest.approx(
            (0.5 + 1.0 + 0.8) / 3
        )

    def test_ghg_retrieval_inventory_quality_recomputes_from_per_indicator_qa(
        self,
    ) -> None:
        payload = {
            f"_provenance.ghg.{ind}": {"extra": {"confidence_terms": {"qa": v}}}
            for ind, v in [("ch4", 0.85), ("co2", 1.00), ("viirs", 0.85)]
        }
        out = compute_retrieval_inventory_quality(payload)
        assert out["ghg.retrieval_inventory_quality"] == pytest.approx(
            (0.85 + 1.00 + 0.85) / 3
        )

    def test_strict_none_propagation_when_one_indicator_has_no_confidence_terms(
        self,
    ) -> None:
        # ch4 has confidence_terms; co2 has provenance but no extra dict;
        # viirs has provenance with extra={} but no confidence_terms key.
        # All three "missing" shapes should produce the same result: drop
        # that indicator from the rollup via survivor-renormalise rather
        # than crash or silently zero.
        payload = self._payload_with_raw_provenance(
            ch4={"extra": {"confidence_terms": {"n_valid": 0.7, "qa": 0.85, "spatial_context": 0.6}}},
            co2={},                                # no extra dict at all
            viirs={"extra": {}},                   # extra dict empty
        )
        # Only ch4 contributes a survivor.
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx(0.7),
        }
        assert compute_retrieval_inventory_quality(payload) == {
            "ghg.retrieval_inventory_quality": pytest.approx(0.85),
        }
        assert compute_spatial_resolution_suitability(payload) == {
            "ghg.spatial_resolution_suitability": pytest.approx(0.6),
        }

    def test_strict_none_when_confidence_terms_key_value_is_none(self) -> None:
        # The per-term lookup `terms.get(term)` returns None when the
        # specific term is missing OR explicitly None. The reader's
        # type check `isinstance(value, (int, float))` is what filters
        # this out; verify it does.
        payload = self._payload_with_raw_provenance(
            ch4={"extra": {"confidence_terms": {
                "n_valid": None,         # explicitly None — should drop
                "qa":      0.85,
                "spatial_context": 0.6,
            }}},
            co2={"extra": {"confidence_terms": {
                "n_valid": 0.9,
                "qa":      0.95,
                "spatial_context": 0.7,
            }}},
        )
        # Only co2 contributes to temporal_coverage; ch4's None n_valid drops.
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx(0.9),
        }
        # But ch4's qa is real → contributes to retrieval_inventory_quality.
        assert compute_retrieval_inventory_quality(payload) == {
            "ghg.retrieval_inventory_quality": pytest.approx((0.85 + 0.95) / 2),
        }


class TestNatureValidPixelCoverageRederivationStrictNone:
    """D3.1 — Nature mirror of the GHG strict-None tests."""

    @staticmethod
    def _payload_with_raw_provenance(**per_indicator_provenance) -> dict:
        return {
            f"_provenance.nature.{ind}": prov
            for ind, prov in per_indicator_provenance.items()
        }

    def test_nature_valid_pixel_coverage_recomputes_from_per_indicator_qa(
        self,
    ) -> None:
        payload = {
            f"_provenance.nature.{ind}": {"extra": {"confidence_terms": {"qa": v}}}
            for ind, v in [
                ("kba",         1.0),
                ("dw",          0.9),
                ("habitat",     0.85),
                ("forest_loss", 1.0),
                ("ndvi",        0.9),
                ("water",       0.9),
                ("recovery",    0.85),
                ("regional_loss_evidence", 1.0),
            ]
        }
        out = compute_nature_quality_sub_scores(payload, aoi={"radius_km": 5})
        expected = (1.0 + 0.9 + 0.85 + 1.0 + 0.9 + 0.9 + 0.85 + 1.0) / 8
        assert out["nature.valid_pixel_coverage"] == pytest.approx(expected)

    def test_nature_strict_none_propagation_with_malformed_provenance(self) -> None:
        # kba has terms; dw provenance lacks extra entirely; habitat has
        # extra={}; ndvi has confidence_terms but qa is None. Only kba
        # and any other "real" survivor should contribute.
        payload = self._payload_with_raw_provenance(
            kba={"extra": {"confidence_terms": {"qa": 1.0}}},
            dw={},
            habitat={"extra": {}},
            ndvi={"extra": {"confidence_terms": {"qa": None}}},
            forest_loss={"extra": {"confidence_terms": {"qa": 0.85}}},
        )
        out = compute_nature_quality_sub_scores(payload, aoi={"radius_km": 5})
        # Survivors: kba (1.0) and forest_loss (0.85).
        assert out["nature.valid_pixel_coverage"] == pytest.approx(
            (1.0 + 0.85) / 2
        )
