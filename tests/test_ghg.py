"""Synthetic-payload tests for engine.ghg (Milestone 5a).

All tests bypass Earth Engine: `engine.ghg.compute_ghg_indicator_snapshot`
is monkey-patched for `run_pillar` integration tests; the standalone
sub-aggregate / pillar-aggregate tests run on pure-Python payloads.
"""

from __future__ import annotations

import math

import pytest

from engine.ghg import (
    GHG_INDICATOR_CONFIG,
    GhgIndicatorConfig,
    compute_ch4_context_adjusted,
    compute_ch4_hotspot_signal,
    compute_co2_context,
    compute_co2_snapshot,
    compute_combustion_proxy,
    compute_fire_or_regional_transport_risk,
    compute_ghg_audit_followup_priority,
    compute_ghg_data_quality_attribution,
    compute_ghg_spatiotemporal_anomaly,
    compute_ghg_trend,
    compute_core_ghg_audit_support,
    compute_temporal_coverage,
    compute_spatial_resolution_suitability,
    compute_retrieval_inventory_quality,
    compute_nearby_source_isolation,
    compute_activity_score,
    compute_activity_adjusted_co2,
    compute_fossil_combustion_score,
    run_pillar,
)
from engine.exceptions import IndicatorComputeError, PillarComputeError


_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_TIME_RANGE = ("2026-01-01", "2026-04-01")


# ---------------------------------------------------------------------------
# 1. GHG_INDICATOR_CONFIG integrity
# ---------------------------------------------------------------------------

class TestConfigIntegrity:
    def test_two_indicators_registered(self) -> None:
        assert set(GHG_INDICATOR_CONFIG.keys()) == {"ch4", "viirs"}

    @pytest.mark.parametrize("key", list(GHG_INDICATOR_CONFIG.keys()))
    def test_each_entry_has_required_fields(self, key: str) -> None:
        cfg = GHG_INDICATOR_CONFIG[key]
        assert isinstance(cfg, GhgIndicatorConfig)
        assert cfg.asset_id
        assert cfg.band
        assert cfg.scale_factor > 0
        assert cfg.scale_m > 0
        assert cfg.display_unit
        assert cfg.direction in ("higher_is_worse", "lower_is_worse")

    def test_ch4_emits_full_nine_measurement_set(self) -> None:
        assert GHG_INDICATOR_CONFIG["ch4"].emitted_measurements == (
            "site", "background", "anomaly", "z", "hf",
            "trend", "trend_p", "confidence", "score",
        )

    def test_viirs_emits_reduced_five_measurement_set(self) -> None:
        # Per Schema_v2 §3.1: VIIRS NTL omits background, z, hf, trend_p.
        assert GHG_INDICATOR_CONFIG["viirs"].emitted_measurements == (
            "site", "anomaly", "trend", "confidence", "score",
        )


# ---------------------------------------------------------------------------
# 2. compute_co2_snapshot is the wrapper that raises NotImplementedError
# ---------------------------------------------------------------------------

class TestCo2Stub:
    def test_compute_co2_snapshot_raises_with_deferred_message(self) -> None:
        with pytest.raises(NotImplementedError, match="M5.5"):
            compute_co2_snapshot(
                aoi=_AOI, time_range=_TIME_RANGE,
                mode="screening", ee_client=None,
            )

    def test_compute_co2_context_returns_none_in_v1(self) -> None:
        # The sub-aggregate is a different function — it just returns None
        # because ghg.co2.score isn't in the payload until M5.5.
        result = compute_co2_context({})
        assert result == {"ghg.co2_context": None}


# ---------------------------------------------------------------------------
# 3. compute_combustion_proxy borrows from Air payload
# ---------------------------------------------------------------------------

class TestCombustionProxyBorrow:
    def test_borrows_air_industrial_combustion_proxy_value(self) -> None:
        result = compute_combustion_proxy({
            "air.industrial_combustion_proxy": 0.7,
        })
        assert result == {"ghg.combustion_proxy": 0.7}

    def test_returns_none_when_air_value_missing(self) -> None:
        result = compute_combustion_proxy({})
        assert result == {"ghg.combustion_proxy": None}

    def test_returns_none_when_air_value_is_none(self) -> None:
        result = compute_combustion_proxy({
            "air.industrial_combustion_proxy": None,
        })
        assert result == {"ghg.combustion_proxy": None}

    def test_fire_risk_borrows_air_smoke_dust_transport(self) -> None:
        # Parallel structure for the second Air-borrowed sub-aggregate.
        result = compute_fire_or_regional_transport_risk({
            "air.smoke_dust_regional_transport": 0.42,
        })
        assert result == {"ghg.fire_or_regional_transport_risk": 0.42}

    def test_fire_risk_none_when_air_value_missing(self) -> None:
        result = compute_fire_or_regional_transport_risk({})
        assert result == {"ghg.fire_or_regional_transport_risk": None}


