"""Synthetic-payload tests for engine.nature (Milestone 5b).

Tests bypass Earth Engine: the EE-touching `compute_*` functions are
monkey-patched per test as needed; the sub-aggregate / pillar-aggregate
tests run on pure-Python payloads.

Real-EE smoke tests are deferred to tests/test_nature_integration.py
(mirrors tests/test_air_integration.py — skipped unless RUN_EE_TESTS=1).
"""

from __future__ import annotations

import math

import pytest

from engine.constants import (
    NATURE_SEVERITY_CORE_WEIGHTS,
    BIODIVERSITY_EXPOSURE_WEIGHTS,
    CONVERSION_SATURATION_PCT,
    HABITAT_CONVERSION_WEIGHTS,
    KBA_DISTANCE_DECAY_KM,
    NATURE_FOLLOWUP_WEIGHTS,
    NATURE_MEASUREMENT_QUALITY_WEIGHTS,
    VEGETATION_CONDITION_WEIGHTS,
    WATER_FLOODED_VEG_SATURATION_PCT,
)
from engine.exceptions import IndicatorComputeError, PillarComputeError
from engine.nature import (
    NATURE_INDICATOR_CONFIG,
    NatureIndicatorConfig,
    _augment_habitat_pct_norms,
    _buffer_area_ha,
    _format_kba_result,
    _ndvi_inverted_anomaly,
    _ndvi_low_area_pct,
    _normalise_dw_histogram,
    compute_biodiversity_exposure,
    compute_habitat_conversion,
    compute_habitat_conversion_score,
    compute_nature_followup_priority,
    compute_nature_measurement_quality,
    compute_nature_spatiotemporal_anomaly,
    compute_supplier_spatial_link,
    compute_vegetation_condition,
    run_pillar,
)


_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
_TIME_RANGE = ("2026-01-01", "2026-04-01")


# ---------------------------------------------------------------------------
# 1. NATURE_INDICATOR_CONFIG integrity
# ---------------------------------------------------------------------------

class TestConfigIntegrity:
    def test_seven_indicators_registered(self) -> None:
        assert set(NATURE_INDICATOR_CONFIG.keys()) == {
            "kba", "dw", "habitat", "forest_loss", "ndvi", "water", "recovery",
        }

    @pytest.mark.parametrize("key", list(NATURE_INDICATOR_CONFIG.keys()))
    def test_each_entry_has_required_fields(self, key: str) -> None:
        cfg = NATURE_INDICATOR_CONFIG[key]
        assert isinstance(cfg, NatureIndicatorConfig)
        assert cfg.asset_id
        # KBA is a vector asset → scale_m is 0; all raster indicators are >0.
        if key == "kba":
            assert cfg.scale_m == 0
        else:
            assert cfg.scale_m > 0
        assert cfg.direction in ("higher_is_worse", "lower_is_worse")
        # Every indicator must declare at least one emitted canonical ID.
        assert len(cfg.emitted_keys) > 0

    def test_ndvi_direction_is_lower_is_worse(self) -> None:
        # IC §3.1 — declining NDVI is bad, so direction inverts the score sign.
        assert NATURE_INDICATOR_CONFIG["ndvi"].direction == "lower_is_worse"

    def test_dw_emits_all_nine_class_pct_keys(self) -> None:
        # Schema_v2 §4.2 — every DW class produces both `<slug>_pct` and
        # `<slug>_ha`. We pin nine slugs by checking the dw indicator's
        # emitted_keys for the pct half of each pair.
        emitted = set(NATURE_INDICATOR_CONFIG["dw"].emitted_keys)
        expected_slugs = (
            "trees", "crops", "built", "bare", "grass", "shrub",
            "flooded_veg", "water", "snow",
        )
        for slug in expected_slugs:
            assert f"nature.dw.{slug}_pct" in emitted
            assert f"nature.dw.{slug}_ha" in emitted


# ---------------------------------------------------------------------------
# 2. Weights — sums and shapes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,weights,expected_sum", [
    ("BIODIVERSITY_EXPOSURE_WEIGHTS",     BIODIVERSITY_EXPOSURE_WEIGHTS,     1.0),
    ("HABITAT_CONVERSION_WEIGHTS",        HABITAT_CONVERSION_WEIGHTS,        1.0),
    ("NATURE_MEASUREMENT_QUALITY_WEIGHTS", NATURE_MEASUREMENT_QUALITY_WEIGHTS, 1.0),
    ("NATURE_FOLLOWUP_WEIGHTS",           NATURE_FOLLOWUP_WEIGHTS,           1.0),
    ("NATURE_SEVERITY_CORE_WEIGHTS",      NATURE_SEVERITY_CORE_WEIGHTS,      1.0),
])
def test_weights_sum_to_one(name: str, weights: dict, expected_sum: float) -> None:
    total = sum(weights.values())
    assert math.isclose(total, expected_sum, abs_tol=1e-9), f"{name} sum was {total}"


def test_vegetation_condition_weights() -> None:
    # M-TREND-A1 (TR17): the NDVI slope term (was 0.25) is demoted to
    # drill-down-only and its weight redistributed across the positive
    # terms (0.45/0.65, 0.20/0.65), keeping recovery's −0.10. The positive
    # terms now sum to 1.00, so the signed sum is 0.90 and abs sum 1.10.
    assert "nature.ndvi.negative_trend" not in VEGETATION_CONDITION_WEIGHTS
    assert VEGETATION_CONDITION_WEIGHTS["nature.ndvi.inverted_anomaly"] == pytest.approx(0.45 / 0.65)
    assert VEGETATION_CONDITION_WEIGHTS["nature.low_ndvi.pct_norm"] == pytest.approx(0.20 / 0.65)
    assert VEGETATION_CONDITION_WEIGHTS["nature.recovery.score"] == pytest.approx(-0.10)
    positive = sum(v for v in VEGETATION_CONDITION_WEIGHTS.values() if v > 0)
    assert positive == pytest.approx(1.00)


# ---------------------------------------------------------------------------
# 3. KBA proximity result formatter — synthetic
# ---------------------------------------------------------------------------

class TestKbaResultFormatter:
    def test_zero_distance_full_overlap_maxes_score(self) -> None:
        out = _format_kba_result(dist_km=0.0, overlap_ha=100.0, overlap_pct=100.0)
        # max(100/100, exp(0)) = max(1.0, 1.0) = 1.0
        assert out["nature.kba.proximity_score"] == pytest.approx(1.0)
        assert out["nature.kba.dist_km"] == 0.0
        assert out["nature.kba.overlap_pct"] == 100.0

    def test_distance_only_no_overlap_uses_exp_decay(self) -> None:
        # 7 km outside any KBA → exp(-7/10) ≈ 0.4966
        out = _format_kba_result(dist_km=7.0, overlap_ha=0.0, overlap_pct=0.0)
        expected = math.exp(-7.0 / KBA_DISTANCE_DECAY_KM)
        assert out["nature.kba.proximity_score"] == pytest.approx(expected)

    def test_partial_overlap_takes_max_of_two_terms(self) -> None:
        # 30 % overlap (=0.30) vs distance term exp(-50/10) ≈ 0.0067.
        # max() picks the overlap term.
        out = _format_kba_result(dist_km=50.0, overlap_ha=10.0, overlap_pct=30.0)
        assert out["nature.kba.proximity_score"] == pytest.approx(0.30)

    def test_far_away_no_overlap_decays_toward_zero(self) -> None:
        out = _format_kba_result(dist_km=50.0, overlap_ha=0.0, overlap_pct=0.0)
        # exp(-50/10) ≈ 0.0067 — clearly tiny.
        assert 0.0 < out["nature.kba.proximity_score"] < 0.01


