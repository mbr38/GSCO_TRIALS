"""Tests for the M-ATTRIB-A1 PDF habitat-attribution appendix (§5.6).

Low-only sub-block, parallel to the coastal / fallback PDF appendices.
Targets the pure HTML-building function.
"""

from __future__ import annotations

from ui.components.p11_sections import (
    _HABITAT_ATTRIB_APPENDIX_HEADER,
    _render_habitat_attribution_appendix,
)


def _prov_blocks(state, *, offset=4.2, direction="NW", n=47):
    return [(
        "nature.supplier_spatial_link",
        {
            "asset_id": "GOOGLE/DYNAMICWORLD/V1",
            "extra": {
                "spatial_link_terms": {
                    "attributability_state": state,
                    "centroid_offset_km": offset,
                    "direction": direction,
                    "n_change_pixels": n,
                },
            },
        },
    )]


def test_low_renders_appendix_with_distance_direction_and_pixels():
    html = _render_habitat_attribution_appendix(_prov_blocks("low"))
    assert _HABITAT_ATTRIB_APPENDIX_HEADER in html
    assert "Low" in html
    assert "4.2 km" in html
    assert "NW" in html
    assert "47" in html


def test_high_renders_nothing():
    assert _render_habitat_attribution_appendix(_prov_blocks("high", offset=0.5)) == ""


def test_moderate_renders_nothing():
    assert _render_habitat_attribution_appendix(_prov_blocks("moderate", offset=2.0)) == ""


def test_sparse_renders_nothing():
    assert _render_habitat_attribution_appendix(
        _prov_blocks("sparse", offset=None, direction=None, n=0)
    ) == ""


def test_absent_block_renders_nothing():
    assert _render_habitat_attribution_appendix([]) == ""
