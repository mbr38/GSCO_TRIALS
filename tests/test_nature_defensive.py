"""Defensive empty-result tests for engine.nature reducers (M-NATURE-DEFENSIVE).

Each Nature reducer was hardened against the case where Earth Engine's
reduceRegion returns a dict missing the expected band key — the bug that
surfaced at Altamira Frontier Farm as
``Dictionary.get: Dictionary does not contain key: 'label'`` when
Dynamic World filtered to zero usable scenes.

These tests stub the EE call chain so the final ``.getInfo()`` returns
an empty dict, then assert the reducer emits the canonical
skipped-result shape (None-valued canonical IDs + provenance block with
``skipped_reason``).
"""

# M-NATURE-DEFENSIVE
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.nature import (
    NATURE_INDICATOR_CONFIG,
    compute_current_land_cover,
    compute_forest_loss,
    compute_habitat_conversion,
    compute_water_exposure,
)
from ui.components.c4b_kpi_grid import _SKIPPED_REASON_TRANSLATIONS
from ui.components.c9_partial_banner import _SKIPPED_REASON_PROSE


_AOI = {"centre": {"lat": -3.20, "lon": -52.20}, "radius_km": 25}
_TIME_RANGE = ("2026-02-19", "2026-05-20")


# ---------------------------------------------------------------------------
# Test helpers — chainable EE mock
# ---------------------------------------------------------------------------

def _chainable(get_info_returns) -> MagicMock:
    """Build a MagicMock where every chained method returns the same mock,
    *except* ``.getInfo()`` which returns ``get_info_returns``.

    Lets a test write
    ``ic.select("label").mode().reduceRegion(...).getInfo()`` against the
    mock without configuring every intermediate step.
    """
    chain = MagicMock()
    chain.getInfo.return_value = get_info_returns
    # Every other attribute returns the same chain — so .select, .mode,
    # .reduceRegion, .filterDate, .filterBounds, .multiply etc. all chain.
    chain.select.return_value = chain
    chain.mode.return_value = chain
    chain.mean.return_value = chain
    chain.sum.return_value = chain
    chain.reduceRegion.return_value = chain
    chain.filterDate.return_value = chain
    chain.filterBounds.return_value = chain
    chain.multiply.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.lt.return_value = chain
    chain.And.return_value = chain
    chain.copyProperties.return_value = chain
    chain.rename.return_value = chain
    # .size() is its own chain because callers wrap it in int(...).getInfo().
    size_chain = MagicMock()
    size_chain.getInfo.return_value = 5  # non-zero so size check passes.
    chain.size.return_value = size_chain
    return chain


@pytest.fixture
def stub_ee(monkeypatch):
    """Stub the EE surfaces touched by Nature reducers.

    ``adaptive_scale_m`` is also stubbed so the test doesn't need a real
    ``ee.Geometry`` with an .area() chain. ``site_buffer`` returns a
    sentinel object that the reducers pass through to EE calls — they're
    stubbed so the sentinel is fine.
    """
    chain = _chainable({})  # Default: empty reduction.

    # Build a MagicMock for ee.Image that's *both* callable (so
    # ``ee.Image(asset_id)`` returns the chain) and has an attribute
    # ``.pixelArea`` (so ``ee.Image.pixelArea()`` returns the chain too —
    # used by compute_forest_loss). Same trick for ee.ImageCollection.
    fake_image_cls = MagicMock()
    fake_image_cls.return_value = chain
    fake_image_cls.pixelArea.return_value = chain

    fake_ic_cls = MagicMock()
    fake_ic_cls.return_value = chain

    monkeypatch.setattr("engine.nature.ee.ImageCollection", fake_ic_cls)
    monkeypatch.setattr("engine.nature.ee.Image", fake_image_cls)
    monkeypatch.setattr("engine.nature.ee.Reducer", MagicMock())
    monkeypatch.setattr(
        "engine.nature.adaptive_scale_m", lambda _geom, native, **_kw: native,
    )
    monkeypatch.setattr(
        "engine.nature.site_buffer", lambda *_a, **_kw: object(),
    )
    return chain