# ---------------------------------------------------------------------------
# 4. DW histogram normaliser
# ---------------------------------------------------------------------------

class TestNormaliseDwHistogram:
    def test_maps_string_keys_to_class_labels(self) -> None:
        # DW class order: water=0, trees=1, grass=2, flooded_veg=3, crops=4,
        # shrub=5, built=6, bare=7, snow=8.
        out = _normalise_dw_histogram({"0": 100, "1": 200, "6": 50})
        assert out["water"] == 100
        assert out["trees"] == 200
        assert out["built"] == 50

    def test_unknown_keys_are_ignored(self) -> None:
        out = _normalise_dw_histogram({"1": 100, "99": 999, "not_a_number": 5})
        assert out == {"trees": 100}

    def test_empty_histogram_returns_empty(self) -> None:
        assert _normalise_dw_histogram({}) == {}


# ---------------------------------------------------------------------------
# 4b. DW class_confidence — wires DW probability bands (v1x followup #12)
# ---------------------------------------------------------------------------
#
# These tests use a chainable MagicMock to stand in for the EE call chain
# inside compute_current_land_cover. The compute now makes two getInfo
# calls in sequence: (1) the label-band frequencyHistogram → dominant
# class, (2) the dominant-class probability band mean → class_confidence.
# Mock pattern mirrors the one in tests/test_nature_defensive.py (kept
# local here to honour the test-file layout the task spec named).

class TestDwClassConfidenceWiring:
    """v1x followup #12 — nature.dw.class_confidence now reads the
    dominant class's DW probability band (mean over the buffer), replacing
    the placeholder that returned the dominant class's pixel fraction."""

    _AOI_LOCAL = {"centre": {"lat": -3.20, "lon": -52.20}, "radius_km": 25}
    _TR_LOCAL = ("2026-02-19", "2026-05-20")

    @staticmethod
    def _stub(monkeypatch, *, getinfo_side_effect=None, getinfo_return=None):
        from unittest.mock import MagicMock

        chain = MagicMock()
        if getinfo_side_effect is not None:
            chain.getInfo.side_effect = getinfo_side_effect
        else:
            chain.getInfo.return_value = getinfo_return
        for attr in (
            "select", "mode", "mean", "sum", "reduceRegion",
            "filterDate", "filterBounds", "multiply", "rename",
            "copyProperties", "gte", "lte", "lt", "eq", "And",
            "updateMask",
        ):
            getattr(chain, attr).return_value = chain
        size_chain = MagicMock()
        size_chain.getInfo.return_value = 5
        chain.size.return_value = size_chain

        fake_ic_cls = MagicMock(return_value=chain)
        fake_image_cls = MagicMock(return_value=chain)
        fake_image_cls.pixelArea.return_value = chain
        monkeypatch.setattr("engine.nature.ee.ImageCollection", fake_ic_cls)
        monkeypatch.setattr("engine.nature.ee.Image", fake_image_cls)
        monkeypatch.setattr("engine.nature.ee.Reducer", MagicMock())
        monkeypatch.setattr(
            "engine.nature.adaptive_scale_m", lambda _g, native, **_kw: native,
        )
        monkeypatch.setattr(
            "engine.nature.site_buffer", lambda *_a, **_kw: object(),
        )
        return chain

    def test_dw_class_confidence_reads_dominant_class_probability_band(
        self, monkeypatch,
    ) -> None:
        chain = self._stub(
            monkeypatch,
            getinfo_side_effect=[
                {"label": {"1": 100}},   # histogram reduction → 100% trees
                {"trees": 0.75},          # dominant-prob reduction
            ],
        )
        from engine.nature import compute_current_land_cover
        result = compute_current_land_cover(
            aoi=self._AOI_LOCAL, time_range=self._TR_LOCAL, ee_client=None,
        )
        assert result["nature.dw.dominant_class"] == "trees"
        assert result["nature.dw.class_confidence"] == pytest.approx(0.75)
        # Two getInfo calls: histogram + dominant-prob. If the old
        # pixel-fraction placeholder were still in place, only the
        # histogram getInfo would fire.
        assert chain.getInfo.call_count == 2

    def test_dw_class_confidence_handles_zero_pixels(self, monkeypatch) -> None:
        # Empty histogram triggers the existing skip path; every emitted
        # canonical ID (class_confidence included) goes to None, and the
        # new dominant-prob getInfo is never issued.
        chain = self._stub(monkeypatch, getinfo_return={})
        from engine.nature import compute_current_land_cover
        result = compute_current_land_cover(
            aoi=self._AOI_LOCAL, time_range=self._TR_LOCAL, ee_client=None,
        )
        assert result["nature.dw.class_confidence"] is None
        assert (
            result["_provenance.nature.dw"]["skipped_reason"] == "no_dw_pixels"
        )
        assert chain.getInfo.call_count == 1

    def test_dw_class_confidence_uses_correct_band_for_dominant_class(
        self, monkeypatch,
    ) -> None:
        # Trees 70%, crops 30% → dominant is "trees". The engine MUST
        # select the trees band for the probability read, not crops.
        from unittest.mock import call
        chain = self._stub(
            monkeypatch,
            getinfo_side_effect=[
                {"label": {"1": 70, "4": 30}},
                {"trees": 0.5},
            ],
        )
        from engine.nature import compute_current_land_cover
        result = compute_current_land_cover(
            aoi=self._AOI_LOCAL, time_range=self._TR_LOCAL, ee_client=None,
        )
        assert result["nature.dw.dominant_class"] == "trees"
        assert result["nature.dw.class_confidence"] == pytest.approx(0.5)
        select_calls = chain.select.call_args_list
        assert call("label") in select_calls
        assert call("trees") in select_calls
        assert call("crops") not in select_calls
        # Mask construction: label_mode.eq(<trees_index>). trees = 1 per
        # DW_INDEX_TO_LABEL. Asserts the mask uses the dominant class's
        # integer index, not e.g. the wrong class or a name-based filter.
        assert call(1) in chain.eq.call_args_list


# ---------------------------------------------------------------------------
# 5. NDVI helper sub-scores
# ---------------------------------------------------------------------------

class TestNdviSubScores:
    def test_inverted_anomaly_returns_score_directly(self) -> None:
        # The six_step's `score` is already direction-inverted when
        # direction='lower_is_worse', so inverted_anomaly is just an alias.
        assert _ndvi_inverted_anomaly({"score": 0.6}) == 0.6

    def test_inverted_anomaly_none_when_score_missing(self) -> None:
        assert _ndvi_inverted_anomaly({}) is None


