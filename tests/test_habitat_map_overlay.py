"""Tests for the M-ATTRIB-A1 habitat attributability map overlay (§5.1/§5.2).

Targets the pure folium-element construction (`_habitat_overlay_elements`)
and the hover-tooltip text (`_habitat_centroid_tooltip`) rather than the
Streamlit render path, per the C4a test convention.
"""

from __future__ import annotations

import folium
import pytest

from ui.components.c4a_indicator_map import (
    _habitat_centroid_tooltip,
    _habitat_overlay_elements,
)


_SETUP = {"centre": {"lat": -13.50, "lon": -58.80}, "radius_km": 5.0}


def _result(state, *, lat=-13.49, lon=-58.79, offset=0.8, n=40):
    return {
        "nature.habitat.attributability_state": state,
        "nature.supplier_spatial_link.centroid_lat": lat,
        "nature.supplier_spatial_link.centroid_lon": lon,
        "nature.supplier_spatial_link.centroid_offset_km": offset,
        "nature.supplier_spatial_link.n_change_pixels": n,
    }


class TestCentroidTooltip:
    def test_format_matches_spec(self):
        t = _habitat_centroid_tooltip("high", 0.8, 40)
        assert t == (
            "Habitat changes centred 0.8 km from supplier — "
            "High attributability. N = 40 change pixels."
        )

    def test_low_label(self):
        assert "Low attributability" in _habitat_centroid_tooltip("low", 4.2, 47)


class TestOverlayElements:
    def test_high_renders_marker_and_line(self):
        elements = _habitat_overlay_elements(_SETUP, _result("high"))
        assert len(elements) == 2
        marker, line = elements
        assert isinstance(marker, folium.Marker)
        assert isinstance(line, folium.PolyLine)
        assert marker.location == [-13.49, -58.79]
        # green for high (AT9).
        assert marker.icon.options["markerColor"] == "green"
        assert line.options["color"] == "#16a34a"
        # Line runs supplier centre → centroid.
        assert line.locations == [[-13.50, -58.80], [-13.49, -58.79]]

    def test_low_uses_red(self):
        marker, line = _habitat_overlay_elements(_SETUP, _result("low", offset=4.2))
        assert marker.icon.options["markerColor"] == "red"
        assert line.options["color"] == "#dc2626"

    def test_moderate_uses_orange(self):
        marker, line = _habitat_overlay_elements(_SETUP, _result("moderate", offset=2.0))
        assert marker.icon.options["markerColor"] == "orange"
        assert line.options["color"] == "#f59e0b"

    def test_sparse_renders_nothing(self):
        assert _habitat_overlay_elements(_SETUP, _result("sparse", lat=None, lon=None)) == []

    def test_no_centroid_renders_nothing(self):
        assert _habitat_overlay_elements(_SETUP, _result("high", lat=None, lon=None)) == []

    def test_absent_state_renders_nothing(self):
        assert _habitat_overlay_elements(_SETUP, {}) == []

    def test_marker_carries_hover_tooltip(self):
        marker, _line = _habitat_overlay_elements(_SETUP, _result("high"))
        # folium stores the tooltip as a child Tooltip element.
        tooltips = [
            c for c in marker._children.values()
            if isinstance(c, folium.Tooltip)
        ]
        assert tooltips, "centroid marker should carry a hover tooltip"
        assert "attributability" in tooltips[0].text.lower()
