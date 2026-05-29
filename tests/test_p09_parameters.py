"""Tests for the P-09 'Parameters & calibration' rendering helpers
(M-UX-A1 item 2.8).

The Streamlit rendering itself isn't exercised; the pure helpers (tier badge
colour mapping, value formatting, feature flag) carry the logic worth testing.
"""

# M-UX-A1
from __future__ import annotations

from ui.components.p09_library import (
    _PARAMETERS_SECTION_ENABLED,
    _TIER_BADGE_COLOURS,
    _format_param_value,
    _tier_badge,
)


class TestTierBadge:
    def test_badge_colours_match_ux13(self) -> None:
        # UX13 — first-pass amber, calibrated green, spec-mandated blue.
        assert _TIER_BADGE_COLOURS["first-pass"] == "#b45309"   # amber
        assert _TIER_BADGE_COLOURS["calibrated"] == "#15803d"   # green
        assert _TIER_BADGE_COLOURS["spec-mandated"] == "#1d4ed8"  # blue

    def test_badge_renders_tier_label_and_colour(self) -> None:
        html = _tier_badge("first-pass")
        assert "first-pass" in html
        assert "#b45309" in html

    def test_unknown_tier_falls_back_to_grey(self) -> None:
        html = _tier_badge("mystery")
        assert "#6b7280" in html


class TestFormatParamValue:
    def test_scalar(self) -> None:
        assert _format_param_value(2.0) == "2.0"
        assert _format_param_value(10) == "10"

    def test_tuple(self) -> None:
        assert _format_param_value((0.33, 0.66)) == "0.33, 0.66"

    def test_nested_dict_severity_bands(self) -> None:
        out = _format_param_value(
            {"zscore": {"High": 2.0, "Concern": 1.0}, "sparse_confidence": 0.40}
        )
        assert "zscore: {High=2.0, Concern=1.0}" in out
        assert "sparse_confidence=0.4" in out


def test_feature_flag_default_enabled() -> None:
    # UX20 — the surface ships on; flipping the flag hides it without
    # touching the other two surfaces.
    assert _PARAMETERS_SECTION_ENABLED is True