class TestNdviLowAreaPct:
    """M-NDVI-EMPTY-WINDOW regression — when the requested window has zero
    MODIS NDVI granules over the site, `filtered.mean()` is a band-less image
    and `mean_image.lt(0.3)` would throw `Image.lt: ... Got 0 and 1`. That raw
    ee.EEException is NOT caught by `_run_one_nature_task`, so it failed the
    WHOLE NDVI indicator — even when six_step's SPPY fallback had already
    recovered the site over an earlier window. `with_guaranteed_band` makes the
    `.lt` well-typed server-side; an empty window then reduces to no NDVI value
    → 0 % low-NDVI, with NO extra getInfo round-trip (the size guard is gone)."""

    _AOI_LOCAL = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 50}
    _TR_LOCAL = ("2026-01-01", "2026-04-01")

    @staticmethod
    def _fake_ic(monkeypatch, *, reduction_return=None):
        from unittest.mock import MagicMock

        chain = MagicMock()
        for attr in ("filterDate", "filterBounds", "mean", "lt", "reduceRegion"):
            getattr(chain, attr).return_value = chain
        chain.getInfo.return_value = reduction_return
        monkeypatch.setattr("engine.nature.site_buffer", lambda *_a, **_k: MagicMock())
        monkeypatch.setattr("engine.nature.ee.Reducer", MagicMock())
        # The guard is tested directly in TestWithGuaranteedBand; here we make
        # it an identity passthrough so the reduceRegion result drives output.
        monkeypatch.setattr(
            "engine.nature.with_guaranteed_band", lambda img, _band: img,
        )
        return chain

    def test_empty_window_returns_zero(self, monkeypatch) -> None:
        # Empty window → reduceRegion yields no "NDVI" key → 0 % low-NDVI.
        chain = self._fake_ic(monkeypatch, reduction_return={})
        result = _ndvi_low_area_pct(self._AOI_LOCAL, chain, self._TR_LOCAL, 250.0)
        assert result == 0.0
        # No `.size().getInfo()` round-trip — only the reduceRegion getInfo.
        assert chain.getInfo.call_count == 1

    def test_non_empty_window_computes_pct(self, monkeypatch) -> None:
        chain = self._fake_ic(monkeypatch, reduction_return={"NDVI": 0.42})
        result = _ndvi_low_area_pct(self._AOI_LOCAL, chain, self._TR_LOCAL, 250.0)
        assert result == pytest.approx(42.0)
        chain.mean.assert_called_once()
        chain.lt.assert_called_once_with(0.3)
        assert chain.getInfo.call_count == 1

    # M-TREND-A1 (TR17): the _ndvi_negative_trend tests are removed — the
    # function is deleted (the NDVI slope is demoted to drill-down-only).
    # The slope→severity normalisation now lives in engine/core/trend.py and
    # is covered by tests/test_trend.py::TestTrendSeverity.


# ---------------------------------------------------------------------------
# 6. Habitat pct_norm augmentation
# ---------------------------------------------------------------------------

