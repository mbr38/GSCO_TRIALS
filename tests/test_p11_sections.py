"""Tests for ui.components.p11_sections (M-P11.2).

Pure-Python — no Streamlit, no Jinja runtime required. Section
functions return raw HTML strings; we assert on substrings, table
shape, and presence of templated phrasing.
"""

# M-P11.2
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ui.components import p11_sections
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_sections import (
    _band_for_score,
    _composite_score,
    _fmt,
    _render_executive_summary,
    _render_indicator_detail,
    _render_methodology,
    _render_per_supplier_detail,
    _render_pillar_findings,
    _render_priority_findings,
    _render_provenance_appendix,
    _render_source_pillar_block,
    _render_title_page,
    get_section,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _state(title="Demo report", notes=""):
    return SimpleNamespace(title=title, notes=notes)


def _screening_source(
    sid="src-1",
    name="Screening A",
    composite=0.5,
    indicators=None,
    extra_payload=None,
):
    payload = {
        "air.audit_followup_priority":    0.6,
        "ghg.audit_followup_priority":    0.4,
        "nature.followup_priority":       0.2,
        "composite.overall_screening":    composite,
    }
    if extra_payload:
        payload.update(extra_payload)
    if indicators is None:
        # Default: full-19 coverage so the verbal-summary path fires
        # (M-P11.2-FIX gates the summary on full coverage).
        indicators = list(ALL_INDICATOR_IDS)
    return {
        "id":              sid,
        "name":            name,
        "type":            "screening",
        "screening_setup": {
            "centre":     {"lat": 1.0, "lon": 2.0},
            "radius_km":  10,
            "time_range": ["2025-01-01", "2025-06-01"],
            "indicators": indicators,
        },
        "payload":         payload,
    }


def _prioritisation_source(
    sid="prio-1",
    name="Prioritisation A",
    n_suppliers=2,
):
    supplier_results = [
        {
            "name":   f"Supplier {i}",
            "status": "success",
            "result": {
                "air.audit_followup_priority": 0.6,
                "ghg.audit_followup_priority": 0.4,
                "nature.followup_priority":    0.2,
                "composite.overall_screening": 0.4 + 0.1 * i,
            },
        }
        for i in range(n_suppliers)
    ]
    return {
        "id":                   sid,
        "name":                 name,
        "type":                 "prioritisation",
        "prioritisation_setup": {
            "indicators": ["air.no2.score"] * 19,
        },
        "supplier_results":     supplier_results,
    }


# ---------------------------------------------------------------------------
# 5a. get_section
# ---------------------------------------------------------------------------

def test_get_section_known_keys_return_callable():
    for key in (
        "title_page",
        "executive_summary",
        "methodology",
        "scope_summary",
        "pillar_findings",
        "priority_findings",
        "indicator_detail",
        "per_supplier_detail",
        "provenance_appendix",
    ):
        fn = get_section(key)
        assert callable(fn), f"section {key} did not resolve to a callable"


def test_get_section_unknown_key_returns_none():
    assert get_section("not_a_real_section") is None


# ---------------------------------------------------------------------------
# 5b/5c. title page
# ---------------------------------------------------------------------------

def test_render_title_page_includes_title_and_source_count():
    out = _render_title_page(_state("Q2 demo"), [_screening_source()])
    assert "Q2 demo" in out
    assert "1 source" in out
    # Date string is present (year — current year)
    from datetime import datetime, timezone
    assert datetime.now(timezone.utc).strftime("%Y") in out


def test_render_title_page_empty_title_uses_placeholder():
    out = _render_title_page(_state(""), [])
    assert "Untitled report" in out
    assert "0 sources" in out


# ---------------------------------------------------------------------------
# 5d/5e. executive summary
# ---------------------------------------------------------------------------

def test_render_executive_summary_includes_one_row_per_source():
    sources = [_screening_source("a", "Source A"),
               _screening_source("b", "Source B")]
    out = _render_executive_summary(_state(), sources)
    assert "<table>" in out
    assert "Source A" in out
    assert "Source B" in out
    # Two data rows + one header row.
    assert out.count("<tr>") == 3


def test_render_executive_summary_includes_notes_when_present():
    out = _render_executive_summary(
        _state(notes="Custom intro paragraph for stakeholders."),
        [_screening_source()],
    )
    assert "Custom intro paragraph for stakeholders." in out


def test_render_executive_summary_omits_notes_when_blank():
    out = _render_executive_summary(_state(notes=""), [_screening_source()])
    assert "Custom intro" not in out


# ---------------------------------------------------------------------------
# 5f/5g. methodology
# ---------------------------------------------------------------------------

def test_render_methodology_partial_caveat_when_indicators_under_19():
    src = _screening_source(indicators=["a", "b", "c"])
    out = _render_methodology(_state(), [src])
    assert "Partial coverage" in out


def test_render_methodology_no_caveat_when_all_full_19():
    src = _screening_source(indicators=[f"ind_{i}" for i in range(19)])
    out = _render_methodology(_state(), [src])
    assert "Partial coverage" not in out


# ---------------------------------------------------------------------------
# 5h. pillar findings reuses verbal summary
# ---------------------------------------------------------------------------

def test_render_pillar_findings_invokes_verbal_summary_per_source():
    src_a = _screening_source("a", "A")
    src_b = _screening_source("b", "B")
    fake = SimpleNamespace(
        overview="overview-text",
        air="air-text",
        ghg="ghg-text",
        nature="nature-text",
    )
    with patch.object(
        p11_sections, "generate_verbal_summary", return_value=fake,
    ) as mock_vs:
        out = _render_pillar_findings(_state(), [src_a, src_b])
    assert mock_vs.call_count == 2
    assert "overview-text" in out
    assert "air-text" in out


# ---------------------------------------------------------------------------
# 5i. priority findings — branches by source type
# ---------------------------------------------------------------------------

def test_render_priority_findings_prioritisation_renders_ranked_table():
    out = _render_priority_findings(_state(), [_prioritisation_source()])
    assert "Supplier 0" in out
    assert "Supplier 1" in out
    # Includes a status column row per supplier.
    assert "success" in out


def test_render_priority_findings_screening_renders_pillar_score_block():
    out = _render_priority_findings(_state(), [_screening_source()])
    assert "Air Pollution" in out
    assert "GHG Emissions" in out
    assert "Nature/Land" in out
    assert "Composite" in out


# ---------------------------------------------------------------------------
# 5j. provenance appendix
# ---------------------------------------------------------------------------

def test_render_provenance_appendix_empty_payload_shows_no_entries():
    src = _screening_source(extra_payload={})
    out = _render_provenance_appendix(_state(), [src])
    assert "No provenance entries" in out


def test_render_provenance_appendix_renders_entries_when_present():
    extra = {
        "_provenance.air.no2.score": {
            "asset_id":       "COPERNICUS/S5P/OFFL/L3_NO2",
            "native_scale_m": 1113.0,
            "time_range":     ("2025-01-01", "2025-06-01"),
            "skipped_reason": None,
        },
        "_provenance.ghg.ch4": {
            "asset_id":       "COPERNICUS/S5P/OFFL/L3_CH4",
            "native_scale_m": 7000.0,
            "time_range":     ("2025-01-01", "2025-06-01"),
            "skipped_reason": "Not enough valid grids",
        },
    }
    src = _screening_source(extra_payload=extra)
    out = _render_provenance_appendix(_state(), [src])
    assert "COPERNICUS/S5P/OFFL/L3_NO2" in out
    assert "COPERNICUS/S5P/OFFL/L3_CH4" in out
    assert "Skipped" in out
    assert "OK" in out


# ---------------------------------------------------------------------------
# 5k. _band_for_score
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score, expected_class, expected_label",
    [
        (None,  "grey",  "No data"),
        (0.80,  "red",   "High priority"),
        (0.66,  "red",   "High priority"),
        (0.50,  "amber", "Moderate"),
        (0.33,  "amber", "Moderate"),
        (0.10,  "green", "Low priority"),
        (0.0,   "green", "Low priority"),
    ],
)
def test_band_for_score_buckets(score, expected_class, expected_label):
    css, label = _band_for_score(score)
    assert css == expected_class
    assert label == expected_label


