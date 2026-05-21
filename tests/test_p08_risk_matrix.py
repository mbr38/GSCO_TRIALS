"""Tests for ui.components.p08_risk_matrix (M-P08.3).

Pure-Python — no Streamlit / Plotly rendering. Targets the helper
functions that drive axis options, defaults, filtering, key lookup,
and band colouring.
"""

# M-P08.3
from __future__ import annotations

import pytest

from engine.constants import TRAFFIC_LIGHT_THRESHOLDS
from ui.components.p08_risk_matrix import (
    _BAND_COLOURS,
    _axis_to_payload_key,
    _band_colour,
    _build_axis_options,
    _default_x_index,
    _default_y_index,
    _filter_plottable,
    _fmt_composite,
)
from ui.prioritisation_state import SupplierResult


_ALL_PILLARS = {"air", "ghg", "nature"}


def _supplier(
    name: str,
    status: str = "success",
    air: float | None = None,
    ghg: float | None = None,
    nature: float | None = None,
    composite: float | None = None,
    error: str | None = None,
    result_is_none: bool = False,
) -> SupplierResult:
    """Build a SupplierResult with a synthetic engine payload."""
    if result_is_none or status in ("failed", "cancelled"):
        result = None
    else:
        result = {
            "air.audit_followup_priority": air,
            "ghg.audit_followup_priority": ghg,
            "nature.followup_priority":    nature,
            "composite.overall_screening": composite,
        }
    return SupplierResult(
        supplier_id=name.lower().replace(" ", "_"),
        name=name,
        lat=0.0, lon=0.0, source="ad_hoc",
        status=status,
        result=result,
        error=error,
    )


# ---------------------------------------------------------------------------
# _build_axis_options
# ---------------------------------------------------------------------------

def test_axis_options_all_three_pillars_with_composite():
    assert _build_axis_options(_ALL_PILLARS, show_composite=True) == [
        "Composite", "Air", "GHG", "Nature",
    ]


def test_axis_options_two_pillars_no_composite():
    assert _build_axis_options(
        {"air", "ghg"}, show_composite=False,
    ) == ["Air", "GHG"]


def test_axis_options_single_pillar_returns_one_entry():
    """One-entry result triggers the <2 banner in render_risk_matrix."""
    assert _build_axis_options({"air"}, show_composite=False) == ["Air"]


# ---------------------------------------------------------------------------
# _default_x_index / _default_y_index
# ---------------------------------------------------------------------------

def test_default_x_index_picks_air_when_present():
    options = ["Composite", "Air", "GHG", "Nature"]
    assert _default_x_index(options) == 1


def test_default_x_index_falls_back_to_first_when_air_absent():
    options = ["Composite", "GHG", "Nature"]
    assert _default_x_index(options) == 0


def test_default_y_index_picks_nature_when_present_and_distinct():
    options = ["Composite", "Air", "GHG", "Nature"]
    assert _default_y_index(options, x_axis="Air") == 3


def test_default_y_index_falls_back_to_first_non_x_when_nature_absent():
    """No Nature in options → pick the first option that isn't x_axis."""
    options = ["Composite", "Air", "GHG"]
    assert _default_y_index(options, x_axis="Air") == 0  # Composite ≠ Air


def test_default_y_index_skips_x_when_x_equals_nature():
    """X is Nature → default-y can't also be Nature; falls back."""
    options = ["Composite", "Air", "GHG", "Nature"]
    idx = _default_y_index(options, x_axis="Nature")
    assert options[idx] != "Nature"


# ---------------------------------------------------------------------------
# _axis_to_payload_key
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("axis, expected", [
    ("Composite", "composite.overall_screening"),
    ("Air",       "air.audit_followup_priority"),
    ("GHG",       "ghg.audit_followup_priority"),
    ("Nature",    "nature.followup_priority"),
])
def test_axis_to_payload_key_known_labels(axis, expected):
    assert _axis_to_payload_key(axis) == expected