class TestHabitatPctNorms:
    def test_saturates_at_10pct_buffer_loss(self) -> None:
        # CONVERSION_SATURATION_PCT = 0.10 → 10 ha lost out of 100 ha
        # buffer = 0.10 fraction → score 1.0.
        out = _augment_habitat_pct_norms(
            payload={"nature.habitat.natural_loss_ha": 10.0},
            buffer_ha=100.0,
        )
        assert out["nature.habitat.natural_loss_pct_norm"] == pytest.approx(1.0)

    def test_half_saturation_at_5pct_buffer_loss(self) -> None:
        # 5 ha out of 100 → 0.05 fraction → 0.05 / 0.10 = 0.5
        out = _augment_habitat_pct_norms(
            payload={"nature.habitat.natural_loss_ha": 5.0},
            buffer_ha=100.0,
        )
        assert out["nature.habitat.natural_loss_pct_norm"] == pytest.approx(0.5)

    def test_none_propagates_when_input_missing(self) -> None:
        # Nothing supplied in payload → every pct_norm is None.
        # M-V1x-RECONCILE: forest_loss.pct_norm dropped per audit §9.3 v1.4.
        out = _augment_habitat_pct_norms(payload={}, buffer_ha=100.0)
        for key in (
            "nature.habitat.natural_loss_pct_norm",
            "nature.habitat.nat_to_built_pct_norm",
            "nature.habitat.nat_to_bare_pct_norm",
            "nature.habitat.annualised_rate_score",
        ):
            assert out[key] is None
        assert "nature.forest_loss.pct_norm" not in out

    def test_annualised_rate_score_uses_same_saturation(self) -> None:
        # 2 ha/yr out of 100 ha buffer = 0.02 fraction/yr → 0.02 / 0.10 = 0.20
        out = _augment_habitat_pct_norms(
            payload={"nature.habitat.annualised_rate": 2.0},
            buffer_ha=100.0,
        )
        assert out["nature.habitat.annualised_rate_score"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# 6b. Habitat conversion — baseline window date math
# ---------------------------------------------------------------------------

def _date_to_ordinal(yyyy_mm_dd: str) -> int:
    """Convert an ISO date to a day-since-epoch ordinal for span comparison."""
    from datetime import date as _date
    y, m, d = (int(x) for x in yyyy_mm_dd.split("-"))
    return _date(y, m, d).toordinal()


class TestHabitatConversionBaselineWindow:
    """The baseline window must mirror the current window's day-of-year span
    exactly, just shifted by HABITAT_BASELINE_YEARS years. Older versions
    of the code derived baseline_start from `baseline_year - 1`, which made
    the baseline window 15 months wide instead of matching the current
    window's 90-day span. This test pins the correct date arithmetic.
    """

    def _capture_windows(
        self, monkeypatch, time_range: tuple[str, str],
    ) -> list[tuple[str, str]]:
        captured: list[tuple[str, str]] = []

        def fake_dw_mode_histogram(asset_id, geom, time_range, scale_m):
            captured.append(time_range)
            # Return a non-empty histogram so the calling function doesn't
            # raise on missing pixels. Pixel index "1" = trees.
            return {"trees": 100}

        # Also stub ee.* surfaces site_buffer / FeatureCollection touch.
        # M-ADAPTIVE-SCALE: also stub the adaptive-scale helper since it
        # would otherwise call geom.area(maxError=100).getInfo() on the
        # opaque ``object()`` returned by the site_buffer stub.
        monkeypatch.setattr(
            "engine.nature._dw_mode_histogram", fake_dw_mode_histogram,
        )
        monkeypatch.setattr(
            "engine.nature.site_buffer", lambda *_a, **_kw: object(),
        )
        monkeypatch.setattr(
            "engine.nature.adaptive_scale_m", lambda _geom, native, **_kw: native,
        )

        compute_habitat_conversion(
            aoi=_AOI, time_range=time_range, ee_client=None,
        )
        return captured

    def test_baseline_window_matches_current_window_span(self, monkeypatch) -> None:
        # 90-day current window → baseline should also be 90 days, just
        # shifted by HABITAT_BASELINE_YEARS (= 5) years.
        time_range = ("2026-01-01", "2026-04-01")
        windows = self._capture_windows(monkeypatch, time_range)

        # First call is current, second is baseline.
        assert windows[0] == time_range
        baseline = windows[1]

        # Same MM-DD day-of-year endpoints, 5 years earlier.
        assert baseline == ("2021-01-01", "2021-04-01")

        # Span equality — the regression guard. Old code produced a
        # 15-month-wide baseline, which would fail this assertion.
        current_span = _date_to_ordinal(time_range[1]) - _date_to_ordinal(time_range[0])
        baseline_span = _date_to_ordinal(baseline[1]) - _date_to_ordinal(baseline[0])
        assert current_span == baseline_span

    def test_cross_year_window_preserves_year_offset(self, monkeypatch) -> None:
        # Nov→Feb current window crosses a year boundary. The baseline must
        # also cross a year boundary five years earlier — not collapse to a
        # same-year window which would invert start/end.
        time_range = ("2026-11-01", "2027-02-01")
        windows = self._capture_windows(monkeypatch, time_range)

        assert windows[0] == time_range
        baseline = windows[1]
        assert baseline == ("2021-11-01", "2022-02-01")

        current_span = _date_to_ordinal(time_range[1]) - _date_to_ordinal(time_range[0])
        baseline_span = _date_to_ordinal(baseline[1]) - _date_to_ordinal(baseline[0])
        assert current_span == baseline_span


# ---------------------------------------------------------------------------
# 7. Sub-aggregates — strict null propagation + happy paths
# ---------------------------------------------------------------------------

class TestBiodiversityExposure:
    def test_weighted_sum_when_all_three_terms_present(self) -> None:
        payload = {
            "nature.kba.proximity_score":           0.8,
            "nature.sensitive_land_cover_presence": 0.6,
            "nature.water_or_flooded_veg_exposure": 0.4,
        }
        out = compute_biodiversity_exposure(payload)
        # BIODIVERSITY_EXPOSURE_WEIGHTS rescales the IC raw weights by 1/0.90
        # because Buffer_Sensitivity_v1 is 0 in v1.
        w = BIODIVERSITY_EXPOSURE_WEIGHTS
        expected = (
            w["nature.kba.proximity_score"]           * 0.8
            + w["nature.sensitive_land_cover_presence"] * 0.6
            + w["nature.water_or_flooded_veg_exposure"] * 0.4
        )
        assert out["nature.biodiversity_exposure"] == pytest.approx(expected)

    def test_returns_none_when_any_dependency_missing(self) -> None:
        # KBA present, but sensitive_land_cover and water exposure missing.
        payload = {"nature.kba.proximity_score": 0.8}
        out = compute_biodiversity_exposure(payload)
        assert out["nature.biodiversity_exposure"] is None


class TestHabitatConversionScore:
    def test_weighted_sum_when_all_four_terms_present(self) -> None:
        # M-V1x-RECONCILE: forest_loss demoted from composite per audit §9.3 v1.4.
        payload = {
            "nature.habitat.natural_loss_pct_norm": 0.5,
            "nature.habitat.nat_to_built_pct_norm": 0.4,
            "nature.habitat.nat_to_bare_pct_norm":  0.3,
            "nature.habitat.annualised_rate_score": 0.1,
        }
        out = compute_habitat_conversion_score(payload)
        w = HABITAT_CONVERSION_WEIGHTS
        expected = (
            w["nature.habitat.natural_loss_pct_norm"] * 0.5
            + w["nature.habitat.nat_to_built_pct_norm"] * 0.4
            + w["nature.habitat.nat_to_bare_pct_norm"] * 0.3
            + w["nature.habitat.annualised_rate_score"] * 0.1
        )
        assert out["nature.habitat.conversion_score"] == pytest.approx(expected)

    def test_returns_none_when_any_dependency_missing(self) -> None:
        # Missing the last term.
        payload = {
            "nature.habitat.natural_loss_pct_norm": 0.5,
            "nature.habitat.nat_to_built_pct_norm": 0.4,
            "nature.habitat.nat_to_bare_pct_norm":  0.3,
        }
        out = compute_habitat_conversion_score(payload)
        assert out["nature.habitat.conversion_score"] is None


class TestVegetationCondition:
    # M-TREND-A1 (TR17): the NDVI slope term is demoted to drill-down-only.
    # Vegetation_Condition is now 0.6923·inv_anom + 0.3077·low_pct − 0.10·recovery.
    _W = VEGETATION_CONDITION_WEIGHTS

    def test_formula_with_synthetic_components(self) -> None:
        payload = {
            "nature.ndvi.inverted_anomaly": 0.6,
            "nature.low_ndvi.pct_norm":     0.4,
            "nature.recovery.score":        0.2,
        }
        out = compute_vegetation_condition(payload)
        expected = (
            self._W["nature.ndvi.inverted_anomaly"] * 0.6
            + self._W["nature.low_ndvi.pct_norm"]     * 0.4
            + self._W["nature.recovery.score"]        * 0.2
        )
        assert out["nature.vegetation_condition"] == pytest.approx(expected)
        assert 0.0 <= out["nature.vegetation_condition"] <= 1.0

    def test_clamps_above_one_to_one(self) -> None:
        # Positive terms at max sum to 1.0 exactly; recovery 0 → result 1.0.
        payload = {
            "nature.ndvi.inverted_anomaly": 1.0,
            "nature.low_ndvi.pct_norm":     1.0,
            "nature.recovery.score":        0.0,
        }
        out = compute_vegetation_condition(payload)
        assert out["nature.vegetation_condition"] == pytest.approx(1.0)

    def test_clamps_below_zero_to_zero(self) -> None:
        # Large recovery, no concern → −0.10 → clamped to 0.
        payload = {
            "nature.ndvi.inverted_anomaly": 0.0,
            "nature.low_ndvi.pct_norm":     0.0,
            "nature.recovery.score":        1.0,
        }
        out = compute_vegetation_condition(payload)
        assert out["nature.vegetation_condition"] == 0.0

    def test_returns_none_when_any_dependency_missing(self) -> None:
        # Missing recovery → strict-None.
        payload = {
            "nature.ndvi.inverted_anomaly": 0.6,
            "nature.low_ndvi.pct_norm":     0.4,
        }
        out = compute_vegetation_condition(payload)
        assert out["nature.vegetation_condition"] is None


# ---------------------------------------------------------------------------
# 8. Pillar aggregates — renormalisation
# ---------------------------------------------------------------------------

class TestNatureMeasurementQuality:
    def test_renormalises_over_present_terms(self) -> None:
        # M-ATTRIB-A1 (AT13/AT14): three of the four measurement-quality
        # terms have values; renormalise over the survivors.
        payload = {
            "nature.valid_pixel_coverage":      0.8,
            "nature.cloud_observation_quality": 0.9,
            "nature.seasonal_comparability":    1.0,
        }
        out = compute_nature_measurement_quality(payload)
        w = NATURE_MEASUREMENT_QUALITY_WEIGHTS
        denom = (
            w["nature.valid_pixel_coverage"]
            + w["nature.cloud_observation_quality"]
            + w["nature.seasonal_comparability"]
        )
        expected = (
            w["nature.valid_pixel_coverage"]      * 0.8
            + w["nature.cloud_observation_quality"] * 0.9
            + w["nature.seasonal_comparability"]    * 1.0
        ) / denom
        assert out["nature.measurement_quality"] == pytest.approx(expected)

    def test_returns_none_when_all_terms_missing(self) -> None:
        out = compute_nature_measurement_quality({})
        assert out["nature.measurement_quality"] is None

    def test_attribution_signals_not_in_aggregate(self) -> None:
        # M-ATTRIB-A1 (AT14) regression: supplier_spatial_link and
        # external_driver_screening must not influence the aggregate.
        assert "nature.supplier_spatial_link" not in NATURE_MEASUREMENT_QUALITY_WEIGHTS
        assert "nature.external_driver_screening" not in NATURE_MEASUREMENT_QUALITY_WEIGHTS
        assert len(NATURE_MEASUREMENT_QUALITY_WEIGHTS) == 4


class TestNatureFollowupPriority:
    def test_two_level_weighted_sum(self) -> None:
        """M-WEIGHTS-HARMONISE-A1: 0.80·severity_core + 0.20·quality, where
        the core is the three exposure/change/condition strands."""
        payload = {
            "nature.biodiversity_exposure":      0.7,
            "nature.habitat.conversion_score":   0.6,
            "nature.vegetation_condition":       0.5,
            "nature.measurement_quality":        0.8,  # M-ATTRIB-A1 (AT13)
        }
        out = compute_nature_followup_priority(payload, mode="screening")
        sc = NATURE_SEVERITY_CORE_WEIGHTS
        core = (
            sc["biodiversity_exposure"] * 0.7
            + sc["habitat_conversion"]   * 0.6
            + sc["vegetation_condition"] * 0.5
        )
        expected = (
            NATURE_FOLLOWUP_WEIGHTS["severity_core"] * core
            + NATURE_FOLLOWUP_WEIGHTS["quality"] * 0.8
        )
        assert out["nature.followup_priority"] == pytest.approx(expected)

    def test_returns_none_when_quality_attribution_missing(self) -> None:
        """M-FOLLOWUP-FALLBACK: any missing sub-aggregate → priority is
        None. The prior renormalise-over-survivors behaviour produced
        Rio's misleading 0.858 priority from quality_attribution alone
        when biodiversity/habitat/vegetation were all None."""
        payload = {
            "nature.biodiversity_exposure":      0.7,
            "nature.habitat.conversion_score":   0.6,
            "nature.vegetation_condition":       0.5,
        }
        out = compute_nature_followup_priority(payload, mode="screening")
        assert out["nature.followup_priority"] is None

    def test_returns_none_when_all_terms_missing(self) -> None:
        out = compute_nature_followup_priority({}, mode="screening")
        assert out["nature.followup_priority"] is None


class TestNatureSpatiotemporalAnomaly:
    def test_clamps_z_into_zero_one(self) -> None:
        # NORMALISATION_K = 3 → z=6 → 2.0 → clamp(2.0, 0, 1) = 1.0
        out = compute_nature_spatiotemporal_anomaly({"nature.ndvi.z": 6.0})
        assert out["nature.spatiotemporal_anomaly_score"] == 1.0

    def test_none_when_ndvi_z_missing(self) -> None:
        out = compute_nature_spatiotemporal_anomaly({})
        assert out["nature.spatiotemporal_anomaly_score"] is None


# ---------------------------------------------------------------------------
# 9. run_pillar integration — synthetic, no EE
# ---------------------------------------------------------------------------

def _patch_all_indicators(monkeypatch, *, fail: set[str] | None = None) -> None:
    """Replace every EE-touching compute_* with a deterministic synthetic.

    `fail` is the set of indicator keys (e.g. {"kba"}) that should raise
    IndicatorComputeError instead of returning a payload. Defaults to no
    failures.

    M-TIER-A1 Step E — every fake now emits a `_provenance.nature.<ind>`
    block with `extra.confidence_terms` matching the canonical shape
    real engine output uses. Without this, `nature.valid_pixel_coverage`
    silently re-derived to None in integration tests, hiding the M-TIER-A1
    pillar QA rollup paths from CI coverage.

    Terms use the D1 _DEFAULT_SIX_STEP template (qa=0.85, n_valid=0.60,
    anomaly_strength=0.40, spatial_context=1.00). Every Nature indicator's
    column_to_surface_uncertainty defaults to "n_a" (no column retrievals
    in this pillar), so the multiplier is 1.00 and c_final = 0.685.
    """
    fail = fail or set()

    def _maybe_fail(name: str) -> None:
        if name in fail:
            raise IndicatorComputeError(
                indicator_id=f"nature.{name}",
                reason=f"synthetic failure for {name}",
            )

    # Shared confidence_terms payload — single source of truth across the
    # eight Nature fakes. The values mirror tests/test_air.py::_DEFAULT_SIX_STEP.
    confidence_terms = {
        "qa":                            0.85,
        "n_valid":                       0.60,
        "anomaly_strength":              0.40,
        "spatial_context":               1.00,
        "column_to_surface_uncertainty": "n_a",
    }
    expected_confidence = 0.685   # = 0.30·0.85 + 0.30·0.60 + 0.25·0.40 + 0.15·1.00

    def fake_kba(aoi, time_range=None, ee_client=None):
        # M5.6 — compute_kba_proximity takes time_range for provenance
        # consistency (KBA is reference data, but the user's request window
        # is documented in provenance).
        # M-TIER-A1 Step E — also pass aoi so _format_kba_result emits a
        # real `nature.kba.confidence` value and threads confidence_terms
        # into provenance.extra. The helper already does this work.
        _maybe_fail("kba")
        return _format_kba_result(
            dist_km=2.0, overlap_ha=5.0, overlap_pct=10.0,
            time_range=time_range,
            aoi=aoi,
        )

    def fake_dw(aoi, time_range, ee_client):
        _maybe_fail("dw")
        return {
            "nature.dw.trees_pct":               40.0,
            "nature.dw.trees_ha":                100.0,
            "nature.dw.crops_pct":               20.0,
            "nature.dw.crops_ha":                50.0,
            "nature.dw.built_pct":               10.0,
            "nature.dw.built_ha":                25.0,
            "nature.dw.bare_pct":                5.0,
            "nature.dw.bare_ha":                 12.5,
            "nature.dw.grass_pct":               15.0,
            "nature.dw.grass_ha":                37.5,
            "nature.dw.shrub_pct":               5.0,
            "nature.dw.shrub_ha":                12.5,
            "nature.dw.flooded_veg_pct":         2.0,
            "nature.dw.flooded_veg_ha":          5.0,
            "nature.dw.water_pct":               3.0,
            "nature.dw.water_ha":                7.5,
            "nature.dw.snow_pct":                0.0,
            "nature.dw.snow_ha":                 0.0,
            "nature.dw.dominant_class":          "trees",
            "nature.dw.class_confidence":        0.85,
            "nature.dw.confidence":              expected_confidence,
            "nature.sensitive_land_cover_presence": 0.62,
            "nature.water_or_flooded_veg_exposure": 0.25,
            "_provenance.nature.dw": {
                "asset_id":       "GOOGLE/DYNAMICWORLD/V1",
                "band":           "label",
                "data_type":      "ml_classified_satellite",
                "data_source":    "Google / WRI (Dynamic World V1)",
                "native_scale_m": 10.0,
                "time_range":     time_range,
                "extra":          {"confidence_terms": confidence_terms},
            },
        }

    def fake_habitat(aoi, time_range, ee_client):
        _maybe_fail("habitat")
        return {
            "nature.habitat.natural_loss_ha":    25.0,
            "nature.habitat.natural_loss_pct":   1.0,
            "nature.habitat.nat_to_built_ha":    10.0,
            "nature.habitat.nat_to_bare_ha":     5.0,
            "nature.habitat.nat_to_crop_ha":     10.0,
            "nature.habitat.built_expansion_ha": 10.0,
            "nature.habitat.bare_expansion_ha":  5.0,
            "nature.habitat.annualised_rate":    5.0,
            "nature.habitat.confidence":         expected_confidence,
            "_provenance.nature.habitat": {
                "asset_id":       "GOOGLE/DYNAMICWORLD/V1",
                "band":           "label",
                "data_type":      "ml_classified_satellite",
                "data_source":    "Google / WRI (Dynamic World V1)",
                "native_scale_m": 10.0,
                "time_range":     time_range,
                "extra":          {"confidence_terms": confidence_terms},
            },
        }

    def fake_forest_loss(aoi, time_range, ee_client):
        _maybe_fail("forest_loss")
        return {
            "nature.forest_loss.ha":         15.0,
            "nature.forest_loss.pct":        0.6,
            "nature.forest_loss.confidence": expected_confidence,
            "_provenance.nature.forest_loss": {
                "asset_id":       "UMD/hansen/global_forest_change_2023_v1_11",
                "band":           "lossyear",
                "data_type":      "reference_dataset",
                "data_source":    "UMD / Hansen Global Forest Change",
                "native_scale_m": 30.92,
                "time_range":     time_range,
                "observations":   {"count": 1, "unit": "annual_rasters"},
                "extra":          {"confidence_terms": confidence_terms},
            },
        }

    def fake_ndvi(aoi, time_range, mode, ee_client, fallback=None):
        _maybe_fail("ndvi")
        return {
            "nature.ndvi.mean":             0.55,
            "nature.ndvi.anomaly":          -0.05,
            "nature.ndvi.z":                -1.5,
            "nature.ndvi.slope":            -0.005,
            "nature.ndvi.slope_p":          0.10,
            "nature.ndvi.score":            0.35,
            "nature.ndvi.confidence":       expected_confidence,
            "nature.ndvi.inverted_anomaly": 0.35,
            "nature.low_ndvi.ha":           5.0,
            "nature.low_ndvi.pct":          2.0,
            "nature.low_ndvi.pct_norm":     0.02,
            "_provenance.nature.ndvi": {
                "asset_id":       "MODIS/061/MOD13Q1",
                "band":           "NDVI",
                "data_type":      "satellite_observation",
                "data_source":    "NASA MODIS (MOD13Q1)",
                "native_scale_m": 250.0,
                "time_range":     time_range,
                "observations":   {"count": 1, "unit": "16day_composites"},
                "extra":          {"confidence_terms": confidence_terms},
            },
        }

    def fake_water(aoi, time_range, ee_client):
        _maybe_fail("water")
        return {
            "nature.water.area_now_ha":       7.5,
            "nature.flooded_veg.area_now_ha": 5.0,
            "nature.water.confidence":        expected_confidence,
            "_provenance.nature.water": {
                "asset_id":       "GOOGLE/DYNAMICWORLD/V1",
                "band":           "label",
                "data_type":      "ml_classified_satellite",
                "data_source":    "Google / WRI (Dynamic World V1)",
                "native_scale_m": 10.0,
                "time_range":     time_range,
                "extra":          {"confidence_terms": confidence_terms},
            },
        }

    def fake_recovery(aoi, time_range, ee_client):
        _maybe_fail("recovery")
        return {
            "nature.recovery.ndvi_improvement_pct": None,
            "nature.recovery.natural_cover_gain_ha": None,
            "nature.recovery.bare_reduction_ha":     None,
            "nature.recovery.score":                 0.0,
            "nature.recovery.confidence":            expected_confidence,
            "_provenance.nature.recovery": {
                "asset_id":       "MODIS/061/MOD13Q1",
                "band":           "NDVI",
                "data_type":      "satellite_observation",
                "data_source":    "NASA MODIS (MOD13Q1)",
                "native_scale_m": 250.0,
                "time_range":     time_range,
                "extra":          {
                    "placeholder":      True,
                    "confidence_terms": confidence_terms,
                },
            },
        }

    def fake_regional_loss_evidence(aoi, time_range, ee_client):
        # M-ATTRIB-A1 (AT5): reference data — emits ratio + window, not the
        # old external_driver_screening sub-score. Stubbed so tests skip EE.
        return {
            "nature.regional_loss_evidence.ratio":  1.4,
            "nature.regional_loss_evidence.window": "2019–2023",
            "_provenance.nature.regional_loss_evidence": {
                "asset_id":       "UMD/hansen/global_forest_change_2023_v1_11",
                "band":           "lossyear",
                "data_type":      "reference_dataset",
                "data_source":    "UMD / Hansen Global Forest Change",
                "native_scale_m": 30.92,
                "time_range":     ("2019-01-01", "2023-12-31"),
                "observations":   {"count": 5, "unit": "annual_rasters"},
                "extra":          {"ratio": 1.4, "regional_loss_evidence_raw": 0.0},
            },
        }

    monkeypatch.setattr("engine.nature.compute_kba_proximity", fake_kba)
    monkeypatch.setattr("engine.nature.compute_current_land_cover", fake_dw)
    monkeypatch.setattr("engine.nature.compute_habitat_conversion", fake_habitat)
    monkeypatch.setattr("engine.nature.compute_forest_loss", fake_forest_loss)
    monkeypatch.setattr("engine.nature.compute_ndvi_condition", fake_ndvi)
    monkeypatch.setattr("engine.nature.compute_water_exposure", fake_water)
    monkeypatch.setattr("engine.nature.compute_recovery_signal", fake_recovery)
    monkeypatch.setattr(
        "engine.nature.compute_regional_loss_evidence",
        fake_regional_loss_evidence,
    )

    def fake_supplier_spatial_link(aoi, time_range, ee_client, **_kw):
        # M-ATTRIB-A1 (AT7): habitat-conversion attributability surface.
        # Stubbed so run_pillar tests skip the centroid EE pipeline.
        return {
            "nature.supplier_spatial_link.centroid_offset_km": 0.8,
            "nature.supplier_spatial_link.centroid_lat":       0.001,
            "nature.supplier_spatial_link.centroid_lon":       0.002,
            "nature.supplier_spatial_link.n_change_pixels":    37,
            "nature.habitat.attributability_state":            "high",
            "_provenance.nature.supplier_spatial_link": {
                "indicator_id": "nature.supplier_spatial_link",
                "extra": {"spatial_link_terms": {"attributability_state": "high"}},
            },
        }

    monkeypatch.setattr(
        "engine.nature.compute_supplier_spatial_link",
        fake_supplier_spatial_link,
    )


_ALL_NATURE_SELECTED = {
    "nature.kba.proximity_score",
    "nature.dw.trees_pct",
    "nature.habitat.natural_loss_ha",
    "nature.forest_loss.ha",
    "nature.ndvi.score",
    "nature.water.area_now_ha",
    "nature.recovery.score",
}


class TestRunPillarHappyPath:
    def test_full_payload_with_all_seven_indicators(self, monkeypatch) -> None:
        _patch_all_indicators(monkeypatch)
        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators=_ALL_NATURE_SELECTED,
            ee_client=None,
        )

        # Single-value indicator outputs present.
        assert result["nature.kba.proximity_score"] is not None
        assert result["nature.dw.trees_pct"] == 40.0
        assert result["nature.habitat.natural_loss_ha"] == 25.0
        assert result["nature.forest_loss.ha"] == 15.0
        assert result["nature.ndvi.score"] == 0.35
        assert result["nature.water.area_now_ha"] == 7.5
        assert result["nature.recovery.score"] == 0.0

        # All three sub-aggregates produced non-None values.
        assert result["nature.biodiversity_exposure"] is not None
        assert result["nature.habitat.conversion_score"] is not None
        assert result["nature.vegetation_condition"] is not None

        # Pillar aggregates.
        assert result["nature.measurement_quality"] is not None  # M-ATTRIB-A1
        assert result["nature.followup_priority"] is not None
        assert result["nature.spatiotemporal_anomaly_score"] is not None

        # No failures.
        assert "_failures" not in result

    def test_accumulated_payload_kwarg_accepted_but_unused(self, monkeypatch) -> None:
        # Cross-pillar signature parity: Nature accepts but ignores the kwarg.
        _patch_all_indicators(monkeypatch)
        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators=_ALL_NATURE_SELECTED,
            ee_client=None,
            accumulated_payload={"air.industrial_combustion_proxy": 0.5},
        )
        # Air key did NOT leak into Nature's output.
        assert "air.industrial_combustion_proxy" not in result