# ---------------------------------------------------------------------------
# 4. compute_ch4_context_adjusted formula + clamp
# ---------------------------------------------------------------------------

class TestCh4ContextAdjusted:
    def test_subtracts_one_fifth_of_fire_risk(self) -> None:
        result = compute_ch4_context_adjusted({
            "ghg.ch4.score": 0.50,
            "ghg.fire_or_regional_transport_risk": 0.30,
        })
        # 0.50 − 0.20 × 0.30 = 0.44
        assert result["ghg.ch4_context_adjusted"] == pytest.approx(0.44)

    def test_clamps_negative_result_to_zero(self) -> None:
        result = compute_ch4_context_adjusted({
            "ghg.ch4.score": 0.10,
            "ghg.fire_or_regional_transport_risk": 1.00,
        })
        # 0.10 − 0.20 = -0.10 → clamp to 0.0
        assert result["ghg.ch4_context_adjusted"] == 0.0

    def test_clamps_above_one_to_one(self) -> None:
        # Construct an unrealistic input that would exceed 1 after adjustment.
        result = compute_ch4_context_adjusted({
            "ghg.ch4.score": 1.20,
            "ghg.fire_or_regional_transport_risk": 0.00,
        })
        # 1.20 − 0.0 = 1.20 → clamp to 1.0
        assert result["ghg.ch4_context_adjusted"] == 1.0

    def test_none_when_ch4_score_missing(self) -> None:
        result = compute_ch4_context_adjusted({
            "ghg.fire_or_regional_transport_risk": 0.30,
        })
        assert result == {"ghg.ch4_context_adjusted": None}

    def test_none_when_fire_risk_missing(self) -> None:
        result = compute_ch4_context_adjusted({
            "ghg.ch4.score": 0.50,
        })
        assert result == {"ghg.ch4_context_adjusted": None}


# ---------------------------------------------------------------------------
# 5. compute_ghg_audit_followup_priority — partial-missing renormalisation
# ---------------------------------------------------------------------------

class TestAuditFollowupPartialMissing:
    def test_renormalises_when_trend_aggregate_missing(self) -> None:
        # Trend missing (None) → drop the 0.20 weight, renormalise the rest.
        payload = {
            "ghg.core_audit_support":          0.50,
            "ghg.spatiotemporal_anomaly":      0.40,
            "ghg.trend":                       None,
            "ghg.data_quality_attribution":    0.70,
        }
        out = compute_ghg_audit_followup_priority(payload, mode="trend")
        # Surviving weights: core=0.40, anomaly=0.25, quality=0.15, sum=0.80.
        expected = (0.40 * 0.50 + 0.25 * 0.40 + 0.15 * 0.70) / 0.80
        assert out["ghg.audit_followup_priority"] == pytest.approx(expected)

    def test_returns_none_when_all_inputs_missing(self) -> None:
        out = compute_ghg_audit_followup_priority({}, mode="screening")
        assert out["ghg.audit_followup_priority"] is None


# ---------------------------------------------------------------------------
# 6. run_pillar integration — synthetic, no EE
# ---------------------------------------------------------------------------

def _fake_ch4_snapshot(include_air_keys: bool = False) -> dict:
    """Synthetic CH₄ snapshot. When `include_air_keys` is True, the returned
    dict carries the two Air-borrowed values too — this is how the test
    simulates Air running before GHG (M5c will plumb this through the
    orchestrator).
    """
    snap = {
        "ghg.ch4.site":       1900.0,
        "ghg.ch4.background": 1880.0,
        "ghg.ch4.anomaly":    20.0,
        "ghg.ch4.z":          2.5,
        "ghg.ch4.hf":         0.40,
        "ghg.ch4.trend":      None,
        "ghg.ch4.trend_p":    None,
        "ghg.ch4.confidence": 0.80,
        "ghg.ch4.score":      0.60,
        "_provenance.ghg.ch4": {
            "asset_id":   "COPERNICUS/S5P/OFFL/L3_CH4",
            "time_range": _TIME_RANGE,
        },
    }
    if include_air_keys:
        snap["air.industrial_combustion_proxy"] = 0.70
        snap["air.smoke_dust_regional_transport"] = 0.40
    return snap


def _fake_viirs_snapshot() -> dict:
    return {
        "ghg.viirs.site":       25.0,
        "ghg.viirs.anomaly":    10.0,
        "ghg.viirs.trend":      None,
        "ghg.viirs.confidence": 0.70,
        "ghg.viirs.score":      0.50,
        "_provenance.ghg.viirs": {
            "asset_id":   "NASA/VIIRS/002/VNP46A2",
            "time_range": _TIME_RANGE,
        },
    }