def test_axis_to_payload_key_unknown_label_defensive_fallback():
    """Unrecognised axis label → composite (worst case = wrong axis,
    not a stack trace)."""
    assert _axis_to_payload_key("Mystery") == "composite.overall_screening"


# ---------------------------------------------------------------------------
# _filter_plottable
# ---------------------------------------------------------------------------

def test_filter_plottable_all_successful_all_included():
    suppliers = [
        _supplier("A", air=0.2, nature=0.3, composite=0.25),
        _supplier("B", air=0.5, nature=0.6, composite=0.55),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert len(plottable) == 2
    assert omitted == 0
    assert [p["name"] for p in plottable] == ["A", "B"]


def test_filter_plottable_failed_omitted():
    suppliers = [
        _supplier("A", air=0.5, nature=0.5, composite=0.5),
        _supplier("B", status="failed", error="boom"),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert len(plottable) == 1
    assert omitted == 1
    assert plottable[0]["name"] == "A"


def test_filter_plottable_cancelled_omitted():
    suppliers = [
        _supplier("A", air=0.5, nature=0.5, composite=0.5),
        _supplier("B", status="cancelled"),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert len(plottable) == 1
    assert omitted == 1


def test_filter_plottable_x_axis_none_omitted():
    suppliers = [
        _supplier("A", air=None, nature=0.5, composite=0.25),
        _supplier("B", air=0.4, nature=0.5, composite=0.45),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert [p["name"] for p in plottable] == ["B"]
    assert omitted == 1


def test_filter_plottable_y_axis_none_omitted():
    suppliers = [
        _supplier("A", air=0.5, nature=None, composite=0.25),
        _supplier("B", air=0.4, nature=0.5, composite=0.45),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert [p["name"] for p in plottable] == ["B"]
    assert omitted == 1


def test_filter_plottable_partial_status_included():
    """A partial supplier with both scores still plots."""
    suppliers = [
        _supplier("A", status="partial", air=0.5, nature=0.5, composite=0.5),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert len(plottable) == 1
    assert omitted == 0


def test_filter_plottable_result_none_omitted():
    """Defensive — status looks OK but result dict is None."""
    suppliers = [
        _supplier("A", status="success", result_is_none=True),
        _supplier("B", air=0.4, nature=0.5, composite=0.45),
    ]
    plottable, omitted = _filter_plottable(suppliers, "Air", "Nature")
    assert [p["name"] for p in plottable] == ["B"]
    assert omitted == 1


# ---------------------------------------------------------------------------
# _band_colour
# ---------------------------------------------------------------------------

def test_band_colour_none_is_grey():
    assert _band_colour(None) == _BAND_COLOURS["grey"]


def test_band_colour_high_score_is_red():
    _, high = TRAFFIC_LIGHT_THRESHOLDS
    assert _band_colour(high + 0.1) == _BAND_COLOURS["red"]


def test_band_colour_mid_score_is_amber():
    low, high = TRAFFIC_LIGHT_THRESHOLDS
    assert _band_colour((low + high) / 2) == _BAND_COLOURS["amber"]


def test_band_colour_low_score_is_green():
    low, _ = TRAFFIC_LIGHT_THRESHOLDS
    assert _band_colour(low - 0.1) == _BAND_COLOURS["green"]


def test_band_colour_exactly_high_threshold_is_red():
    """≥-based comparison: a score of exactly 0.66 lands in red."""
    _, high = TRAFFIC_LIGHT_THRESHOLDS
    assert _band_colour(high) == _BAND_COLOURS["red"]


def test_band_colour_exactly_low_threshold_is_amber():
    """Score of exactly 0.33 lands in amber (≥-based comparison)."""
    low, _ = TRAFFIC_LIGHT_THRESHOLDS
    assert _band_colour(low) == _BAND_COLOURS["amber"]


# ---------------------------------------------------------------------------
# _fmt_composite
# ---------------------------------------------------------------------------

def test_fmt_composite_float():
    assert _fmt_composite(0.4242) == "0.42"


def test_fmt_composite_none():
    assert _fmt_composite(None) == "—"