# ---------------------------------------------------------------------------
# 5l. _composite_score
# ---------------------------------------------------------------------------

def test_composite_score_screening_source_pulls_direct_value():
    src = _screening_source(composite=0.42)
    assert _composite_score(src) == pytest.approx(0.42)


def test_composite_score_prioritisation_source_averages_plottable():
    src = _prioritisation_source(n_suppliers=2)
    # supplier 0 → 0.4, supplier 1 → 0.5 → mean 0.45
    assert _composite_score(src) == pytest.approx(0.45)


def test_composite_score_missing_returns_none():
    src = {"type": "screening", "payload": {}}
    assert _composite_score(src) is None
    # Prioritisation with no success/partial entries.
    src2 = {
        "type":             "prioritisation",
        "supplier_results": [
            {"status": "failed", "result": {}},
        ],
    }
    assert _composite_score(src2) is None


# ---------------------------------------------------------------------------
# 5m. _fmt
# ---------------------------------------------------------------------------

def test_fmt_none_returns_dash():
    assert _fmt(None) == "—"


def test_fmt_float_returns_two_decimals():
    assert _fmt(0.4242) == "0.42"
    assert _fmt(1) == "1.00"


def test_fmt_non_numeric_returns_dash():
    assert _fmt("foo") == "—"
    assert _fmt(object()) == "—"


# ---------------------------------------------------------------------------
# M-P11.2-FIX — per-supplier detail skips screening sources
# ---------------------------------------------------------------------------

