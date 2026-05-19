"""Tests for ui.components.c4b_kpi_grid (M-UI-E.3).

Pure-Python — no Streamlit. Tests the helpers individually because the
``render_*`` functions write to Streamlit and can't be asserted on
directly. Plus an end-to-end pass on a synthetic São Paulo payload to
exercise the success / per-indicator-failure / silent-skip paths
together.
"""

# M-UI-E.3
from __future__ import annotations

import pytest

from ui.components.c4b_kpi_grid import (
    _FLAT_ANOMALY_EPS,
    _TILES,
    _anomaly_direction,
    _arrow_glyph,
    _is_failed,
    _resolve_failure_reason,
)


# ---------------------------------------------------------------------------
# _is_failed
# ---------------------------------------------------------------------------

def test_is_failed_true_when_score_is_none():
    tile = next(t for t in _TILES if t.indicator == "pm10")
    assert _is_failed(tile, {"air.pm10.score": None}) is True


def test_is_failed_false_when_score_is_a_number():
    tile = next(t for t in _TILES if t.indicator == "no2")
    assert _is_failed(tile, {"air.no2.score": 0.42}) is False


def test_is_failed_true_on_empty_payload():
    """Missing key behaves like None — the tile is failed."""
    tile = next(t for t in _TILES if t.indicator == "co")
    assert _is_failed(tile, {}) is True


# ---------------------------------------------------------------------------
# _anomaly_direction / _arrow_glyph
# ---------------------------------------------------------------------------

def test_anomaly_direction_positive():
    assert _anomaly_direction(42.0) == "up"


def test_anomaly_direction_negative():
    assert _anomaly_direction(-3.1) == "down"


def test_anomaly_direction_zero_is_flat():
    assert _anomaly_direction(0.0) == "flat"


def test_anomaly_direction_none():
    assert _anomaly_direction(None) == "none"


def test_anomaly_direction_below_epsilon_is_flat():
    """Values within ±EPS of zero collapse to flat."""
    assert _anomaly_direction(_FLAT_ANOMALY_EPS / 2) == "flat"
    assert _anomaly_direction(-_FLAT_ANOMALY_EPS / 2) == "flat"


def test_arrow_glyph_covers_every_direction():
    assert _arrow_glyph("up")   == "↑"
    assert _arrow_glyph("down") == "↓"
    assert _arrow_glyph("flat") == "→"
    assert _arrow_glyph("none") == ""


# ---------------------------------------------------------------------------
# _resolve_failure_reason
# ---------------------------------------------------------------------------

def test_resolve_reason_from_failures_list():
    """When _failures has a matching indicator_id, its reason wins."""
    tile = next(t for t in _TILES if t.indicator == "pm10")
    payload = {
        "air.pm10.score": None,
        "_failures": {
            "air": [
                {
                    "indicator_id": "air.pm10",
                    "reason": "site buffer (5 km) smaller than pm10 native pixel (44.5 km)",
                },
            ],
        },
    }
    assert "buffer" in _resolve_failure_reason(tile, payload)


def test_resolve_reason_from_provenance_skipped():
    """coverage_window silent-skip path — reason from provenance."""
    tile = next(t for t in _TILES if t.indicator == "co2")
    payload = {
        "ghg.co2.score": None,
        "_provenance.ghg.co2": {"skipped_reason": "out_of_coverage"},
    }
    reason = _resolve_failure_reason(tile, payload)
    assert "coverage window" in reason.lower()


def test_resolve_reason_unknown_skipped_code_passes_through():
    """An unrecognised skipped_reason returns the raw code (no crash)."""
    tile = next(t for t in _TILES if t.indicator == "ch4")
    payload = {
        "ghg.ch4.score": None,
        "_provenance.ghg.ch4": {"skipped_reason": "some_future_code"},
    }
    assert _resolve_failure_reason(tile, payload) == "some_future_code"


def test_resolve_reason_generic_fallback():
    """Nothing in _failures or provenance → generic fallback."""
    tile = next(t for t in _TILES if t.indicator == "aod")
    reason = _resolve_failure_reason(tile, {"air.aod.score": None})
    assert reason == "Indicator did not return a value."


def test_resolve_reason_failures_entry_without_reason_falls_through():
    """An entry in _failures with no `reason` key falls through to the
    generic fallback rather than returning None."""
    tile = next(t for t in _TILES if t.indicator == "so2")
    payload = {
        "air.so2.score": None,
        "_failures": {"air": [{"indicator_id": "air.so2"}]},
    }
    assert _resolve_failure_reason(tile, payload) == (
        "Indicator did not return a value."
    )


# ---------------------------------------------------------------------------
# Tile-spec integrity
# ---------------------------------------------------------------------------

def test_tile_count_is_twelve():
    assert len(_TILES) == 12


