"""Tests for M-TIER-A3 Step H2 UI surfaces (spec §4.6).

Three surfaces are exercised:

  1. C5 expander "Coastal handling" sub-section in `ui/components/c5_drilldown.py`
     — conditional render on `ring_land_fraction < 1.0`, warning band at `< 0.20`.
  2. P-09 Indicator Library "How this is computed (coastal sites)" paragraph
     in `ui/components/p09_library.py` — static methodology paragraph
     attached to each ring-based indicator card.
  3. PDF audit appendix coastal handling sub-block in
     `ui/components/p11_sections.py` — surfaces per-indicator land/water
     splits when any indicator's ring touched the coastline.

Per-indicator P-09 hover summaries (LM9 / item 2.2) are explicitly NOT
exercised here — that surface stays focused on definitions per the LM9
locked decision.
"""

from __future__ import annotations

import pytest

from ui.components import c5_drilldown
from ui.components.c5_drilldown import (
    _COASTAL_HANDLING_BODY_TEMPLATE,
    _COASTAL_HANDLING_WARNING,
    _format_coastal_handling_pcts,
)
from ui.components.p09_library import (
    _COASTAL_HANDLING_CARD_PARAGRAPH,
    _RING_BASED_INDICATORS,
)
from ui.components.p11_sections import (
    _COASTAL_HANDLING_APPENDIX_HEADER,
    _COASTAL_HANDLING_APPENDIX_INTRO,
    _render_coastal_handling_appendix,
)


# ---------------------------------------------------------------------------
# Surface 1 — C5 expander Coastal handling sub-section
# ---------------------------------------------------------------------------


class _StreamlitSpy:
    """Records st.* calls without importing streamlit. Tests inspect this
    instead of running a real Streamlit session — keeps the suite
    decoupled from Streamlit's rendering."""

    def __init__(self) -> None:
        self.markdown_calls: list[str] = []
        self.warning_calls:  list[str] = []
        self.divider_calls:  int = 0

    def markdown(self, s, **_kwargs) -> None:
        self.markdown_calls.append(s)

    def warning(self, s, **_kwargs) -> None:
        self.warning_calls.append(s)

    def divider(self) -> None:
        self.divider_calls += 1


@pytest.fixture
def st_spy(monkeypatch):
    spy = _StreamlitSpy()
    monkeypatch.setattr(c5_drilldown, "st", spy)
    return spy


class TestC5ExpanderCoastalHandling:
    """Spec §4.6 — render conditional sub-section based on ring_land_fraction."""

    def test_omits_coastal_section_when_ring_land_fraction_is_one(
        self, st_spy,
    ) -> None:
        extra = {
            "ring_land_fraction": 1.0,
            "land_mask_applied":  True,
            "land_mask_asset":    "MODIS/006/MOD44W",
        }
        c5_drilldown._render_coastal_handling_section(extra)
        assert st_spy.markdown_calls == []
        assert st_spy.divider_calls == 0
        assert st_spy.warning_calls == []

    def test_renders_coastal_section_when_ring_land_fraction_below_one(
        self, st_spy,
    ) -> None:
        # Mumbai-realistic 0.524 land fraction.
        extra = {
            "ring_land_fraction": 0.524,
            "land_mask_applied":  True,
            "land_mask_asset":    "MODIS/006/MOD44W",
        }
        c5_drilldown._render_coastal_handling_section(extra)
        # Divider + header + body. Two markdown calls.
        assert st_spy.divider_calls == 1
        assert len(st_spy.markdown_calls) == 2
        assert "Coastal handling" in st_spy.markdown_calls[0]
        body = st_spy.markdown_calls[1]
        assert "48%" in body  # round(1 - 0.524) * 100 = 48
        assert "52%" in body  # 100 - 48 = 52

    def test_water_pct_rounds_correctly_to_integer(self) -> None:
        # 0.524 → land 52%, water 48% per spec §3.8 rounding rule.
        assert _format_coastal_handling_pcts(0.524) == (48, 52)
        # 0.571 (Rio) → 43% water, 57% land.
        assert _format_coastal_handling_pcts(0.571) == (43, 57)
        # 0.50 boundary.
        assert _format_coastal_handling_pcts(0.50) == (50, 50)
        # Below threshold (would only render if mask still applied).
        assert _format_coastal_handling_pcts(0.10) == (90, 10)

    def test_shows_warning_when_ring_land_fraction_below_zero_point_two(
        self, st_spy,
    ) -> None:
        extra = {
            "ring_land_fraction": 0.15,
            "land_mask_applied":  True,
            "land_mask_asset":    "MODIS/006/MOD44W",
        }
        c5_drilldown._render_coastal_handling_section(extra)
        assert len(st_spy.warning_calls) == 1
        assert st_spy.warning_calls[0] == _COASTAL_HANDLING_WARNING

    def test_omits_warning_when_ring_land_fraction_above_zero_point_two(
        self, st_spy,
    ) -> None:
        extra = {
            "ring_land_fraction": 0.524,
            "land_mask_applied":  True,
            "land_mask_asset":    "MODIS/006/MOD44W",
        }
        c5_drilldown._render_coastal_handling_section(extra)
        assert st_spy.warning_calls == []

    def test_omits_section_when_mask_not_applied(self, st_spy) -> None:
        # apply_land_mask=False is the opt-out path; the section's claims
        # about excluding ocean pixels would be misleading.
        extra = {
            "ring_land_fraction": 0.524,
            "land_mask_applied":  False,
            "land_mask_asset":    "MODIS/006/MOD44W",
        }
        c5_drilldown._render_coastal_handling_section(extra)
        assert st_spy.markdown_calls == []

    def test_omits_section_when_ring_land_fraction_missing(self, st_spy) -> None:
        # Defensive: legacy payloads pre-Step-E don't carry these fields.
        c5_drilldown._render_coastal_handling_section({})
        assert st_spy.markdown_calls == []

    def test_template_carries_spec_phrasing(self) -> None:
        # Pin the spec §3.8 phrasing so a future copy-tweak doesn't drift
        # from the M-TIER-A3 plain-language explainer or the PDF appendix.
        assert "background ring" in _COASTAL_HANDLING_BODY_TEMPLATE
        assert "ocean pixels" in _COASTAL_HANDLING_BODY_TEMPLATE
        assert "{water_pct}" in _COASTAL_HANDLING_BODY_TEMPLATE
        assert "{land_pct}" in _COASTAL_HANDLING_BODY_TEMPLATE


