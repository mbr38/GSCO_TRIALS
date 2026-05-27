"""Tests for ui.components.c4a_indicator_map (M-UI-E.6 → M-UI-A5).

Pure-Python — no Streamlit, no Earth Engine network calls. The layer
builders touch EE when *called* and can't be unit-tested here; instead we
cover the registry shape, the canonical-ID alignment, the parametric Air
factory's closure semantics, the zoom heuristic, and the palette grammars.
The EE-touching render path is smoke-tested in the browser.
"""

# M-UI-A5
from __future__ import annotations

from engine.air import AIR_POLLUTANT_CONFIG
from engine.ghg import GHG_INDICATOR_CONFIG
from engine.nature import NATURE_INDICATOR_CONFIG
from ui.components.c4a_indicator_map import (
    _AIR_DISPLAY,
    _DW_CLASS_NAMES,
    _DW_CLASS_PALETTE,
    _NDVI_LABELS,
    _NDVI_PALETTE,
    _RENDERERS,
    _VIIRS_LABELS,
    _VIIRS_PALETTE,
    _air_source_label,
    _make_air_pollutant_layer,
    _zoom_for_radius_km,
)


# ---------------------------------------------------------------------------
# Registry shape — M-UI-A5 extends the registry to all 14 scored tiles
# ---------------------------------------------------------------------------

# The 14 scored C4b tiles get map treatment (MV9); Hansen + ODIAC reference
# datasets are deliberately excluded (MV10).
_EXPECTED_KEYS = {
    "air.no2.score", "air.so2.score", "air.co.score", "air.hcho.score",
    "air.o3.score", "air.aai.score", "air.pm25.score", "air.pm10.score",
    "air.aod.score", "ghg.ch4.score", "ghg.viirs.score",
    "nature.kba.proximity_score", "nature.dw.trees_pct", "nature.ndvi.score",
}


def test_registry_ships_fourteen_renderers():
    """M-UI-A5 covers all 14 scored C4b tiles (MV9)."""
    assert len(_RENDERERS) == 14
    assert set(_RENDERERS) == _EXPECTED_KEYS


def test_reference_datasets_excluded_from_registry():
    """Hansen + ODIAC stay off the map (MV10) — no registry entry."""
    for key in _RENDERERS:
        assert "hansen" not in key, key
        assert "odiac" not in key and "co2" not in key, key


def test_registry_keys_are_canonical_ids():
    """Each key must follow ``<pillar>.<slug>.<measurement>``."""
    for indicator_id in _RENDERERS:
        parts = indicator_id.split(".")
        assert len(parts) == 3, indicator_id


def test_registry_values_are_callables():
    for indicator_id, renderer in _RENDERERS.items():
        assert callable(renderer), indicator_id


def test_air_renderers_exist_for_every_engine_pollutant():
    """Every Air pollutant in the engine config has a map renderer (MV9)."""
    for key in AIR_POLLUTANT_CONFIG:
        assert f"air.{key}.score" in _RENDERERS, key


def test_ghg_renderers_registered_for_engine_indicators():
    """CH₄ and VIIRS must exist in the GHG engine config (recon A.3)."""
    assert "ghg.ch4.score" in _RENDERERS and "ch4" in GHG_INDICATOR_CONFIG
    assert "ghg.viirs.score" in _RENDERERS and "viirs" in GHG_INDICATOR_CONFIG


def test_nature_renderer_indicators_exist_in_engine_config():
    """KBA, DW and NDVI must be live indicators in the Nature engine config."""
    nature_slugs = {"kba", "dw", "ndvi"}
    for indicator_id in _RENDERERS:
        if not indicator_id.startswith("nature."):
            continue
        slug = indicator_id.split(".")[1]
        if slug in nature_slugs:
            assert slug in NATURE_INDICATOR_CONFIG, slug


