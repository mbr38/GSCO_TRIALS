"""Tests for ui.components.traffic_light (M-UI-E.2).

Pure-Python — no Streamlit. Pins the band + dot thresholds and asserts
they match engine.verbal_summary._bucket at the boundaries, so chip
colours and prose buckets cannot disagree.
"""

# M-UI-E.2
from __future__ import annotations

import pytest

from engine.verbal_summary import _bucket
from ui.components.traffic_light import (
    band_colour,
    band_for_score,
    band_label,
    confidence_glyph,
)


# ---------------------------------------------------------------------------
# band_for_score — tertile boundaries
# ---------------------------------------------------------------------------

def test_high_boundary_inclusive():
    """0.66 is in 'high' — boundary belongs to the higher-severity band."""
    assert band_for_score(0.66) == "high"


def test_just_below_high_boundary():
    assert band_for_score(0.659) == "moderate"


def test_low_boundary_inclusive():
    """0.33 is in 'moderate' — boundary belongs to the higher-severity band."""
    assert band_for_score(0.33) == "moderate"


def test_just_below_low_boundary():
    assert band_for_score(0.329) == "low"


def test_score_zero_is_low():
    assert band_for_score(0.0) == "low"


def test_score_one_is_high():
    assert band_for_score(1.0) == "high"


def test_none_score_propagates():
    assert band_for_score(None) is None


# ---------------------------------------------------------------------------
# confidence_glyph
# ---------------------------------------------------------------------------

def test_confidence_glyph_high():
    assert confidence_glyph(0.8) == "●"


def test_confidence_glyph_moderate():
    assert confidence_glyph(0.5) == "◐"


def test_confidence_glyph_low():
    assert confidence_glyph(0.1) == "○"


def test_confidence_glyph_none_renders_as_empty_dot():
    assert confidence_glyph(None) == "○"


# ---------------------------------------------------------------------------
# Threshold lock-step with the verbal summary bucket
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("score", [0.0, 0.329, 0.33, 0.5, 0.659, 0.66, 1.0])
def test_band_matches_verbal_summary_bucket(score):
    """The C3 chip band and the C7 prose bucket must agree at every
    boundary value — both read TRAFFIC_LIGHT_THRESHOLDS from
    engine.constants. This test will fail if either side drifts.
    """
    assert band_for_score(score) == _bucket(score)


def test_none_propagates_consistently_between_band_and_bucket():
    assert band_for_score(None) is None
    assert _bucket(None) is None


# ---------------------------------------------------------------------------
# band_label and band_colour
# ---------------------------------------------------------------------------

def test_band_label_for_each_band():
    assert band_label("high")     == "High"
    assert band_label("moderate") == "Moderate"
    assert band_label("low")      == "Low"
    assert band_label(None)       == "—"


def test_band_colour_returns_hex_for_each_band():
    """Three named bands + the None fallback — every entry must be a
    7-character hex string so the inline-HTML fill bar renders.
    """
    for band in ("high", "moderate", "low", None):
        colour = band_colour(band)
        assert isinstance(colour, str)
        assert colour.startswith("#")
        assert len(colour) == 7
