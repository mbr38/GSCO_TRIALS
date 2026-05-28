"""Tests for the M-UI-A6 reference-dataset treatment (Hansen + ODIAC).

Pure-Python — no Streamlit. Per the C5 test convention, the ``render_*``
functions write to Streamlit and can't be asserted on directly, so these
tests target the pure field/interpretation/vintage helpers, the C7 clause
logic, the PDF section function, and the cross-milestone regressions from
the M-UI-A6 spec §8.
"""

# M-UI-A6
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ui.components.c5_drilldown import (
    _DATA_UNAVAILABLE_TEXT,
    _ODIAC_INTERPRETATION,
    _ODIAC_UNAVAILABLE_INTERPRETATION,
    _REFERENCE_BADGE_TEXT,
    _ReferenceCardFields,
    _hansen_card_fields,
    _hansen_interpretation,
    _hansen_vintage_year,
    _odiac_card_fields,
    _odiac_vintage_year,
    _parse_year_from_asset_id,
    _regional_context_line,
)
from engine.verbal_summary import (
    _hansen_reference_clause,
    generate_verbal_summary,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HANSEN_PROV_2023 = {
    "_provenance.nature.forest_loss": {
        "asset_id": "UMD/hansen/global_forest_change_2023_v1_11",
    },
}
_ODIAC_PROV_2023 = {
    "_provenance.ghg.co2": {"coverage_window": ["2020-01-01", "2023-12-31"]},
}


def _full_present_payload() -> dict:
    """A payload where both reference datasets have values."""
    return {
        "nature.forest_loss.pct": 2.34,
        "ghg.co2.mean": 12450.0,
        **_HANSEN_PROV_2023,
        **_ODIAC_PROV_2023,
    }


# ---------------------------------------------------------------------------
# RD5 — canonical badge text
# ---------------------------------------------------------------------------

def test_badge_text_is_canonical_string():
    assert _REFERENCE_BADGE_TEXT == (
        "Reference dataset — not used in composite score"
    )


# ---------------------------------------------------------------------------
# Vintage derivation (Step B: derived in UI, no engine field)
# ---------------------------------------------------------------------------

def test_parse_year_from_hansen_asset_id():
    assert _parse_year_from_asset_id(
        "UMD/hansen/global_forest_change_2023_v1_11"
    ) == 2023


def test_parse_year_returns_last_year_run():
    # The 11 in v1_11 is two digits and must not be read as a year.
    assert _parse_year_from_asset_id("foo_2020_2023_v1_11") == 2023


def test_parse_year_none_when_no_year():
    assert _parse_year_from_asset_id("projects/x/assets/odiac") is None
    assert _parse_year_from_asset_id(None) is None


def test_hansen_vintage_from_provenance():
    assert _hansen_vintage_year(_HANSEN_PROV_2023) == 2023


def test_hansen_vintage_falls_back_when_no_provenance():
    # Fallback mirrors engine.nature._HANSEN_MAX_LOSS_YEAR (23 → 2023).
    assert _hansen_vintage_year({}) == 2023


# ---------------------------------------------------------------------------
# M-ATTRIB-A1 (AT6/AT22) — Hansen-card regional-context line
# ---------------------------------------------------------------------------

class TestRegionalContextLine:
    def test_none_when_ratio_or_window_missing(self):
        assert _regional_context_line({}) is None
        assert _regional_context_line(
            {"nature.regional_loss_evidence.ratio": 1.2}
        ) is None
        assert _regional_context_line(
            {"nature.regional_loss_evidence.window": "2019–2023"}
        ) is None

    def test_low_ratio_says_buffer_was_active_pocket(self):
        line = _regional_context_line({
            "nature.regional_loss_evidence.ratio": 0.3,
            "nature.regional_loss_evidence.window": "2019–2023",
        })
        assert "ring loss is 0.3× buffer loss over 2019–2023" in line
        assert "active deforestation pocket" in line

    def test_similar_ratio_says_no_strong_pattern(self):
        line = _regional_context_line({
            "nature.regional_loss_evidence.ratio": 1.0,
            "nature.regional_loss_evidence.window": "2019–2023",
        })
        assert "no strong" in line

    def test_high_ratio_says_broader_regional_pattern(self):
        line = _regional_context_line({
            "nature.regional_loss_evidence.ratio": 3.5,
            "nature.regional_loss_evidence.window": "2019–2023",
        })
        assert "ring loss is 3.5× buffer loss" in line
        assert "broader regional deforestation pattern" in line

    def test_hansen_card_fields_carries_regional_context(self):
        payload = {
            "nature.forest_loss.pct": 2.34,
            "nature.regional_loss_evidence.ratio": 1.8,
            "nature.regional_loss_evidence.window": "2019–2023",
            **_HANSEN_PROV_2023,
        }
        fields = _hansen_card_fields(payload)
        assert fields.regional_context is not None
        assert "1.8×" in fields.regional_context

    def test_odiac_card_has_no_regional_context(self):
        fields = _odiac_card_fields(_full_present_payload())
        assert fields.regional_context is None


def test_odiac_vintage_from_coverage_window():
    assert _odiac_vintage_year(_ODIAC_PROV_2023) == 2023


def test_odiac_vintage_none_when_no_window():
    assert _odiac_vintage_year({}) is None
    assert _odiac_vintage_year(
        {"_provenance.ghg.co2": {"coverage_window": None}}
    ) is None


# ---------------------------------------------------------------------------
# §4.1 — Hansen interpretation bands
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pct, fragment", [
    (7.5, "Substantial cumulative loss"),
    (5.0, "Substantial cumulative loss"),   # boundary → substantial
    (2.34, "Moderate cumulative loss"),
    (1.0, "Moderate cumulative loss"),       # boundary → moderate
    (0.5, "Minimal cumulative loss"),
    (0.0, "Minimal cumulative loss"),
])
def test_hansen_interpretation_bands(pct, fragment):
    assert fragment in _hansen_interpretation(pct)