class TestRunPillarPartialFailure:
    def test_single_indicator_failure_degrades_gracefully(self, monkeypatch) -> None:
        # Force NDVI to fail. Other six indicators compute normally.
        _patch_all_indicators(monkeypatch, fail={"ndvi"})

        result = run_pillar(
            aoi=_AOI,
            time_range=_TIME_RANGE,
            mode="screening",
            selected_indicators=_ALL_NATURE_SELECTED,
            ee_client=None,
        )

        # Every NDVI emitted key is None.
        for key in NATURE_INDICATOR_CONFIG["ndvi"].emitted_keys:
            assert result[key] is None, f"{key} should be None after NDVI failure"

        # Other indicators still computed.
        assert result["nature.kba.proximity_score"] is not None
        assert result["nature.dw.trees_pct"] == 40.0

        # Vegetation_Condition aggregate is None (its NDVI deps are missing).
        assert result["nature.vegetation_condition"] is None
        # But biodiversity_exposure still computable from KBA + DW + water exposure.
        assert result["nature.biodiversity_exposure"] is not None

        # M-FOLLOWUP-FALLBACK: Nature priority is now strict-None — any
        # missing sub-aggregate (vegetation_condition here) takes the
        # whole priority to None. Avoids the misleading "high priority"
        # headlines that the old renormalise-over-survivors path
        # produced when only one of four sub-aggregates was populated.
        assert result["nature.followup_priority"] is None

        # _failures lists NDVI.
        assert "_failures" in result
        assert len(result["_failures"]) == 1
        assert result["_failures"][0]["indicator"] == "ndvi"
        assert "synthetic failure" in result["_failures"][0]["reason"]