# ---------------------------------------------------------------------------
# Canonical-shape helper assertions
# ---------------------------------------------------------------------------

def _assert_skipped_shape(
    result: dict,
    ind_key: str,
    expected_reason: str,
) -> None:
    """Every emitted canonical ID is None and provenance carries the
    expected skipped_reason. Shared invariant across the four reducers.
    """
    cfg = NATURE_INDICATOR_CONFIG[ind_key]
    for emitted in cfg.emitted_keys:
        assert result[emitted] is None, f"{emitted} should be None on skip"
    prov = result[f"_provenance.nature.{ind_key}"]
    assert prov["skipped_reason"] == expected_reason
    assert prov["observations"] == {"count": 0, "unit": _OBSERVATION_UNITS[ind_key]}


_OBSERVATION_UNITS = {
    "dw":          "daily_images",
    "habitat":     "daily_images",
    "forest_loss": "annual_rasters",
    "water":       "daily_images",
}


# ---------------------------------------------------------------------------
# compute_current_land_cover — DW landcover
# ---------------------------------------------------------------------------

class TestComputeCurrentLandCoverDefensive:
    def test_empty_reduction_returns_skipped_block(self, stub_ee):
        """Reduction returns {} → no 'label' key → silent skip with
        skipped_reason='no_dw_pixels'."""
        stub_ee.getInfo.return_value = {}
        result = compute_current_land_cover(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "dw", "no_dw_pixels")

    def test_label_key_missing_returns_skipped_block(self, stub_ee):
        """Reduction returned a dict but without the 'label' key."""
        stub_ee.getInfo.return_value = {"other_band": {"0": 100}}
        result = compute_current_land_cover(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "dw", "no_dw_pixels")

    def test_label_present_but_empty_returns_skipped_block(self, stub_ee):
        """Reduction returned 'label' key with empty histogram dict."""
        stub_ee.getInfo.return_value = {"label": {}}
        result = compute_current_land_cover(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "dw", "no_dw_pixels")

    def test_happy_path_unchanged(self, stub_ee):
        """Regression — a non-empty histogram still produces the existing
        per-class values. Sanity check that the new guard didn't break
        the success branch."""
        stub_ee.getInfo.return_value = {"label": {"1": 50, "6": 50}}
        result = compute_current_land_cover(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        # 'trees' (class 1) and 'built' (class 6) split 50/50.
        assert result["nature.dw.trees_pct"] == pytest.approx(50.0)
        assert result["nature.dw.built_pct"] == pytest.approx(50.0)
        # No skipped marker on the happy path.
        assert result["_provenance.nature.dw"]["skipped_reason"] is None


# ---------------------------------------------------------------------------
# compute_habitat_conversion — two DW composites
# ---------------------------------------------------------------------------

class TestComputeHabitatConversionDefensive:
    def test_both_composites_empty_returns_skipped(self, stub_ee):
        stub_ee.getInfo.return_value = {}
        result = compute_habitat_conversion(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "habitat", "no_dw_pixels")

    def test_one_empty_one_full_still_skipped(self, monkeypatch):
        """When the current composite parses but baseline doesn't, the
        diff is undefined — must skip. Patch ``_dw_mode_histogram``
        directly to return one-empty / one-full.
        """
        calls: list = []

        def fake_hist(asset_id, geom, time_range, scale_m):
            calls.append(time_range)
            return {"trees": 100} if len(calls) == 1 else {}

        monkeypatch.setattr("engine.nature._dw_mode_histogram", fake_hist)
        monkeypatch.setattr(
            "engine.nature.site_buffer", lambda *_a, **_kw: object(),
        )
        monkeypatch.setattr(
            "engine.nature.adaptive_scale_m", lambda _geom, native, **_kw: native,
        )

        result = compute_habitat_conversion(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "habitat", "no_dw_pixels")


# ---------------------------------------------------------------------------
# compute_forest_loss — Hansen reduce
# ---------------------------------------------------------------------------

class TestComputeForestLossDefensive:
    def test_empty_reduction_returns_skipped(self, stub_ee):
        stub_ee.getInfo.return_value = {}
        result = compute_forest_loss(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "forest_loss", "no_hansen_pixels")

    def test_lossyear_value_zero_is_happy_path(self, stub_ee):
        """A real zero (no loss in the AOI) is NOT a skip — it's a valid
        result. Pin the distinction between None (missing) and 0 (no loss).
        """
        stub_ee.getInfo.return_value = {"lossyear": 0}
        result = compute_forest_loss(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        assert result["nature.forest_loss.ha"] == 0.0
        assert result["_provenance.nature.forest_loss"]["skipped_reason"] is None

    def test_window_is_fixed_hansen_lookback_not_user_window(self, stub_ee):
        """M-V1x-STANDING-WINDOW — Hansen reads its own fixed lookback window
        (most recent HANSEN_LOOKBACK_YEARS), ignoring the user's analysis
        window. `_TIME_RANGE` is a present-day 2026 window; the provenance must
        still report the 2019-2023 Hansen window (not the user's 2026 one,
        which would mask to a year with no Hansen data and report 0)."""
        stub_ee.getInfo.return_value = {"lossyear": 12345.0}
        result = compute_forest_loss(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        prov = result["_provenance.nature.forest_loss"]
        assert tuple(prov["time_range"]) == ("2019-01-01", "2023-12-31")


# ---------------------------------------------------------------------------
# compute_water_exposure — DW water + flooded_veg
# ---------------------------------------------------------------------------

class TestComputeWaterExposureDefensive:
    def test_empty_reduction_returns_skipped(self, stub_ee):
        stub_ee.getInfo.return_value = {}
        result = compute_water_exposure(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        _assert_skipped_shape(result, "water", "no_dw_pixels")

    def test_label_key_present_with_only_non_water_classes(self, stub_ee):
        """Happy path — DW pixels exist but no water/flooded_veg. Result
        should have zero hectares, NOT a skip (the data is there, it's
        just zero).
        """
        stub_ee.getInfo.return_value = {"label": {"1": 1000}}  # trees only
        result = compute_water_exposure(
            aoi=_AOI, time_range=_TIME_RANGE, ee_client=None,
        )
        assert result["nature.water.area_now_ha"] == 0.0
        assert result["nature.flooded_veg.area_now_ha"] == 0.0
        assert result["_provenance.nature.water"]["skipped_reason"] is None


# ---------------------------------------------------------------------------
# UI prose dicts — every new code is registered in both lookup tables
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code",
    ["no_dw_pixels", "no_hansen_pixels", "no_modis_pixels", "no_cams_pixels"],
)
def test_skipped_reason_prose_registered_in_c9(code: str):
    """C9 partial banner can translate every new code to user-readable
    text. Missing entries fall back to the raw code, which is what the
    banner showed before this milestone — pin the explicit translation.
    """
    assert code in _SKIPPED_REASON_PROSE
    assert len(_SKIPPED_REASON_PROSE[code]) > 0


@pytest.mark.parametrize(
    "code",
    ["no_dw_pixels", "no_hansen_pixels", "no_modis_pixels", "no_cams_pixels"],
)
def test_skipped_reason_prose_registered_in_c4b(code: str):
    """Same lookup table mirrored in C4b's failed-tile reason expander."""
    assert code in _SKIPPED_REASON_TRANSLATIONS
    assert len(_SKIPPED_REASON_TRANSLATIONS[code]) > 0


def test_c9_and_c4b_prose_match_for_all_new_codes():
    """C9 and C4b dicts are intentional mirrors. A drift between them
    means a user sees one wording on the banner and a different wording
    in the tile expander.
    """
    for code in ("no_dw_pixels", "no_hansen_pixels", "no_modis_pixels", "no_cams_pixels"):
        assert _SKIPPED_REASON_PROSE[code] == _SKIPPED_REASON_TRANSLATIONS[code]