def test_hansen_interpretation_none():
    assert _hansen_interpretation(None) == (
        "Hansen data is not available for this AOI."
    )


# ---------------------------------------------------------------------------
# §8.1 — card field rendering (value, badge, vintage, source, interpretation,
# footnote, P-09 link)
# ---------------------------------------------------------------------------

def test_hansen_card_fields_present():
    f = _hansen_card_fields(_full_present_payload())
    assert isinstance(f, _ReferenceCardFields)
    assert f.value_str == "2.34%"
    assert f.unit_line == "of buffer area lost (5-year cumulative)"
    assert f.vintage_line == "Latest Hansen data: 2023"
    assert "University of Maryland" in f.source_line
    assert "Moderate cumulative loss" in f.interpretation
    # RD8 / M-ATTRIB-A1: explains what Hansen *does* feed — the reference
    # ring-vs-buffer ratio (External Driver Screening was removed by AT5).
    assert "ring-vs-buffer ratio" in f.audit_footnote
    assert "not part of the composite score" in f.audit_footnote
    # P-09 link target (M-UI-A2 affordance uses the library card key).
    assert f.indicator_id == "nature.forest_loss.ha"


def test_odiac_card_fields_present():
    f = _odiac_card_fields(_full_present_payload())
    assert f.value_str == "12,450 t CO₂ yr⁻¹ per pixel"
    assert f.unit_line == "annual emissions intensity"
    assert f.vintage_line == "Latest ODIAC year: 2023"
    assert "NIES" in f.source_line
    assert f.interpretation == _ODIAC_INTERPRETATION
    assert "inventory-allocated" in f.audit_footnote
    assert f.indicator_id == "ghg.co2.score"


# ---------------------------------------------------------------------------
# RD12 — missing-data path (card still renders; "Data not available")
# ---------------------------------------------------------------------------