class TestRunPillarAllFail:
    def test_pillar_compute_error_when_every_indicator_fails(
        self, monkeypatch,
    ) -> None:
        # Every selected indicator raises IndicatorComputeError.
        _patch_all_indicators(
            monkeypatch,
            fail={"kba", "dw", "habitat", "forest_loss", "ndvi", "water", "recovery"},
        )

        with pytest.raises(PillarComputeError) as excinfo:
            run_pillar(
                aoi=_AOI,
                time_range=_TIME_RANGE,
                mode="screening",
                selected_indicators=_ALL_NATURE_SELECTED,
                ee_client=None,
            )

        err = excinfo.value
        assert err.pillar == "nature"
        # Spot-check: KBA's four keys all in the affected list.
        for key in NATURE_INDICATOR_CONFIG["kba"].emitted_keys:
            assert key in err.indicator_ids


# ---------------------------------------------------------------------------
# 10. Buffer area helper — quick sanity
# ---------------------------------------------------------------------------

class TestBufferAreaHa:
    def test_circle_area_matches_pi_r_squared(self) -> None:
        # 50 km radius → π × 50² km² = π × 2500 km² = π × 250 000 ha.
        expected = math.pi * (50.0 ** 2) * 100  # km² → ha
        assert _buffer_area_ha(50.0) == pytest.approx(expected, rel=1e-9)

    def test_unit_consistency_against_water_saturation(self) -> None:
        # Sanity that the saturation constants are interpretable.
        # 20 % water cover at 50 km buffer = 20 % of buffer area.
        buffer_ha = _buffer_area_ha(50.0)
        twenty_pct_ha = buffer_ha * 0.20
        # 20 % of buffer divided by saturation constant (20.0 in pct units)
        # multiplied by 100 to convert fraction to pct = 100 → score 1.0 (saturated).
        score = min((twenty_pct_ha / buffer_ha * 100.0) / WATER_FLOODED_VEG_SATURATION_PCT, 1.0)
        assert score == pytest.approx(1.0)


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
    """Every Nature indicator must emit the canonical 15-field provenance
    block. Tests exercise the construction paths that don't require EE.
    """

    def test_kba_provenance_canonical_keys_and_reference_data_type(self) -> None:
        # _format_kba_result is the canonical path for KBA provenance —
        # tested directly so we don't need a fake EE.
        out = _format_kba_result(
            dist_km=2.0, overlap_ha=5.0, overlap_pct=10.0,
            time_range=_TIME_RANGE,
        )
        prov = out["_provenance.nature.kba"]
        assert list(prov.keys()) == list(_CANONICAL_PROV_KEYS)
        assert prov["data_type"] == "reference_dataset"
        assert "BirdLife" in prov["data_source"]
        assert prov["observations"]["unit"] == "static_snapshot"
        assert prov["observations"]["count"] == 1
        assert prov["extra"]["distance_decay_km"] == 10.0

    def test_kba_provenance_uses_static_sentinel_when_no_time_range(self) -> None:
        # When compute_kba_proximity is called without a time_range
        # (tests calling it directly), the provenance carries a sentinel.
        out = _format_kba_result(
            dist_km=2.0, overlap_ha=5.0, overlap_pct=10.0,
            time_range=None,
        )
        assert out["_provenance.nature.kba"]["time_range"] == ("static", "static")

    @pytest.mark.parametrize("indicator,expected_type,expected_source_substring", [
        ("kba",         "reference_dataset",       "BirdLife"),
        ("dw",          "ml_classified_satellite", "Dynamic World"),
        ("habitat",     "ml_classified_satellite", "Dynamic World"),
        # M-V1x-RECONCILE per audit §9.3 v1.4: Hansen reclassified from
        # ml_classified_satellite to reference_dataset (standing-exposure
        # demotion). Tests must reflect engine-actual state.
        ("forest_loss", "reference_dataset",       "Hansen"),
        ("ndvi",        "satellite_observation",   "MODIS"),
        ("water",       "ml_classified_satellite", "Dynamic World"),
        ("recovery",    "satellite_observation",   "MODIS"),
    ])
    def test_config_advertises_correct_provenance_metadata(
        self, indicator: str, expected_type: str, expected_source_substring: str,
    ) -> None:
        # Pin per-indicator metadata at the config layer — these strings
        # land in every provenance block constructed via build_provenance.
        cfg = NATURE_INDICATOR_CONFIG[indicator]
        assert cfg.data_type == expected_type
        assert expected_source_substring in cfg.data_source