# ---------------------------------------------------------------------------
# Parametric Air factory (MV9 / §5.1) — closure semantics, no EE
# ---------------------------------------------------------------------------

def test_air_factory_returns_distinct_callables_per_key():
    """The factory closes over the pollutant key — different keys give
    independent renderers (§8.1)."""
    no2 = _make_air_pollutant_layer("no2")
    so2 = _make_air_pollutant_layer("so2")
    assert callable(no2) and callable(so2)
    assert no2 is not so2


def test_air_factory_registry_entries_use_factory():
    """Every Air registry entry is a factory-produced callable bound to its key."""
    for key in AIR_POLLUTANT_CONFIG:
        assert callable(_RENDERERS[f"air.{key}.score"])


def test_air_source_label_matches_family():
    """Prose source label branches on the three Air asset families (recon A.2)."""
    for key in ("no2", "so2", "co", "hcho", "o3", "aai"):
        assert _air_source_label(key) == "Sentinel-5P TROPOMI"
    assert _air_source_label("pm25") == "ECMWF CAMS"
    assert _air_source_label("pm10") == "ECMWF CAMS"
    assert _air_source_label("aod") == "MODIS MAIAC"


def test_air_display_covers_every_pollutant():
    """Every pollutant has a display name + measurement phrase for the prose."""
    assert set(_AIR_DISPLAY) == set(AIR_POLLUTANT_CONFIG)


# ---------------------------------------------------------------------------
# Zoom heuristic
# ---------------------------------------------------------------------------

def test_zoom_for_zero_km_falls_back_to_default():
    """Defensive: zero or negative km doesn't crash; uses a sane default."""
    assert _zoom_for_radius_km(0) == 12
    assert _zoom_for_radius_km(-5) == 12


def test_zoom_for_tiny_radius_clamps_to_max():
    """Very small km → log heuristic exceeds the Leaflet practical max of 18."""
    assert _zoom_for_radius_km(0.001) == 18


def test_zoom_for_huge_radius_clamps_to_min():
    """Very large km → log heuristic drops below Leaflet's practical min of 5."""
    assert _zoom_for_radius_km(50_000) == 5


def test_zoom_for_ten_km_lands_in_city_range():
    """A 5 km buffer at 2× margin (10 km display) → city-scale zoom (10-12)."""
    z = _zoom_for_radius_km(10)
    assert 10 <= z <= 12


def test_zoom_is_monotonically_non_increasing_in_km():
    """Larger display extent → smaller (or equal) zoom number."""
    last = _zoom_for_radius_km(0.5)
    for km in (1, 5, 10, 50, 100, 500, 1000):
        z = _zoom_for_radius_km(km)
        assert z <= last, (km, z, last)
        last = z


# ---------------------------------------------------------------------------
# Dynamic World palette / class names
# ---------------------------------------------------------------------------

def test_dw_palette_has_nine_classes():
    """DW V1 has 9 official classes — palette and name lists must match."""
    assert len(_DW_CLASS_NAMES) == 9
    assert len(_DW_CLASS_PALETTE) == 9


def test_dw_palette_entries_are_hex_strings():
    for colour in _DW_CLASS_PALETTE:
        assert isinstance(colour, str)
        assert colour.startswith("#")
        assert len(colour) == 7


# ---------------------------------------------------------------------------
# VIIRS + NDVI palette grammars (§5.3 / §5.4) — legend alignment
# ---------------------------------------------------------------------------

def test_viirs_palette_and_labels_align():
    """``_render_inline_legend`` asserts palette/labels lengths match."""
    assert len(_VIIRS_PALETTE) == len(_VIIRS_LABELS)
    for colour in _VIIRS_PALETTE:
        assert colour.startswith("#") and len(colour) == 7


def test_ndvi_palette_and_labels_align():
    assert len(_NDVI_PALETTE) == len(_NDVI_LABELS)
    for colour in _NDVI_PALETTE:
        assert colour.startswith("#") and len(colour) == 7
