"""Synthetic-payload tests for engine.ghg (Milestones 5a + 5c + 5.5).

All tests bypass Earth Engine: `engine.ghg.compute_ghg_indicator_snapshot`
and `engine.ghg.compute_co2_snapshot` are monkey-patched for `run_pillar`
integration tests; the standalone sub-aggregate / pillar-aggregate tests
run on pure-Python payloads.

Real-EE smoke tests for CO₂ live in tests/test_ghg_integration.py
(skipped unless RUN_EE_TESTS=1).
"""

from __future__ import annotations

import math

import pytest

from engine.constants import CO2_TO_C_RATIO
from engine.ghg import (
    GHG_INDICATOR_CONFIG,
    GhgIndicatorConfig,
    _co2_relative_intensity_and_score,
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
# 0. _time_range_in_coverage helper (M5.5c)
# ---------------------------------------------------------------------------

class TestTimeRangeCoverage:
    def test_none_coverage_always_returns_true(self) -> None:
        from engine.ghg import _time_range_in_coverage
        assert _time_range_in_coverage(("2026-01-01", "2026-04-01"), None) is True

    def test_overlapping_range_returns_true(self) -> None:
        from engine.ghg import _time_range_in_coverage
        # User range straddles the end of coverage.
        assert _time_range_in_coverage(
            ("2023-10-01", "2024-03-01"),
            ("2020-01-01", "2023-12-31"),
        ) is True

    def test_fully_outside_after_coverage_returns_false(self) -> None:
        from engine.ghg import _time_range_in_coverage
        assert _time_range_in_coverage(
            ("2026-01-01", "2026-04-01"),
            ("2020-01-01", "2023-12-31"),
        ) is False

    def test_fully_outside_before_coverage_returns_false(self) -> None:
        from engine.ghg import _time_range_in_coverage
        assert _time_range_in_coverage(
            ("2015-01-01", "2015-04-01"),
            ("2020-01-01", "2023-12-31"),
        ) is False

    def test_fully_inside_coverage_returns_true(self) -> None:
        from engine.ghg import _time_range_in_coverage
        assert _time_range_in_coverage(
            ("2022-01-01", "2022-04-01"),
            ("2020-01-01", "2023-12-31"),
        ) is True


# ---------------------------------------------------------------------------
# 1. GHG_INDICATOR_CONFIG integrity
# ---------------------------------------------------------------------------

class TestConfigIntegrity:
    def test_three_indicators_registered(self) -> None:
        # M5.5 added CO₂ via ODIAC; M5a had only CH₄ + VIIRS.
        assert set(GHG_INDICATOR_CONFIG.keys()) == {"ch4", "viirs", "co2"}

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

    def test_co2_emits_seven_measurement_set(self) -> None:
        # Per Schema_v2 §3.1 (M5.5 update): CO₂ uses a custom 7-key set
        # with `.relative_intensity` replacing the old `.anomaly`.
        assert GHG_INDICATOR_CONFIG["co2"].emitted_measurements == (
            "mean", "total", "relative_intensity",
            "trend", "trend_p", "confidence", "score",
        )

    def test_co2_asset_id_and_native_scale(self) -> None:
        cfg = GHG_INDICATOR_CONFIG["co2"]
        assert cfg.asset_id == "projects/supply-chain-observatory/assets/odiac"
        assert cfg.band == "b1"
        assert cfg.scale_m == 1000.0
        assert "CO₂" in cfg.display_unit or "CO2" in cfg.display_unit

    def test_co2_has_coverage_window_set(self) -> None:
        # M5.5c — ODIAC publishes annual grids 2020-2023.
        cfg = GHG_INDICATOR_CONFIG["co2"]
        assert cfg.coverage_window == ("2020-01-01", "2023-12-31")

    def test_ch4_and_viirs_have_no_coverage_window(self) -> None:
        # Sentinel-5P CH₄ and VIIRS NTL are both still actively updated.
        assert GHG_INDICATOR_CONFIG["ch4"].coverage_window is None
        assert GHG_INDICATOR_CONFIG["viirs"].coverage_window is None

    def test_co2_data_type_is_inventory(self) -> None:
        cfg = GHG_INDICATOR_CONFIG["co2"]
        assert cfg.data_type == "emissions_inventory_allocation"

    def test_ch4_and_viirs_data_type_is_satellite(self) -> None:
        assert GHG_INDICATOR_CONFIG["ch4"].data_type == "satellite_observation"
        assert GHG_INDICATOR_CONFIG["viirs"].data_type == "satellite_observation"


# ---------------------------------------------------------------------------
# 2. compute_co2_snapshot — M5.5 activated ODIAC implementation
# ---------------------------------------------------------------------------

class _FakeReducerResult:
    """Stand-in for ee.Image.reduceRegion result.

    M-AIR-GHG-DEFENSIVE: ``compute_co2_snapshot`` now materialises the
    reduction dict via ``reduceRegion(...).getInfo()`` and then calls
    ``.get(cfg.band)`` on the Python dict (rather than the previous
    server-side ``.get(band).getInfo()`` chain). This stub returns a
    dict shaped like a real EE reduction so the new defensive pattern
    sees a normal-looking response. ``band`` is set per call so each of
    the three reductions (site sum, site mean, ring mean) returns its
    own value.
    """

    def __init__(self, value: float, band: str = "b1") -> None:
        self._value = value
        self._band = band

    def getInfo(self) -> dict:
        return {self._band: self._value}


class _FakeSummedImage:
    """Stand-in for the `ic.sum()` result. Tracks reduceRegion(geometry=...)
    calls so the test can route site vs ring reductions to different values.
    """

    def __init__(self, *, site_sum: float, site_mean: float, ring_mean: float) -> None:
        self._site_sum = site_sum
        self._site_mean = site_mean
        self._ring_mean = ring_mean
        # Tracks the order of reduceRegion calls per (reducer_kind, geom_id).
        self._call_log: list[tuple[str, int]] = []

    def reduceRegion(self, reducer, geometry, **_kw):     # noqa: N803 — EE API name
        # Geometry comes from monkey-patched site_buffer / background_ring;
        # we use id() to distinguish them.
        reducer_kind = type(reducer).__name__
        geom_id = id(geometry)
        self._call_log.append((reducer_kind, geom_id))
        # The reducer types EE returns are stubbed so they don't carry
        # introspectable kind info; we route by call order instead because
        # compute_co2_snapshot always calls: (site sum, site mean, ring mean).
        idx = len(self._call_log) - 1
        if idx == 0:
            return _FakeReducerResult(self._site_sum)
        if idx == 1:
            return _FakeReducerResult(self._site_mean)
        return _FakeReducerResult(self._ring_mean)


class _FakeIc:
    """Chain-friendly stand-in for ee.ImageCollection mirrored after the
    Air fake — supports filterDate, size().getInfo(), select(), sum().
    """

    def __init__(
        self, *, n_months: int, site_sum: float, site_mean: float, ring_mean: float,
    ) -> None:
        self._n_months = n_months
        self._site_sum = site_sum
        self._site_mean = site_mean
        self._ring_mean = ring_mean

    def filterDate(self, *_a, **_kw):
        return self

    def size(self):
        class _Size:
            def __init__(inner_self, n): inner_self._n = n
            def getInfo(inner_self): return inner_self._n
        return _Size(self._n_months)

    def select(self, _band):
        return self

    def sum(self):
        return _FakeSummedImage(
            site_sum=self._site_sum,
            site_mean=self._site_mean,
            ring_mean=self._ring_mean,
        )


@pytest.fixture
def fake_co2_ee(monkeypatch):
    """Replace EE surfaces used by compute_co2_snapshot.

    Returns a factory that installs a synthetic ImageCollection with the
    given per-pixel and ring statistics. Also stubs `ee.Reducer.sum` and
    `ee.Reducer.mean` because the real EE client requires an initialised
    session to construct Reducer instances.
    """
    def install(*, n_months: int = 3, site_sum: float = 100.0,
                site_mean: float = 5.0, ring_mean: float = 1.0):
        fake_ic = _FakeIc(
            n_months=n_months, site_sum=site_sum,
            site_mean=site_mean, ring_mean=ring_mean,
        )
        monkeypatch.setattr(
            "engine.ghg.ee.ImageCollection", lambda *_a, **_kw: fake_ic,
        )
        # Reducer.* doesn't work without an EE session — stub it to a
        # sentinel; _FakeSummedImage.reduceRegion ignores the reducer arg
        # anyway and routes by call order.
        class _FakeReducerKind:
            pass
        monkeypatch.setattr(
            "engine.ghg.ee.Reducer",
            type("FakeReducer", (), {
                "sum":  staticmethod(lambda: _FakeReducerKind()),
                "mean": staticmethod(lambda: _FakeReducerKind()),
            }),
        )
        # site_buffer / background_ring just need to return distinguishable
        # objects — actual geometry isn't inspected by the fake.
        monkeypatch.setattr(
            "engine.ghg.site_buffer", lambda *_a, **_kw: object(),
        )
        # M-TIER-A3 Step B — background_ring returns a dict; ghg.py
        # extracts `["geometry"]`. Wrap the sentinel so the call site
        # still receives a distinguishable opaque object.
        monkeypatch.setattr(
            "engine.ghg.background_ring",
            lambda *_a, **_kw: {
                "geometry": object(),
                "mask": None,
                "land_fraction": 1.0,
                "land_mask_applied": True,
                "land_mask_asset": "MODIS/006/MOD44W",
            },
        )
        return fake_ic
    return install


_AOI_CO2 = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_CO2_TIME_RANGE = ("2023-01-01", "2023-04-01")


class TestCo2Snapshot:
    def test_compute_co2_snapshot_returns_seven_measurement_set(
        self, fake_co2_ee,
    ) -> None:
        fake_co2_ee(n_months=3, site_sum=100.0, site_mean=5.0, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        for measurement in (
            "mean", "total", "relative_intensity",
            "trend", "trend_p", "confidence", "score",
        ):
            assert f"ghg.co2.{measurement}" in result
        # Provenance carries the audit-traceable conversion factor and
        # (M5.5c) the inventory-vs-observation honesty fields. M5.6 moved
        # n_months into observations.count and c_to_co2_factor into extra;
        # allocation_method folded into method_note; role_in_pillar dropped.
        prov = result["_provenance.ghg.co2"]
        assert prov["asset_id"] == "projects/supply-chain-observatory/assets/odiac"
        assert prov["band"] == "b1"
        assert prov["observations"]["count"] == 3
        assert prov["observations"]["unit"] == "monthly_grids"
        assert prov["extra"]["c_to_co2_factor"] == pytest.approx(CO2_TO_C_RATIO)
        assert prov["data_type"] == "emissions_inventory_allocation"
        assert prov["data_source"] == "ODIAC / NIES Japan"
        assert prov["method_note"] is not None
        assert "CARMA" in prov["method_note"]
        # M5.5b's role_in_pillar field was dropped in M5.6 — data_type
        # carries the same information more honestly.
        assert "role_in_pillar" not in prov

    def test_compute_co2_snapshot_score_clamps_to_zero_below_regional(
        self, fake_co2_ee,
    ) -> None:
        # site mean < ring mean → relative_intensity < 1 → score = 0.
        fake_co2_ee(n_months=3, site_sum=10.0, site_mean=0.5, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["ghg.co2.score"] == 0.0
        # relative_intensity is reported as the raw 0.5; it's the SCORE that's clamped.
        assert result["ghg.co2.relative_intensity"] == pytest.approx(0.5)

    def test_compute_co2_snapshot_score_saturates_at_ten_times(
        self, fake_co2_ee,
    ) -> None:
        # site_mean = 10 × ring_mean → relative_intensity = 10 → score = 1.
        fake_co2_ee(n_months=3, site_sum=100.0, site_mean=10.0, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["ghg.co2.score"] == pytest.approx(1.0)

    def test_compute_co2_snapshot_score_midpoint_at_sqrt_ten(
        self, fake_co2_ee,
    ) -> None:
        # log10(sqrt(10)) / log10(10) = 0.5 — verifies the log scaling.
        fake_co2_ee(
            n_months=3, site_sum=100.0,
            site_mean=math.sqrt(10.0), ring_mean=1.0,
        )
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        assert result["ghg.co2.score"] == pytest.approx(0.5, abs=1e-6)

    def test_compute_co2_snapshot_total_conversion_factor(
        self, fake_co2_ee,
    ) -> None:
        # site_sum = 100 t C summed over 3 monthly grids. Annualisation
        # factor = 12 / 3 = 4. CO₂ conversion = 44/12. So total in t CO₂/yr
        # = 100 × 4 × (44/12) ≈ 1466.67.
        fake_co2_ee(n_months=3, site_sum=100.0, site_mean=5.0, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        expected_total = 100.0 * (12.0 / 3.0) * CO2_TO_C_RATIO
        assert result["ghg.co2.total"] == pytest.approx(expected_total)

    def test_compute_co2_snapshot_pixel_size_guard(self) -> None:
        # ODIAC native pixel is 1 km — a 0.5 km buffer fails before any EE
        # call so we don't need the fake.
        with pytest.raises(IndicatorComputeError, match=r"smaller than ODIAC"):
            compute_co2_snapshot(
                aoi={"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 0.5},
                time_range=_CO2_TIME_RANGE,
                mode="screening", ee_client=None,
            )

    # M5.5c — `test_compute_co2_snapshot_empty_time_range` was removed
    # along with the `n_months == 0` raise inside compute_co2_snapshot.
    # Out-of-coverage handling moved to run_pillar (TestPresentDayScreeningSkipsOdiac).


class TestCo2RelativeIntensityHelper:
    def test_returns_none_when_ring_mean_zero(self) -> None:
        # Division-by-zero guard.
        rel, score = _co2_relative_intensity_and_score(site_mean=5.0, ring_mean=0.0)
        assert rel is None
        assert score is None

    def test_caps_relative_intensity_at_ten(self) -> None:
        # 100× regional background → capped at 10× (CARMA-overlap proxy).
        rel, score = _co2_relative_intensity_and_score(site_mean=100.0, ring_mean=1.0)
        assert rel == pytest.approx(10.0)
        assert score == pytest.approx(1.0)


class TestCo2ContextActivation:
    def test_compute_co2_context_returns_score_when_present(self) -> None:
        # M5.5 — co2.score is now present in payload after compute_co2_snapshot.
        result = compute_co2_context({"ghg.co2.score": 0.42})
        assert result == {"ghg.co2_context": 0.42}

    def test_compute_co2_context_returns_none_when_score_missing(self) -> None:
        # CO₂ unselected or compute_co2_snapshot failed → graceful null.
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
# 5. compute_ghg_audit_followup_priority — strict-None propagation
# (M-FOLLOWUP-FALLBACK)
# ---------------------------------------------------------------------------

class TestAuditFollowupPartialMissing:
    def test_returns_none_when_trend_aggregate_missing(self) -> None:
        """M-FOLLOWUP-FALLBACK: any missing sub-aggregate → priority is
        None. The prior renormalise-over-survivors behaviour silently
        rebalanced the formula and produced misleading scores when
        upstream signals had failed."""
        payload = {
            "ghg.core_audit_support":          0.50,
            "ghg.spatiotemporal_anomaly":      0.40,
            "ghg.trend":                       None,
            "ghg.data_quality_attribution":    0.70,
        }
        out = compute_ghg_audit_followup_priority(payload, mode="trend")
        assert out["ghg.audit_followup_priority"] is None

    def test_returns_none_when_all_inputs_missing(self) -> None:
        out = compute_ghg_audit_followup_priority({}, mode="screening")
        assert out["ghg.audit_followup_priority"] is None


# ---------------------------------------------------------------------------
# 6. run_pillar integration — synthetic, no EE
# ---------------------------------------------------------------------------

# M-TIER-A1 Step E — pillar fakes now provide confidence_terms in
# provenance.extra so the GHG_DQA re-derivation paths (temporal_coverage,
# spatial_resolution_suitability, retrieval_inventory_quality) compute
# real values in integration tests instead of None.
#
# Terms match the D1 _DEFAULT_SIX_STEP template:
#   c_raw = 0.30·0.85 + 0.30·0.60 + 0.25·0.40 + 0.15·1.00 = 0.685
# Multiplier per indicator (from engine/core/provenance._COLUMN_TO_SURFACE_UNCERTAINTY):
#   ghg.ch4   → "weak"  → 0.80 multiplier → c_final = 0.685 × 0.80 = 0.548
#   ghg.viirs → "n_a"   → 1.00 multiplier → c_final = 0.685
#   ghg.co2   → "n_a"   → 1.00 multiplier → c_final = 0.685
# Each fake's `confidence` field is updated to match formula(terms) so
# integration tests can't drift into the "fake says 0.7 but real engine
# produces 0.685" footgun the D1 report described.

_DEFAULT_CONFIDENCE_TERMS_INPUT: dict = {
    "qa":               0.85,
    "n_valid":          0.60,
    "anomaly_strength": 0.40,
    "spatial_context":  1.00,
}


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
        "ghg.ch4.confidence": 0.548,                # M-TIER-A1 Step E: weak × 0.685
        "ghg.ch4.score":      0.60,
        "_provenance.ghg.ch4": {
            "asset_id":   "COPERNICUS/S5P/OFFL/L3_CH4",
            "time_range": _TIME_RANGE,
            "extra": {
                "confidence_terms": {
                    **_DEFAULT_CONFIDENCE_TERMS_INPUT,
                    "column_to_surface_uncertainty": "weak",
                },
            },
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
        "ghg.viirs.confidence": 0.685,              # M-TIER-A1 Step E: n_a × 0.685
        "ghg.viirs.score":      0.50,
        "_provenance.ghg.viirs": {
            "asset_id":   "NASA/VIIRS/002/VNP46A2",
            "time_range": _TIME_RANGE,
            "extra": {
                "confidence_terms": {
                    **_DEFAULT_CONFIDENCE_TERMS_INPUT,
                    "column_to_surface_uncertainty": "n_a",
                },
            },
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

        # Three CO₂-dependent sub-aggregates are None — CO₂ isn't in the
        # selection here so ghg.co2.score never lands in the payload, and
        # the dependent sub-aggregates null-propagate. The CO₂-selected
        # happy path lives in test_co2_selected_activates_all_sub_aggregates.
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

    def test_co2_selected_activates_sub_aggregates_but_not_core_audit(
        self, monkeypatch,
    ) -> None:
        # M5.5b — CO₂ snapshot still runs and the three CO₂-dependent
        # sub-aggregates still activate, but they no longer feed
        # ghg.core_audit_support (which is now CH₄ + combustion + activity).
        # M5.5c — time_range must be inside ODIAC's coverage_window
        # (2020-2023) so the coverage check passes and the snapshot runs;
        # _TIME_RANGE is a 2026 window which would now be skipped.
        in_coverage_range = ("2023-01-01", "2023-04-01")

        def _fake_co2_snapshot(aoi, time_range, mode, ee_client):
            return {
                "ghg.co2.mean":               5.0,
                "ghg.co2.total":              1500.0,
                "ghg.co2.relative_intensity": 5.0,
                "ghg.co2.trend":              None,
                "ghg.co2.trend_p":            None,
                # M-TIER-A1 Step E: n_a × 0.685
                "ghg.co2.confidence":         0.685,
                "ghg.co2.score":              0.7,
                "_provenance.ghg.co2": {
                    "asset_id": "FAKE/ODIAC",
                    "extra": {
                        "confidence_terms": {
                            **_DEFAULT_CONFIDENCE_TERMS_INPUT,
                            "column_to_surface_uncertainty": "n_a",
                        },
                    },
                },
            }

        def fake_indicator_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                return _fake_ch4_snapshot(include_air_keys=True)
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError(f"unexpected indicator {indicator!r}")

        monkeypatch.setattr(
            "engine.ghg.compute_ghg_indicator_snapshot", fake_indicator_snapshot,
        )
        monkeypatch.setattr("engine.ghg.compute_co2_snapshot", _fake_co2_snapshot)

        result_high_co2 = run_pillar(
            aoi=_AOI,
            time_range=in_coverage_range,
            mode="screening",
            selected_indicators={
                "ghg.ch4.score", "ghg.viirs.score", "ghg.co2.score",
            },
            ee_client=None,
        )

        # CO₂ measurement keys present.
        for measurement in (
            "mean", "total", "relative_intensity",
            "trend", "trend_p", "confidence", "score",
        ):
            assert f"ghg.co2.{measurement}" in result_high_co2

        # CO₂-dependent sub-aggregates still compute (display-only).
        assert result_high_co2["ghg.co2_context"] == 0.7
        assert result_high_co2["ghg.fossil_combustion_score"] is not None
        assert result_high_co2["ghg.activity_adjusted_co2"] is not None

        # Core audit support comes from the live trio only — proof: rerun
        # with a wildly different CO₂ score and assert the composite
        # doesn't move.
        def _fake_co2_snapshot_low(aoi, time_range, mode, ee_client):
            payload = _fake_co2_snapshot(aoi, time_range, mode, ee_client)
            payload["ghg.co2.score"] = 0.01
            return payload

        monkeypatch.setattr("engine.ghg.compute_co2_snapshot", _fake_co2_snapshot_low)
        result_low_co2 = run_pillar(
            aoi=_AOI,
            time_range=in_coverage_range,
            mode="screening",
            selected_indicators={
                "ghg.ch4.score", "ghg.viirs.score", "ghg.co2.score",
            },
            ee_client=None,
        )

        assert result_high_co2["ghg.core_audit_support"] is not None
        assert result_low_co2["ghg.core_audit_support"] is not None
        # Identical despite a 0.69 swing in ghg.co2.score — CO₂ is out.
        assert result_high_co2["ghg.core_audit_support"] == pytest.approx(
            result_low_co2["ghg.core_audit_support"],
        )


class TestPresentDayScreeningSkipsOdiac:
    """M5.5c — verify that present-day screening (time range outside
    ODIAC's 2020-2023 coverage) skips CO₂ silently, with no failure
    entry, and the live composite still computes from the surviving
    indicators. Replaces the M5.5b-era variant that asserted
    IndicatorComputeError; the coverage_window check moved the skip
    decision upstream so compute_co2_snapshot is never even called.
    """

    def test_present_day_skips_co2_without_failure(self, monkeypatch) -> None:
        def fake_indicator_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                return _fake_ch4_snapshot(include_air_keys=True)
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError(f"unexpected indicator {indicator!r}")

        # If the spy fires, M5.5c didn't skip ODIAC — that's the bug.
        spy_called: list[tuple] = []

        def fake_co2_snapshot(aoi, time_range, mode, ee_client):
            spy_called.append((time_range,))
            return {}

        monkeypatch.setattr(
            "engine.ghg.compute_ghg_indicator_snapshot", fake_indicator_snapshot,
        )
        monkeypatch.setattr("engine.ghg.compute_co2_snapshot", fake_co2_snapshot)

        result = run_pillar(
            aoi=_AOI,
            time_range=("2026-02-10", "2026-05-11"),  # outside ODIAC coverage
            mode="screening",
            selected_indicators={
                "ghg.ch4.score", "ghg.viirs.score", "ghg.co2.score",
            },
            ee_client=None,
        )

        # Critical: compute_co2_snapshot was NOT called.
        assert spy_called == [], (
            "compute_co2_snapshot should not be called when time_range "
            "is outside ODIAC's coverage_window"
        )

        # CO₂ keys are None-filled (so downstream null-propagation works).
        for measurement in (
            "mean", "total", "relative_intensity",
            "trend", "trend_p", "confidence", "score",
        ):
            assert result[f"ghg.co2.{measurement}"] is None

        # Provenance flags the skip reason.
        prov = result["_provenance.ghg.co2"]
        assert prov["skipped_reason"] == "out_of_coverage"
        assert prov["coverage_window"] == ("2020-01-01", "2023-12-31")
        assert prov["data_type"] == "emissions_inventory_allocation"

        # No CO₂ entry in _failures.
        # `_failures` is a flat list at the GHG-pillar level (the
        # orchestrator namespaces it per-pillar later).
        co2_failures = [
            f for f in result.get("_failures", [])
            if f.get("indicator") == "co2"
        ]
        assert co2_failures == [], (
            f"CO₂ should not appear in _failures when skipped; got {co2_failures}"
        )

        # Live composite still computes from CH₄ + combustion + activity.
        assert result["ghg.core_audit_support"] is not None
        assert result["ghg.audit_followup_priority"] is not None


# ---------------------------------------------------------------------------
# Sanity tests for the smaller helpers
# ---------------------------------------------------------------------------

class TestQualitySubScores:
    """M-TIER-A1: three of four GHG quality sub-scores are now derived
    from per-indicator A1 confidence terms (in provenance.extra). The
    payload these tests synthesise mirrors what `run_pillar` assembles
    after the per-indicator snapshots populate their provenance blocks.
    """

    @staticmethod
    def _payload_with_terms(**per_indicator) -> dict:
        """Build a payload where each GHG indicator's confidence_terms
        live under `_provenance.ghg.<ind>.extra.confidence_terms`."""
        payload: dict = {}
        for ind, terms in per_indicator.items():
            payload[f"_provenance.ghg.{ind}"] = {"extra": {"confidence_terms": terms}}
        return payload

    def test_temporal_coverage_is_mean_of_per_indicator_n_valid(self) -> None:
        # Spec §4.2: ghg.temporal_coverage = mean(N_valid across GHG indicators).
        payload = self._payload_with_terms(
            ch4={"n_valid": 0.8},
            co2={"n_valid": 1.0},
            viirs={"n_valid": 0.6},
        )
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx((0.8 + 1.0 + 0.6) / 3),
        }

    def test_temporal_coverage_skips_missing_indicators(self) -> None:
        # Only ch4 emitted → use what's there; ignore the rest.
        payload = self._payload_with_terms(ch4={"n_valid": 0.9})
        assert compute_temporal_coverage(payload) == {
            "ghg.temporal_coverage": pytest.approx(0.9),
        }

    def test_temporal_coverage_none_when_no_indicators_present(self) -> None:
        # Empty payload → strict-None at the pillar sub-score level.
        assert compute_temporal_coverage({}) == {"ghg.temporal_coverage": None}

    def test_spatial_resolution_suitability_is_mean_of_per_indicator_terms(self) -> None:
        # Spec §4.2: mean of spatial_context terms across GHG indicators.
        # Pre-A1 the helper was CH4-only; now it averages all three.
        payload = self._payload_with_terms(
            ch4={"spatial_context": 0.5},
            co2={"spatial_context": 1.0},
            viirs={"spatial_context": 1.0},
        )
        assert compute_spatial_resolution_suitability(payload) == {
            "ghg.spatial_resolution_suitability": pytest.approx((0.5 + 1.0 + 1.0) / 3),
        }

    def test_spatial_resolution_suitability_aoi_kwarg_accepted_but_unused(self) -> None:
        # Signature parity with pre-A1 call sites; aoi argument is ignored.
        payload = self._payload_with_terms(ch4={"spatial_context": 0.5})
        out = compute_spatial_resolution_suitability(
            payload, {"centre": {"lat": 0, "lon": 0}, "radius_km": 50},
        )
        assert out["ghg.spatial_resolution_suitability"] == pytest.approx(0.5)

    def test_retrieval_inventory_quality_is_mean_of_per_indicator_qa(self) -> None:
        # Spec §4.2: mean of QA terms across GHG indicators.
        # Each per-indicator QA comes from QA_PER_INDICATOR (e.g. CH4 = 0.85,
        # ODIAC = 1.00, VIIRS = 0.85) — those exact values get tested
        # end-to-end in the canary test_pillar_confidence_rollup tests.
        payload = self._payload_with_terms(
            ch4={"qa": 0.85},
            co2={"qa": 1.00},
            viirs={"qa": 0.85},
        )
        assert compute_retrieval_inventory_quality(payload) == {
            "ghg.retrieval_inventory_quality": pytest.approx((0.85 + 1.00 + 0.85) / 3),
        }

    def test_nearby_source_isolation_is_fixed_placeholder(self) -> None:
        # IC_v4 §7.2: independent of per-indicator inputs (placeholder pending).
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


class TestCo2DependentFormulas:
    """M5.5 — these formulas were stubs in M5a but activate as soon as
    ghg.co2_context is non-None (i.e. CO₂ is selected and ODIAC succeeded).
    """

    def test_fossil_combustion_score_activated_when_all_inputs_present(self) -> None:
        # 0.50·co2 + 0.30·combustion + 0.20·activity
        out = compute_fossil_combustion_score({
            "ghg.co2_context":      0.40,
            "ghg.combustion_proxy": 0.50,
            "ghg.activity_score":   0.30,
        })
        expected = 0.50 * 0.40 + 0.30 * 0.50 + 0.20 * 0.30
        assert out["ghg.fossil_combustion_score"] == pytest.approx(expected)

    def test_fossil_combustion_score_none_when_co2_missing(self) -> None:
        # Still null-propagates when CO₂ wasn't selected.
        out = compute_fossil_combustion_score({
            "ghg.co2_context":      None,
            "ghg.combustion_proxy": 0.5,
        })
        assert out["ghg.fossil_combustion_score"] is None

    def test_activity_adjusted_co2_activated_when_both_inputs_present(self) -> None:
        # 0.70·co2 + 0.30·activity
        out = compute_activity_adjusted_co2({
            "ghg.co2_context":    0.40,
            "ghg.activity_score": 0.60,
        })
        expected = 0.70 * 0.40 + 0.30 * 0.60
        assert out["ghg.activity_adjusted_co2"] == pytest.approx(expected)

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
    """M5.5b — ODIAC demoted from the live composite. The three surviving
    live signals (CH₄ + combustion + activity) carry rescaled weights
    (0.46 / 0.44 / 0.10) that sum to 1.00. See engine/constants.py for
    the full rationale.
    """

    def test_full_three_term_weighted_sum_post_m55b(self) -> None:
        # M5.5b — CO₂ no longer in the live composite; the three surviving
        # terms (CH₄ + combustion + activity) carry the full weight.
        payload = {
            "ghg.ch4_context_adjusted": 0.50,
            "ghg.combustion_proxy":     0.40,
            "ghg.activity_score":       0.30,
        }
        selected = set(payload.keys())
        out = compute_core_ghg_audit_support(payload, selected)
        expected = (
            0.46 * 0.50 + 0.44 * 0.40 + 0.10 * 0.30
        )
        assert out["ghg.core_audit_support"] == pytest.approx(expected)

    def test_co2_context_in_payload_does_not_affect_composite(self) -> None:
        # Regression guard: post-M5.5b, including ghg.co2_context in the
        # payload (and in `selected`) must not change the composite — it's
        # simply not in CORE_GHG_AUDIT_SUPPORT_WEIGHTS.
        payload_with = {
            "ghg.co2_context":          0.90,  # would heavily shift if it counted
            "ghg.ch4_context_adjusted": 0.50,
            "ghg.combustion_proxy":     0.40,
            "ghg.activity_score":       0.30,
        }
        payload_without = {
            k: v for k, v in payload_with.items() if k != "ghg.co2_context"
        }
        out_with = compute_core_ghg_audit_support(payload_with, set(payload_with))
        out_without = compute_core_ghg_audit_support(
            payload_without, set(payload_without),
        )
        assert out_with["ghg.core_audit_support"] == pytest.approx(
            out_without["ghg.core_audit_support"],
        )

    def test_renormalises_when_one_live_term_missing(self) -> None:
        # Activity missing (None) → drop the 0.10 weight, renormalise the rest.
        payload = {
            "ghg.ch4_context_adjusted": 0.50,
            "ghg.combustion_proxy":     0.40,
            "ghg.activity_score":       None,
        }
        selected = {
            "ghg.ch4_context_adjusted",
            "ghg.combustion_proxy",
            "ghg.activity_score",
        }
        out = compute_core_ghg_audit_support(payload, selected)
        # Surviving sum: 0.46 + 0.44 = 0.90
        expected = (0.46 * 0.50 + 0.44 * 0.40) / 0.90
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


# ---------------------------------------------------------------------------
# M-V1x-RECONCILE — canonical 15-field provenance shape
# ---------------------------------------------------------------------------

_CANONICAL_PROV_KEYS: tuple[str, ...] = (
    "indicator_id",
    "asset_id", "band", "data_type", "data_source",
    "native_scale_m", "method_note", "time_range",
    "coverage_window", "skipped_reason", "observations",
    "column_to_surface_uncertainty", "temporal_mode",
    "sector_signal_anomaly", "extra",
)


class TestProvenanceShape:
    """Every GHG indicator must emit the canonical 15-field provenance
    block via engine.core.build_provenance — including CO₂ on both the
    happy and out-of-coverage paths.
    """

    def test_co2_provenance_canonical_keys_in_order(
        self, fake_co2_ee,
    ) -> None:
        fake_co2_ee(n_months=3, site_sum=100.0, site_mean=5.0, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        prov = result["_provenance.ghg.co2"]
        assert list(prov.keys()) == list(_CANONICAL_PROV_KEYS)

    def test_co2_provenance_carries_canonical_fields(self, fake_co2_ee) -> None:
        fake_co2_ee(n_months=3, site_sum=100.0, site_mean=5.0, ring_mean=1.0)
        result = compute_co2_snapshot(
            aoi=_AOI_CO2, time_range=_CO2_TIME_RANGE,
            mode="screening", ee_client=None,
        )
        prov = result["_provenance.ghg.co2"]
        assert prov["data_type"] == "emissions_inventory_allocation"
        assert prov["data_source"] == "ODIAC / NIES Japan"
        assert prov["coverage_window"] == ("2020-01-01", "2023-12-31")
        assert prov["observations"]["count"] == 3
        assert prov["observations"]["unit"] == "monthly_grids"
        assert prov["extra"]["c_to_co2_factor"] == pytest.approx(CO2_TO_C_RATIO)
        # M5.5b's role_in_pillar field was dropped in M5.6.
        assert "role_in_pillar" not in prov

    def test_co2_skip_path_provenance_shape(self, monkeypatch) -> None:
        # The out-of-coverage skip path also uses build_provenance.
        def fake_indicator_snapshot(aoi, indicator, time_range, mode, ee_client):
            if indicator == "ch4":
                return _fake_ch4_snapshot(include_air_keys=True)
            if indicator == "viirs":
                return _fake_viirs_snapshot()
            raise AssertionError(f"unexpected indicator {indicator!r}")
        monkeypatch.setattr(
            "engine.ghg.compute_ghg_indicator_snapshot", fake_indicator_snapshot,
        )

        result = run_pillar(
            aoi=_AOI,
            time_range=("2026-02-10", "2026-05-11"),  # outside ODIAC
            mode="screening",
            selected_indicators={
                "ghg.ch4.score", "ghg.viirs.score", "ghg.co2.score",
            },
            ee_client=None,
        )
        prov = result["_provenance.ghg.co2"]
        assert list(prov.keys()) == list(_CANONICAL_PROV_KEYS)
        assert prov["skipped_reason"] == "out_of_coverage"
        assert prov["observations"]["count"] == 0
        assert prov["observations"]["unit"] == "monthly_grids"
        assert prov["data_type"] == "emissions_inventory_allocation"
        assert prov["data_source"] == "ODIAC / NIES Japan"

    def test_ch4_format_result_emits_canonical_provenance(self) -> None:
        # CH₄ goes through compute_ghg_indicator_snapshot → _format_result,
        # not the CO₂ bespoke path. Call _format_result directly with a
        # synthetic raw payload to exercise the build_provenance call site
        # without needing a fake EE session.
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["ch4"]
        result = _format_result(
            indicator="ch4",
            cfg=cfg,
            raw={
                "site": 1900.0, "background": 1880.0, "anomaly": 20.0,
                "z": 2.5, "hf": 0.40, "trend": None, "trend_p": None,
                "confidence": 0.80, "score": 0.60,
            },
            time_range=_TIME_RANGE,
        )
        prov = result["_provenance.ghg.ch4"]
        assert list(prov.keys()) == list(_CANONICAL_PROV_KEYS)
        assert prov["data_type"] == "satellite_observation"
        assert "Sentinel-5P" in prov["data_source"]
        assert prov["band"] == "CH4_column_volume_mixing_ratio_dry_air"
        assert prov["coverage_window"] is None
        assert prov["skipped_reason"] is None

    def test_viirs_format_result_emits_canonical_provenance(self) -> None:
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["viirs"]
        result = _format_result(
            indicator="viirs",
            cfg=cfg,
            raw={
                "site": 25.0, "anomaly": 10.0, "trend": None,
                "confidence": 0.70, "score": 0.50,
            },
            time_range=_TIME_RANGE,
        )
        prov = result["_provenance.ghg.viirs"]
        assert list(prov.keys()) == list(_CANONICAL_PROV_KEYS)
        assert prov["data_type"] == "satellite_observation"
        assert "VIIRS" in prov["data_source"]

    # M-TIER-A3 Step E (§4.4) — three land-mask fields land in extra
    # when six_step's return dict carries them. Pins the GHG side of
    # LM4 ("at least one indicator from each pillar verified to consume
    # the masked ring") via the CH₄ six_step path.

    def test_ch4_provenance_extra_carries_ring_land_fraction(self) -> None:
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["ch4"]
        result = _format_result(
            indicator="ch4", cfg=cfg,
            raw={
                "site": 1900.0, "background": 1880.0, "anomaly": 20.0,
                "z": 2.5, "hf": 0.40, "trend": None, "trend_p": None,
                "confidence": 0.80, "score": 0.60,
                "ring_land_fraction":     0.571,    # Rio real-EE value
                "ring_land_mask_applied": True,
                "ring_land_mask_asset":   "MODIS/006/MOD44W",
            },
            time_range=_TIME_RANGE,
        )
        extra = result["_provenance.ghg.ch4"]["extra"]
        assert extra["ring_land_fraction"] == 0.571

    def test_ch4_provenance_extra_carries_land_mask_applied_true(self) -> None:
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["ch4"]
        result = _format_result(
            indicator="ch4", cfg=cfg,
            raw={
                "site": 1900.0, "background": 1880.0, "anomaly": 20.0,
                "z": 2.5, "hf": 0.40, "trend": None, "trend_p": None,
                "confidence": 0.80, "score": 0.60,
                "ring_land_fraction":     1.0,
                "ring_land_mask_applied": True,
                "ring_land_mask_asset":   "MODIS/006/MOD44W",
            },
            time_range=_TIME_RANGE,
        )
        extra = result["_provenance.ghg.ch4"]["extra"]
        assert extra["land_mask_applied"] is True

    def test_ch4_provenance_extra_carries_land_mask_asset_string(self) -> None:
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["ch4"]
        result = _format_result(
            indicator="ch4", cfg=cfg,
            raw={
                "site": 1900.0, "background": 1880.0, "anomaly": 20.0,
                "z": 2.5, "hf": 0.40, "trend": None, "trend_p": None,
                "confidence": 0.80, "score": 0.60,
                "ring_land_fraction":     1.0,
                "ring_land_mask_applied": True,
                "ring_land_mask_asset":   "MODIS/006/MOD44W",
            },
            time_range=_TIME_RANGE,
        )
        extra = result["_provenance.ghg.ch4"]["extra"]
        assert extra["land_mask_asset"] == "MODIS/006/MOD44W"

    def test_ch4_provenance_extra_omits_fields_when_absent_from_raw(self) -> None:
        # Defensive: legacy six_step payloads pre-Step-E don't carry these
        # keys. The conventional pattern (matching n_valid_dates / granule_count)
        # is to omit them from extra rather than emit None values.
        from engine.ghg import _format_result
        cfg = GHG_INDICATOR_CONFIG["ch4"]
        result = _format_result(
            indicator="ch4", cfg=cfg,
            raw={
                "site": 1900.0, "background": 1880.0, "anomaly": 20.0,
                "z": 2.5, "hf": 0.40, "trend": None, "trend_p": None,
                "confidence": 0.80, "score": 0.60,
                # No ring_land_* keys.
            },
            time_range=_TIME_RANGE,
        )
        extra = result["_provenance.ghg.ch4"]["extra"]
        assert "ring_land_fraction" not in extra
        assert "land_mask_applied" not in extra
        assert "land_mask_asset" not in extra