# ---------------------------------------------------------------------------
# compute_supplier_spatial_link — centroid offset (M-ATTRIB-A1 §7.2)
# ---------------------------------------------------------------------------

class _LinkGetInfo:
    def __init__(self, value):
        self._value = value
    def getInfo(self):
        return self._value


class _FakeTransition:
    """Stands in for the transition mask image after .rename().selfMask().

    reduceRegion(count) → {"change": n_change}.
    """
    def __init__(self, n_change: int):
        self._n_change = n_change
    def rename(self, *_):
        return self
    def selfMask(self):                                 # noqa: N802
        return self
    def And(self, _other):                              # noqa: N802
        return self
    def reduceRegion(self, **_kw):                      # noqa: N802
        return _LinkGetInfo({"change": self._n_change})


class _FakeMaskImage:
    """Result of label.mode().remap(...) — supports .And(...)."""
    def __init__(self, transition: _FakeTransition):
        self._transition = transition
    def And(self, _other):                              # noqa: N802
        return self._transition


class _FakeModeImage:
    def __init__(self, transition: _FakeTransition):
        self._transition = transition
    def remap(self, *_a, **_kw):
        return _FakeMaskImage(self._transition)


class _FakeLabelImage:
    def __init__(self, transition: _FakeTransition):
        self._transition = transition
    def mode(self):
        return _FakeModeImage(self._transition)