class TestRunPillar:
    def test_full_payload_with_air_keys_injected(self, monkeypatch) -> None:
        # The mock's CH₄ snapshot carries Air keys so the cross-pillar
        # borrow chain has data to work with.
        def fake_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                return _fake_ch4_snapshot(include_air_keys=True)
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError(f"unexpected indicator {indicator!r}")
        monkeypatch.setattr("engine.ghg.compute_ghg_indicator_snapshot", fake_snapshot)

        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators={"ghg.ch4.score", "ghg.viirs.score"},
            ee_client=None,
        )

        # CH₄ full nine-measurement set + VIIRS reduced five-measurement set.
        for measurement in (
            "site", "background", "anomaly", "z", "hf",
            "trend", "trend_p", "confidence", "score",
        ):
            assert f"ghg.ch4.{measurement}" in result
        for measurement in ("site", "anomaly", "trend", "confidence", "score"):
            assert f"ghg.viirs.{measurement}" in result

        # Five computable sub-aggregates non-None (borrow chain worked).
        assert result["ghg.ch4_hotspot_signal"] is not None
        assert result["ghg.combustion_proxy"] == 0.70
        assert result["ghg.activity_score"] == 0.50
        assert result["ghg.fire_or_regional_transport_risk"] == 0.40
        assert result["ghg.ch4_context_adjusted"] is not None

        # Three CO₂-dependent sub-aggregate stubs are None.
        assert result["ghg.co2_context"] is None
        assert result["ghg.fossil_combustion_score"] is None
        assert result["ghg.activity_adjusted_co2"] is None

        # Pillar aggregates produced something.
        assert result["ghg.core_audit_support"] is not None
        assert result["ghg.audit_followup_priority"] is not None

        # No failures.
        assert "_failures" not in result

    def test_borrowed_sub_aggregates_are_none_without_air_injection(
        self, monkeypatch,
    ) -> None:
        # Sanity check on the cross-pillar dependency: without Air keys in
        # the snapshot mock, the borrow yields None and ch4_context_adjusted
        # also null-propagates.
        def fake_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                return _fake_ch4_snapshot(include_air_keys=False)
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError
        monkeypatch.setattr("engine.ghg.compute_ghg_indicator_snapshot", fake_snapshot)

        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators={"ghg.ch4.score", "ghg.viirs.score"},
            ee_client=None,
        )
        assert result["ghg.combustion_proxy"] is None
        assert result["ghg.fire_or_regional_transport_risk"] is None
        assert result["ghg.ch4_context_adjusted"] is None

    def test_single_indicator_failure_degrades_gracefully(self, monkeypatch) -> None:
        def fake_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                raise IndicatorComputeError(
                    indicator_id="ghg.ch4",
                    reason="site buffer has no valid pixels",
                )
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError
        monkeypatch.setattr("engine.ghg.compute_ghg_indicator_snapshot", fake_snapshot)

        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators={"ghg.ch4.score", "ghg.viirs.score"},
            ee_client=None,
        )

        # CH₄'s nine canonical keys are None.
        for measurement in (
            "site", "background", "anomaly", "z", "hf",
            "trend", "trend_p", "confidence", "score",
        ):
            assert result[f"ghg.ch4.{measurement}"] is None

        # VIIRS computed normally.
        assert result["ghg.viirs.score"] == 0.50
        assert result["ghg.activity_score"] == 0.50

        # _failures lists CH₄.
        assert "_failures" in result
        assert len(result["_failures"]) == 1
        assert result["_failures"][0]["indicator"] == "ch4"
        assert result["_failures"][0]["indicator_id"] == "ghg.ch4"
        assert "no valid pixels" in result["_failures"][0]["reason"]

    def test_all_indicators_failing_raises_pillar_compute_error(
        self, monkeypatch,
    ) -> None:
        def fake_snapshot(aoi, indicator, time_range, mode, ee_client):
            raise IndicatorComputeError(
                indicator_id=f"ghg.{indicator}",
                reason="no valid pixels",
            )
        monkeypatch.setattr("engine.ghg.compute_ghg_indicator_snapshot", fake_snapshot)

        with pytest.raises(PillarComputeError) as excinfo:
            run_pillar(
                aoi=_AOI,
                time_range=_TIME_RANGE,
                mode="screening",
                selected_indicators={"ghg.ch4.score", "ghg.viirs.score"},
                ee_client=None,
            )

        err = excinfo.value
        assert err.pillar == "ghg"
        # CH₄ contributes 9 measurement IDs, VIIRS contributes 5. 14 total.
        assert len(err.indicator_ids) == 9 + 5
        # Spot-check.
        assert "ghg.ch4.score" in err.indicator_ids
        assert "ghg.viirs.confidence" in err.indicator_ids


# ---------------------------------------------------------------------------
# Sanity tests for the smaller helpers
# ---------------------------------------------------------------------------

