"""Tests for ui.components.c4a_indicator_map (M-UI-E.6).

Pure-Python — no Streamlit, no Earth Engine network calls. The renderer
functions touch EE and can't be unit-tested here; instead we cover the
registry shape, the zoom heuristic, and the canonical-ID alignment.
The EE-touching renderers are smoke-tested in the browser.
"""

# M-UI-E.6
from __future__ import annotations

from engine.air import AIR_POLLUTANT_CONFIG
from engine.nature import NATURE_INDICATOR_CONFIG
from ui.components.c4a_indicator_map import (
    _DW_CLASS_NAMES,
    _DW_CLASS_PALETTE,
    _RENDERERS,
    _zoom_for_radius_km,
)


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_registry_ships_three_renderers():
    """v1 commits to three indicator visualisations — see milestone spec."""
    assert len(_RENDERERS) == 3


def test_registry_keys_are_canonical_ids():
    """Each key must follow ``<pillar>.<slug>.<measurement>``."""
    for indicator_id in _RENDERERS:
        parts = indicator_id.split(".")
        assert len(parts) == 3, indicator_id


def test_registry_values_are_callables():
    for indicator_id, renderer in _RENDERERS.items():
        assert callable(renderer), indicator_id


def test_no2_renderer_registered_for_engine_pollutant():
    """The registry's air pollutant must exist in the engine's config."""
    assert "air.no2.score" in _RENDERERS
    assert "no2" in AIR_POLLUTANT_CONFIG


def test_nature_renderer_indicators_exist_in_engine_config():
    """KBA and DW must be live indicators in the Nature engine config."""
    nature_slugs = {"kba", "dw"}
    for indicator_id in _RENDERERS:
        if not indicator_id.startswith("nature."):
            continue
        slug = indicator_id.split(".")[1]
        if slug in nature_slugs:
            assert slug in NATURE_INDICATOR_CONFIG, slug


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
