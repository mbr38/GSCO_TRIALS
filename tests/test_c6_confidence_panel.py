"""Tests for ui.components.c6_confidence_panel (M-UI-E.5).

Pure-Python — no Streamlit. The dispatch helper ``_limiting_factor_for``
delegates to ``engine.verbal_summary``; this file pins the wiring so
prose in C6 cannot drift from prose in C7.
"""

# M-UI-E.5
from __future__ import annotations

import pytest

from engine.verbal_summary import (
    _GHG_LIMITING_FACTOR_PROSE,
    _NATURE_LIMITING_FACTOR_PROSE,
    _AIR_LIMITING_FACTOR_PROSE,
)
from ui.components.c6_confidence_panel import _PILLAR_ROWS, _limiting_factor_for


# ---------------------------------------------------------------------------
# _PILLAR_ROWS shape
# ---------------------------------------------------------------------------

def test_pillar_rows_has_three_entries_one_per_pillar():
    pillars = [row[2] for row in _PILLAR_ROWS]
    assert pillars == ["air", "ghg", "nature"]


# ---------------------------------------------------------------------------
# _limiting_factor_for dispatch
# ---------------------------------------------------------------------------

def test_air_dispatch_returns_lowest_confidence_pollutant_prose():
    """Air's resolver returns the prose for the lowest-confidence pollutant."""
    payload = {
        # SO₂ is lowest → its prose should be returned.
        "air.no2.confidence":  0.80,
        "air.so2.confidence":  0.05,
        "air.pm25.confidence": 0.70,
    }
    result = _limiting_factor_for("air", payload)
    assert result == _AIR_LIMITING_FACTOR_PROSE["so2"]


def test_ghg_dispatch_returns_lowest_subscore_prose():
    """GHG's resolver picks the lowest-valued sub-score from the table."""
    payload = {
        # nearby_source_isolation is lowest → its prose wins.
        "ghg.temporal_coverage":              0.80,
        "ghg.spatial_resolution_suitability": 0.70,
        "ghg.retrieval_inventory_quality":    0.65,
        "ghg.nearby_source_isolation":        0.10,
    }
    result = _limiting_factor_for("ghg", payload)
    assert result == _GHG_LIMITING_FACTOR_PROSE["ghg.nearby_source_isolation"]


def test_nature_dispatch_returns_lowest_subscore_prose():
    payload = {
        "nature.valid_pixel_coverage":      0.90,
        "nature.cloud_observation_quality": 0.85,
        "nature.dw.class_confidence":       0.05,    # lowest → wins.
        "nature.seasonal_comparability":    0.60,
        "nature.supplier_spatial_link":     0.40,
        "nature.external_driver_screening": 0.50,
    }
    result = _limiting_factor_for("nature", payload)
    assert result == _NATURE_LIMITING_FACTOR_PROSE["nature.dw.class_confidence"]


def test_unknown_pillar_returns_none():
    assert _limiting_factor_for("composite", {}) is None


def test_empty_payload_returns_none_for_each_pillar():
    """Nothing to compare → no limiting factor."""
    for pillar in ("air", "ghg", "nature"):
        assert _limiting_factor_for(pillar, {}) is None