class TestQualitySubScores:
    def test_temporal_coverage_proxies_ch4_confidence(self) -> None:
        out = compute_temporal_coverage({"ghg.ch4.confidence": 0.82})
        assert out == {"ghg.temporal_coverage": 0.82}

    def test_temporal_coverage_none_when_ch4_missing(self) -> None:
        out = compute_temporal_coverage({})
        assert out == {"ghg.temporal_coverage": None}

    def test_spatial_resolution_suitability_saturates_for_big_buffer(self) -> None:
        # CH4_NATIVE_SCALE_M = 7000 m. A 50 km buffer → ratio 50000/7000 ≈ 7.14
        # → clamps to 1.0.
        out = compute_spatial_resolution_suitability(
            {"centre": {"lat": 0, "lon": 0}, "radius_km": 50},
        )
        assert out["ghg.spatial_resolution_suitability"] == 1.0

    def test_spatial_resolution_suitability_scales_for_small_buffer(self) -> None:
        # Radius 1 km → ratio 1000/7000 ≈ 0.143.
        out = compute_spatial_resolution_suitability(
            {"centre": {"lat": 0, "lon": 0}, "radius_km": 1},
        )
        assert out["ghg.spatial_resolution_suitability"] == pytest.approx(1000 / 7000)

    def test_retrieval_inventory_quality_is_fixed_placeholder(self) -> None:
        assert compute_retrieval_inventory_quality({}) == {
            "ghg.retrieval_inventory_quality": 0.7,
        }

    def test_nearby_source_isolation_is_fixed_placeholder(self) -> None:
        assert compute_nearby_source_isolation({}) == {
            "ghg.nearby_source_isolation": 1.0,
        }


class TestCh4HotspotSignal:
    def test_returns_score_when_z_at_or_above_threshold(self) -> None:
        # ANOMALY_Z_THRESHOLD = 2.0
        out = compute_ch4_hotspot_signal({"ghg.ch4.score": 0.6, "ghg.ch4.z": 2.5})
        assert out["ghg.ch4_hotspot_signal"] == 0.6

    def test_returns_zero_below_threshold(self) -> None:
        out = compute_ch4_hotspot_signal({"ghg.ch4.score": 0.6, "ghg.ch4.z": 1.0})
        assert out["ghg.ch4_hotspot_signal"] == 0.0

    def test_returns_none_when_z_missing(self) -> None:
        out = compute_ch4_hotspot_signal({"ghg.ch4.score": 0.6})
        assert out["ghg.ch4_hotspot_signal"] is None


class TestCo2DependentStubs:
    def test_fossil_combustion_score_none_when_co2_missing(self) -> None:
        # CO₂ context is None in v1, so the formula null-propagates.
        out = compute_fossil_combustion_score({
            "ghg.co2_context":      None,
            "ghg.combustion_proxy": 0.5,
        })
        assert out["ghg.fossil_combustion_score"] is None

    def test_activity_adjusted_co2_none_when_co2_missing(self) -> None:
        out = compute_activity_adjusted_co2({
            "ghg.co2_context":   None,
            "ghg.activity_score": 0.5,
        })
        assert out["ghg.activity_adjusted_co2"] is None

    def test_activity_score_aliases_viirs_score(self) -> None:
        out = compute_activity_score({"ghg.viirs.score": 0.42})
        assert out == {"ghg.activity_score": 0.42}


class TestCoreGhgAuditSupport:
    def test_renormalises_over_present_terms_without_co2(self) -> None:
        # No CO₂ context in v1 → renormalise over the three non-CO₂ terms.
        payload = {
            "ghg.ch4_context_adjusted": 0.50,
            "ghg.combustion_proxy":     0.40,
            "ghg.activity_score":       0.30,
        }
        selected = {
            "ghg.ch4_context_adjusted",
            "ghg.combustion_proxy",
            "ghg.activity_score",
        }
        out = compute_core_ghg_audit_support(payload, selected)
        # CORE_GHG_AUDIT_SUPPORT_WEIGHTS = co2=0.39, ch4_adj=0.28,
        # combustion=0.22, activity=0.11. Without co2 the renormalised
        # denominator is 0.28 + 0.22 + 0.11 = 0.61.
        expected = (0.28 * 0.50 + 0.22 * 0.40 + 0.11 * 0.30) / 0.61
        assert out["ghg.core_audit_support"] == pytest.approx(expected)


class TestGhgTrendModeHandling:
    def test_screening_returns_zero(self) -> None:
        out = compute_ghg_trend(payload={}, selected=set(), mode="screening")
        assert out["ghg.trend"] == 0.0

    def test_trend_mode_returns_none_when_all_trends_none(self) -> None:
        out = compute_ghg_trend(
            payload={"ghg.ch4.trend": None},
            selected={"ghg.ch4.score"},
            mode="trend",
        )
        assert out["ghg.trend"] is None