def test_per_supplier_detail_only_screenings_returns_empty():
    out = _render_per_supplier_detail(
        _state(),
        [_screening_source("a", "Scr A"), _screening_source("b", "Scr B")],
    )
    assert out == ""


def test_per_supplier_detail_only_prioritisations_renders_breakdown():
    out = _render_per_supplier_detail(
        _state(),
        [_prioritisation_source(name="Prio A")],
    )
    assert "Per-Supplier Detail" in out
    assert "Prio A" in out
    assert "Supplier 0" in out
    assert "Supplier 1" in out


def test_per_supplier_detail_mixed_keeps_only_prioritisations():
    screening = _screening_source("s1", "Screening only")
    prioritisation = _prioritisation_source("p1", "Prio mix")
    out = _render_per_supplier_detail(_state(), [screening, prioritisation])
    assert "Per-Supplier Detail" in out
    # Screening source name should not appear in this section.
    assert "Screening only" not in out
    assert "Prio mix" in out


# ---------------------------------------------------------------------------
# M-P11.2-FIX — pillar block gates verbal summary on full coverage
# ---------------------------------------------------------------------------

def test_pillar_block_full_19_renders_verbal_summary_paragraphs():
    src = _screening_source(name="Full screening")
    fake = SimpleNamespace(
        overview="ov-text",
        air="air-text",
        ghg="ghg-text",
        nature="nat-text",
    )
    with patch.object(
        p11_sections, "generate_verbal_summary", return_value=fake,
    ) as mock_vs:
        out = _render_source_pillar_block(src)
    mock_vs.assert_called_once()
    for snippet in ("ov-text", "air-text", "ghg-text", "nat-text"):
        assert snippet in out
    assert "Partial coverage" not in out


def test_pillar_block_subset_screening_renders_caveat_and_table():
    src = _screening_source(
        name="Partial screening",
        indicators=["air.no2.score"],
    )
    with patch.object(
        p11_sections, "generate_verbal_summary",
    ) as mock_vs:
        out = _render_source_pillar_block(src)
    mock_vs.assert_not_called()
    assert "Partial coverage" in out
    assert "1 of 19 indicators" in out
    # Pillar score table appears.
    assert "Air Pollution" in out
    assert "Composite" in out


def test_pillar_block_prioritisation_source_renders_redirect_caveat():
    src = _prioritisation_source(name="Prio source")
    with patch.object(
        p11_sections, "generate_verbal_summary",
    ) as mock_vs:
        out = _render_source_pillar_block(src)
    mock_vs.assert_not_called()
    assert "prioritisation source" in out
    assert "Priority Findings" in out


def test_pillar_block_empty_screening_setup_treated_as_partial():
    # Defensive: missing screening_setup → empty indicator set → caveat.
    src = {
        "id":      "x",
        "name":    "No setup",
        "type":    "screening",
        "payload": {"composite.overall_screening": 0.4},
    }
    with patch.object(
        p11_sections, "generate_verbal_summary",
    ) as mock_vs:
        out = _render_source_pillar_block(src)
    mock_vs.assert_not_called()
    assert "Partial coverage" in out
    assert "0 of 19" in out


# ---------------------------------------------------------------------------
# M-P11-FIX — indicator_detail skips partial-coverage screening sources
# ---------------------------------------------------------------------------

def test_indicator_detail_only_partial_screenings_returns_empty():
    partial = _screening_source("p1", "Partial", indicators=["air.no2.score"])
    out = _render_indicator_detail(_state(), [partial])
    assert out == ""


def test_indicator_detail_full_screening_renders_normally():
    full = _screening_source("f1", "Full screening")
    out = _render_indicator_detail(_state(), [full])
    assert "Indicator Detail" in out
    assert "Full screening" in out
    # Pillar score block rendered.
    assert "Air Pollution" in out
    assert "Composite" in out


def test_indicator_detail_mixed_partial_and_full_keeps_only_full():
    partial = _screening_source("p1", "Partial", indicators=["air.no2.score"])
    full    = _screening_source("f1", "Full")
    out = _render_indicator_detail(_state(), [partial, full])
    assert "Indicator Detail" in out
    assert "Full" in out
    assert "Partial" not in out


def test_indicator_detail_prioritisation_renders_normally():
    prio = _prioritisation_source(name="Prio detail")
    out = _render_indicator_detail(_state(), [prio])
    assert "Indicator Detail" in out
    assert "Prio detail" in out


def test_indicator_detail_partial_plus_prioritisation_keeps_only_prio():
    partial = _screening_source("p1", "Partial",
                                indicators=["air.no2.score"])
    prio    = _prioritisation_source("pr1", "Prio kept")
    out = _render_indicator_detail(_state(), [partial, prio])
    assert "Indicator Detail" in out
    assert "Prio kept" in out
    assert "Partial" not in out