def test_hansen_card_missing_value():
    f = _hansen_card_fields({})
    assert f.value_str is None          # → render shows _DATA_UNAVAILABLE_TEXT
    assert _hansen_interpretation(None) == f.interpretation


def test_odiac_card_missing_value():
    f = _odiac_card_fields({"ghg.co2.mean": None})
    assert f.value_str is None
    assert f.interpretation == _ODIAC_UNAVAILABLE_INTERPRETATION
    # Vintage line still shows a placeholder, not a crash.
    assert f.vintage_line == "Latest ODIAC year: —"


def test_data_unavailable_text_constant():
    assert _DATA_UNAVAILABLE_TEXT == "Data not available for this AOI"


# ---------------------------------------------------------------------------
# RD7 — both cards share the same standardised structure
# ---------------------------------------------------------------------------

def test_both_cards_share_field_structure():
    payload = _full_present_payload()
    hansen = _hansen_card_fields(payload)
    odiac = _odiac_card_fields(payload)
    # Same dataclass, same set of populated attributes — RD7.
    assert set(vars(hansen)) == set(vars(odiac))
    for f in (hansen, odiac):
        assert f.display_name
        assert f.value_str is not None
        assert f.unit_line and f.vintage_line and f.source_line
        assert f.interpretation and f.audit_footnote
        assert f.indicator_id and f.key_prefix


# ---------------------------------------------------------------------------
# §8.4 — C7 verbal-summary integration (corroboration / divergence / quiet)
# ---------------------------------------------------------------------------

def test_corroboration_fires_when_loss_and_concern():
    payload = {
        "nature.forest_loss.pct": 3.2,
        "nature.biodiversity_exposure": 0.8,   # gives a dominant driver
    }
    clause = _hansen_reference_clause(payload, "high")
    assert clause is not None
    assert "consistent with" in clause
    assert "3.2%" in clause


def test_corroboration_fires_at_moderate_bucket():
    payload = {"nature.forest_loss.pct": 1.5}
    clause = _hansen_reference_clause(payload, "moderate")
    assert clause is not None and "consistent with" in clause


def test_divergence_fires_when_loss_but_quiet():
    payload = {"nature.forest_loss.pct": 4.0}
    clause = _hansen_reference_clause(payload, "low")
    assert clause is not None
    assert "diverge" in clause
    assert "4.0%" in clause


def test_quiet_no_mention_below_threshold():
    # < 1% cumulative loss → no Hansen sentence regardless of bucket.
    assert _hansen_reference_clause({"nature.forest_loss.pct": 0.4}, "high") is None
    assert _hansen_reference_clause({"nature.forest_loss.pct": 0.99}, "low") is None


def test_no_mention_when_loss_missing():
    assert _hansen_reference_clause({}, "high") is None


def test_odiac_never_mentioned_in_reference_clause():
    """RD §6.4 regression — the reference-dataset clause never opines on
    ODIAC. (The GHG paragraph may still name ODIAC as a live-pillar driver;
    that is a separate, pre-existing surface.)"""
    for bucket in ("high", "moderate", "low"):
        for pct in (0.0, 2.0, 9.0):
            clause = _hansen_reference_clause(
                {"nature.forest_loss.pct": pct}, bucket
            )
            assert clause is None or "ODIAC" not in clause


def test_generate_verbal_summary_appends_hansen_clause():
    payload = {
        "nature.followup_priority": 0.9,      # → high nature bucket
        "nature.forest_loss.pct": 3.0,
        "nature.biodiversity_exposure": 0.8,
    }
    summary = generate_verbal_summary(payload)
    assert "cumulative loss" in summary.nature


def test_generate_verbal_summary_omits_clause_when_quiet():
    payload = {
        "nature.followup_priority": 0.9,
        "nature.forest_loss.pct": 0.2,        # below threshold → no mention
    }
    summary = generate_verbal_summary(payload)
    assert "Hansen reference dataset" not in summary.nature