class _FakeCollection:
    def __init__(self, size: int, transition: _FakeTransition):
        self._size = size
        self._transition = transition
    def filterDate(self, *_a, **_kw):                   # noqa: N802
        return self
    def filterBounds(self, *_a, **_kw):                 # noqa: N802
        return self
    def size(self):
        return _LinkGetInfo(self._size)
    def select(self, *_a, **_kw):
        return _FakeLabelImage(self._transition)


class _FakeLonLatMasked:
    def __init__(self, lon, lat):
        self._lon, self._lat = lon, lat
    def reduceRegion(self, **_kw):                      # noqa: N802
        return _LinkGetInfo({"longitude": self._lon, "latitude": self._lat})


class _FakeLonLat:
    def __init__(self, lon, lat):
        self._lon, self._lat = lon, lat
    def updateMask(self, _t):                           # noqa: N802
        return _FakeLonLatMasked(self._lon, self._lat)


def _install_spatial_link_fakes(
    monkeypatch, *, current_size, baseline_size, n_change, centroid_lon, centroid_lat,
):
    transition = _FakeTransition(n_change)
    sizes = iter([current_size, baseline_size])

    def _fake_collection(_asset_id):
        return _FakeCollection(next(sizes), transition)

    monkeypatch.setattr("engine.nature.site_buffer", lambda *_a, **_kw: object())
    monkeypatch.setattr(
        "engine.nature.adaptive_scale_m", lambda _g, native: native,
    )
    monkeypatch.setattr("engine.nature.ee.ImageCollection", _fake_collection)

    class _FakeImage:
        @staticmethod
        def pixelLonLat():                              # noqa: N802
            return _FakeLonLat(centroid_lon, centroid_lat)

    monkeypatch.setattr("engine.nature.ee.Image", _FakeImage)

    class _FakeReducer:
        @staticmethod
        def count():
            return object()
        @staticmethod
        def mean():
            return object()

    monkeypatch.setattr("engine.nature.ee.Reducer", _FakeReducer)


_LINK_AOI = {"centre": {"lat": 0.0, "lon": 0.0}, "radius_km": 5.0}
_LINK_TR = ("2024-01-01", "2024-03-31")


class TestSupplierSpatialLink:
    def test_emits_all_six_fields(self, monkeypatch) -> None:
        _install_spatial_link_fakes(
            monkeypatch, current_size=10, baseline_size=10,
            n_change=50, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        for key in (
            "nature.supplier_spatial_link.centroid_offset_km",
            "nature.supplier_spatial_link.centroid_lat",
            "nature.supplier_spatial_link.centroid_lon",
            "nature.supplier_spatial_link.n_change_pixels",
            "nature.habitat.attributability_state",
            "_provenance.nature.supplier_spatial_link",
        ):
            assert key in out

    def test_high_attributability_for_near_centroid(self, monkeypatch) -> None:
        # Centroid at (0, 0.005) ≈ 0.56 km from supplier (0,0) → high.
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=5,
            n_change=50, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        offset = out["nature.supplier_spatial_link.centroid_offset_km"]
        assert offset == pytest.approx(0.556, abs=0.05)
        assert out["nature.habitat.attributability_state"] == "high"
        assert out["nature.supplier_spatial_link.centroid_lat"] == 0.0
        assert out["nature.supplier_spatial_link.centroid_lon"] == 0.005
        assert out["nature.supplier_spatial_link.n_change_pixels"] == 50

    def test_low_attributability_for_distant_centroid(self, monkeypatch) -> None:
        # Centroid at (0, 0.05) ≈ 5.56 km from supplier → > 3 km → low.
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=5,
            n_change=50, centroid_lon=0.05, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        assert out["nature.supplier_spatial_link.centroid_offset_km"] > 3.0
        assert out["nature.habitat.attributability_state"] == "low"

    def test_sparse_when_too_few_change_pixels(self, monkeypatch) -> None:
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=5,
            n_change=3, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        assert out["nature.habitat.attributability_state"] == "sparse"
        assert out["nature.supplier_spatial_link.centroid_offset_km"] is None
        assert out["nature.supplier_spatial_link.centroid_lat"] is None
        assert out["nature.supplier_spatial_link.centroid_lon"] is None
        assert out["nature.supplier_spatial_link.n_change_pixels"] == 3

    def test_sparse_when_count_reducer_returns_zero(self, monkeypatch) -> None:
        # Both windows have DW scenes (so the size guard passes), but no
        # natural→non-natural transition pixels exist → the count reducer
        # returns 0 → sparse. This pins the in-window "no change" path,
        # distinct from the empty-window size guard (which is covered by
        # test_sparse_when_dw_window_empty below).
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=5,
            n_change=0, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        assert out["nature.habitat.attributability_state"] == "sparse"
        assert out["nature.supplier_spatial_link.centroid_offset_km"] is None
        assert out["nature.supplier_spatial_link.n_change_pixels"] == 0

    def test_sparse_when_dw_window_empty(self, monkeypatch) -> None:
        # Empty baseline window (e.g. baseline predates DW's 2015-06 coverage)
        # → `.select("label").mode()` is band-less → `.remap()` would throw a
        # raw ee.EEException that the worker does NOT catch, crashing the whole
        # screening. The restored size guard must short-circuit to sparse.
        # (Regression for "Image.remap: Image has no bands".)
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=0,
            n_change=99, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        assert out["nature.habitat.attributability_state"] == "sparse"
        assert out["nature.supplier_spatial_link.centroid_offset_km"] is None
        assert out["nature.supplier_spatial_link.n_change_pixels"] == 0
        terms = out["_provenance.nature.supplier_spatial_link"]["extra"]["spatial_link_terms"]
        assert terms["skipped_reason"] == "no_dw_pixels"

    def test_provenance_carries_spatial_link_terms(self, monkeypatch) -> None:
        _install_spatial_link_fakes(
            monkeypatch, current_size=5, baseline_size=5,
            n_change=42, centroid_lon=0.005, centroid_lat=0.0,
        )
        out = compute_supplier_spatial_link(_LINK_AOI, _LINK_TR, ee_client=None)
        prov = out["_provenance.nature.supplier_spatial_link"]
        terms = prov["extra"]["spatial_link_terms"]
        assert terms["attributability_state"] == "high"
        assert terms["n_change_pixels"] == 42
        assert terms["centroid_lat"] == 0.0
        assert terms["centroid_lon"] == 0.005
        assert terms["centroid_offset_km"] == pytest.approx(0.556, abs=0.05)
        # AT17: additive provenance under provenance.extra.
        assert prov["indicator_id"] == "nature.supplier_spatial_link"
        assert prov["observations"] is None