# ---------------------------------------------------------------------------
# Surface 2 — P-09 ring-based card methodology paragraph
# ---------------------------------------------------------------------------


class TestP09RingBasedCardSurface:
    def test_ring_based_set_covers_all_nine_spec_indicators(self) -> None:
        # Spec §3.8 — NO₂, SO₂, CO, HCHO, AAI, O₃, AOD, CH₄, CO₂.
        expected = {
            "air.no2.score", "air.so2.score", "air.co.score",
            "air.hcho.score", "air.aai.score", "air.o3.score",
            "air.aod.score", "ghg.ch4.score", "ghg.co2.score",
        }
        assert _RING_BASED_INDICATORS == expected

    def test_methodology_paragraph_carries_spec_phrasing(self) -> None:
        # Pin the static paragraph; locked LM9 phrasing.
        para = _COASTAL_HANDLING_CARD_PARAGRAPH
        assert "**Coastal sites.**" in para
        assert "background ring" in para
        assert "MODIS MOD44W" in para
        assert "250 m resolution" in para
        assert "confidence breakdown" in para  # cross-refs Surface 1


# ---------------------------------------------------------------------------
# Surface 3 — PDF audit appendix coastal handling sub-block
# ---------------------------------------------------------------------------


def _prov(land_fraction: float | None, applied: bool = True) -> dict:
    """Build a minimal provenance dict with optional land-mask fields."""
    if land_fraction is None:
        return {"asset_id": "X", "extra": {}}
    return {
        "asset_id": "X",
        "extra": {
            "ring_land_fraction": land_fraction,
            "land_mask_applied":  applied,
            "land_mask_asset":    "MODIS/006/MOD44W",
        },
    }


class TestPdfAuditAppendixCoastalHandling:
    def test_omits_section_when_no_indicator_touched_water(self) -> None:
        # Fully inland AOI: every indicator's ring_land_fraction == 1.0.
        prov_blocks = [
            ("air.no2", _prov(1.0)),
            ("air.so2", _prov(1.0)),
            ("ghg.ch4", _prov(1.0)),
        ]
        assert _render_coastal_handling_appendix(prov_blocks) == ""

    def test_omits_section_when_no_extras_at_all(self) -> None:
        # Pre-Step-E payloads carry no ring_land_fraction.
        prov_blocks = [
            ("air.no2", {"asset_id": "X", "extra": {}}),
        ]
        assert _render_coastal_handling_appendix(prov_blocks) == ""

    def test_includes_coastal_handling_for_affected_indicators(self) -> None:
        # Mumbai-like coastal mix — only air.no2 and ghg.ch4 hit water.
        prov_blocks = [
            ("air.no2",   _prov(0.524)),
            ("nature.dw", _prov(None)),   # no extras — should not crash
            ("ghg.ch4",   _prov(0.524)),
            ("air.aai",   _prov(1.0)),    # fully land — should be excluded
        ]
        out = _render_coastal_handling_appendix(prov_blocks)
        assert _COASTAL_HANDLING_APPENDIX_HEADER in out
        assert "air.no2" in out
        assert "ghg.ch4" in out
        # land/water split text appears for affected indicators.
        assert "52% land" in out
        assert "48% water" in out
        # air.aai (1.0 land) and nature.dw (no extras) are excluded.
        assert "air.aai" not in out
        assert "nature.dw" not in out

    def test_warning_caveat_renders_below_0_20_threshold(self) -> None:
        prov_blocks = [("air.no2", _prov(0.15))]
        out = _render_coastal_handling_appendix(prov_blocks)
        # The C5-mirroring caveat appears.
        assert "mostly water" in out

    def test_warning_caveat_omitted_above_0_20_threshold(self) -> None:
        prov_blocks = [("air.no2", _prov(0.524))]
        out = _render_coastal_handling_appendix(prov_blocks)
        assert "mostly water" not in out

    def test_skips_indicator_when_mask_explicitly_disabled(self) -> None:
        # apply_land_mask=False — the appendix's narrative would be
        # misleading (no mask was actually applied to this indicator).
        prov_blocks = [("air.no2", _prov(0.524, applied=False))]
        assert _render_coastal_handling_appendix(prov_blocks) == ""

    def test_intro_carries_spec_phrasing(self) -> None:
        # Pin the appendix intro narrative; locked LM9 phrasing parallels
        # the C5 expander body for consistency across surfaces.
        assert "MODIS MOD44W" in _COASTAL_HANDLING_APPENDIX_INTRO
        assert "250 m" in _COASTAL_HANDLING_APPENDIX_INTRO
        assert "median + σ" in _COASTAL_HANDLING_APPENDIX_INTRO