def test_tile_pillar_split_is_nine_air_three_ghg():
    air_count = sum(1 for t in _TILES if t.pillar == "air")
    ghg_count = sum(1 for t in _TILES if t.pillar == "ghg")
    assert air_count == 9
    assert ghg_count == 3


def test_every_tile_score_key_ends_in_score():
    for tile in _TILES:
        assert tile.score_key.endswith(".score"), tile.indicator


def test_every_tile_confidence_key_ends_in_confidence():
    for tile in _TILES:
        assert tile.confidence_key.endswith(".confidence"), tile.indicator


def test_co2_has_no_anomaly_key():
    """ODIAC CO₂ is inventory-allocated — there's no anomaly concept."""
    co2 = next(t for t in _TILES if t.indicator == "co2")
    assert co2.anomaly_key is None


def test_every_non_co2_tile_has_an_anomaly_key():
    for tile in _TILES:
        if tile.indicator == "co2":
            continue
        assert tile.anomaly_key is not None, tile.indicator


# ---------------------------------------------------------------------------
# End-to-end: São Paulo-shaped payload
# ---------------------------------------------------------------------------

def _sao_paulo_payload() -> dict:
    """Synthetic payload mimicking the keys C4b reads on a São Paulo run.

    PM10/PM25 fail (5 km buffer < 44.5 km native pixel). CO₂ silently
    skipped (May 2026 outside ODIAC's 2020-2023 coverage). The other
    10 tiles return a real numeric value.
    """
    payload: dict = {
        # 7 successful air tiles.
        "air.no2.score":  0.55, "air.no2.site":  41.0, "air.no2.anomaly":  +12.0, "air.no2.confidence":  0.20,
        "air.so2.score":  0.10, "air.so2.site":  20.0, "air.so2.anomaly":  -71.0, "air.so2.confidence":  0.20,
        "air.co.score":   0.30, "air.co.site":   30.0, "air.co.anomaly":   +1.5,  "air.co.confidence":   0.20,
        "air.hcho.score": 0.45, "air.hcho.site": 90.0, "air.hcho.anomaly": +6.0,  "air.hcho.confidence": 0.20,
        "air.o3.score":   0.20, "air.o3.site":  280.0, "air.o3.anomaly":   -2.0,  "air.o3.confidence":   0.20,
        "air.aai.score":  0.40, "air.aai.site":   0.5, "air.aai.anomaly":  +0.2,  "air.aai.confidence":  0.20,
        "air.aod.score":  0.30, "air.aod.site":   0.4, "air.aod.anomaly":  +0.1,  "air.aod.confidence":  0.20,
        # PM10/PM25 failed.
        "air.pm10.score": None, "air.pm10.site": None, "air.pm10.anomaly": None, "air.pm10.confidence": None,
        "air.pm25.score": None, "air.pm25.site": None, "air.pm25.anomaly": None, "air.pm25.confidence": None,
        # 2 successful GHG tiles.
        "ghg.ch4.score":   0.40, "ghg.ch4.site":   1875.0, "ghg.ch4.anomaly":  +15.0, "ghg.ch4.confidence":   0.70,
        "ghg.viirs.score": 0.85, "ghg.viirs.site":   58.4, "ghg.viirs.anomaly": +12.1, "ghg.viirs.confidence": 0.88,
        # CO₂ silently skipped.
        "ghg.co2.score":   None, "ghg.co2.mean":      None, "ghg.co2.confidence":   None,
        "_failures": {
            "air": [
                {"indicator_id": "air.pm10", "reason": "site buffer (5 km) smaller than pm10 native pixel (44.5 km)"},
                {"indicator_id": "air.pm25", "reason": "site buffer (5 km) smaller than pm25 native pixel (44.5 km)"},
            ],
        },
        "_provenance.ghg.co2": {"skipped_reason": "out_of_coverage"},
    }
    return payload


def test_e2e_sao_paulo_failed_tiles_are_pm10_pm25_and_co2():
    payload = _sao_paulo_payload()
    failed = [t.indicator for t in _TILES if _is_failed(t, payload)]
    assert set(failed) == {"pm10", "pm25", "co2"}


def test_e2e_sao_paulo_pm10_reason_mentions_buffer():
    """The per-indicator failure path surfaces the engine's message."""
    payload = _sao_paulo_payload()
    pm10 = next(t for t in _TILES if t.indicator == "pm10")
    assert "buffer" in _resolve_failure_reason(pm10, payload)


def test_e2e_sao_paulo_co2_reason_is_coverage_window():
    """The silent-skip path translates the provenance code."""
    payload = _sao_paulo_payload()
    co2 = next(t for t in _TILES if t.indicator == "co2")
    assert "coverage window" in _resolve_failure_reason(co2, payload).lower()


def test_e2e_sao_paulo_nine_tiles_succeed():
    payload = _sao_paulo_payload()
    successes = [t.indicator for t in _TILES if not _is_failed(t, payload)]
    assert len(successes) == 9
    assert "pm10" not in successes and "pm25" not in successes and "co2" not in successes