# ---------------------------------------------------------------------------
# §8.5 — PDF reference-datasets section
# ---------------------------------------------------------------------------

def _screening_source(payload: dict, name: str = "Demo AOI") -> dict:
    return {"type": "screening", "name": name, "payload": payload}


def test_pdf_section_includes_disclaimer_and_both_datasets():
    from ui.components.p11_sections import _render_reference_datasets

    html = _render_reference_datasets(
        None, [_screening_source(_full_present_payload())]
    )
    assert "Reference datasets" in html
    assert "not part of the composite score" in html
    assert "Hansen forest loss" in html
    assert "ODIAC" in html
    assert "2.34%" in html
    assert "12,450" in html


def test_pdf_section_handles_missing_values():
    from ui.components.p11_sections import _render_reference_datasets

    html = _render_reference_datasets(
        None, [_screening_source({})]
    )
    assert html.count("Data not available for this AOI") == 2


def test_pdf_section_omitted_when_no_screening_source():
    from ui.components.p11_sections import _render_reference_datasets

    assert _render_reference_datasets(None, []) == ""
    assert _render_reference_datasets(
        None, [{"type": "prioritisation", "name": "x"}]
    ) == ""


def test_reference_datasets_section_registered_and_in_templates():
    from ui.components.p11_sections import get_section
    from ui.components.p11_templates import get_template

    assert callable(get_section("reference_datasets"))
    for tid in ("policy_audit", "supplier_audit"):
        sections = get_template(tid).sections
        assert "reference_datasets" in sections
        # RD10 — after the scored-indicators section, before provenance.
        assert sections.index("reference_datasets") < sections.index(
            "provenance_appendix"
        )


# ---------------------------------------------------------------------------
# §8.6 — cross-milestone regression (Hansen/ODIAC absent from headline grid)
# ---------------------------------------------------------------------------

def test_hansen_odiac_absent_from_c4b_headline_grid():
    from ui.components.c4b_kpi_grid import _TILES

    blob = repr(_TILES)
    assert "forest_loss" not in blob
    assert "ghg.co2" not in blob
    assert "Hansen" not in blob
    assert "ODIAC" not in blob


# ---------------------------------------------------------------------------
# §8.7 — golden fixtures (demo saved analyses must render without crashing)
# ---------------------------------------------------------------------------

_SAVED = Path(__file__).resolve().parent.parent / "demo" / "saved_analyses"


# Golden values from the M-V1x-STANDING-WINDOW regeneration (28 May 2026):
# both fixtures now carry real window-independent reference values — Hansen
# cumulative loss over 2019-2023, ODIAC 2023 annual intensity. Hansen is < 1%
# in both AOIs (→ "Minimal"); ODIAC is now present (→ generic interpretation),
# where it used to be None under the old window-bounded engine.
@pytest.mark.parametrize("fixture, hansen_value, odiac_value", [
    ("high_priority_amazon.json", "0.13%", "48 t CO₂ yr⁻¹ per pixel"),
    ("low_priority_brasilia.json", "0.56%", "1,888 t CO₂ yr⁻¹ per pixel"),
])
def test_golden_fixtures_render_reference_cards(fixture, hansen_value, odiac_value):
    payload = json.loads((_SAVED / fixture).read_text())["payload"]
    hansen = _hansen_card_fields(payload)
    odiac = _odiac_card_fields(payload)
    assert hansen.value_str == hansen_value
    assert "Minimal cumulative loss" in hansen.interpretation
    assert odiac.value_str == odiac_value
    assert odiac.interpretation == _ODIAC_INTERPRETATION
    # Standing-exposure vintage, derived in the UI from provenance.
    assert hansen.vintage_line == "Latest Hansen data: 2023"
    assert odiac.vintage_line == "Latest ODIAC year: 2023"
