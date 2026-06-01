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


def test_pdf_appendix_renders_only_audit_transparency_keys():
    """M-UI-A1-SURFACE Sub-milestone 3 polish (24 May 2026) — the PDF
    extras section is gated to ``_PDF_AUDIT_TRANSPARENCY_KEYS``
    (n_valid_dates + granule_count). Engineering calibration
    parameters like aod_qa_bit_mask / lookback_years / placeholder /
    distance_decay_km belong in the CSV, NOT the PDF appendix.
    """
    extra = {
        "_provenance.air.aod": {
            "asset_id":       "MODIS/061/MCD19A2_GRANULES",
            "native_scale_m": 1000.0,
            "time_range":     ("2026-02-22", "2026-05-23"),
            "extra": {
                # In allowlist — these surface.
                "n_valid_dates":   64,
                "granule_count":   3712,
                # NOT in allowlist — engineering noise, must be hidden.
                "aod_qa_bit_mask": "0xF00",
                "lookback_years":   5,
                "placeholder":      "ignored",
                # confidence_terms also still hidden (P-05 owns that surface).
                "confidence_terms": {
                    "qa": 0.90, "n_valid": 1.0,
                    "anomaly_strength": 0.0, "spatial_context": 1.0,
                    "column_to_surface_uncertainty": "n_a",
                },
            },
        },
    }
    src = _screening_source(extra_payload=extra)
    out = _render_provenance_appendix(_state(), [src])
    # The audit-transparency story is rendered as English prose.
    assert "distinct dates observed"        in out
    assert "raw images"                     in out
    # Both numbers surface (with thousands separators for readability).
    assert "64"    in out
    assert "3,712" in out
    # Engineering calibration parameters MUST NOT leak into the PDF.
    assert "aod_qa_bit_mask" not in out
    assert "0xF00"           not in out
    assert "lookback_years"  not in out
    assert "placeholder"     not in out
    # confidence_terms and inner term keys still excluded — P-05 owns that.
    assert "confidence_terms" not in out
    assert "anomaly_strength" not in out


def test_pdf_appendix_omits_single_swath_indicators():
    """Indicators where ``granule_count == n_valid_dates`` (single-
    image-per-day: NO2, SO2, CO, HCHO, O3, AAI, PM2.5, PM10, NDVI,
    VIIRS) have no multi-swath story and are omitted from the bullet
    list. Only multi-swath divergence (AOD, CH4) surfaces."""
    extra = {
        # Single-swath: granule_count == n_valid_dates — must be omitted.
        "_provenance.air.no2": {
            "asset_id": "COPERNICUS/S5P/OFFL/L3_NO2",
            "extra": {"n_valid_dates": 72, "granule_count": 72},
        },
        # Multi-swath: granule_count >> n_valid_dates — must surface.
        "_provenance.air.aod": {
            "asset_id": "MODIS/061/MCD19A2_GRANULES",
            "extra": {"n_valid_dates": 64, "granule_count": 3712},
        },
    }
    src = _screening_source(extra_payload=extra)
    out = _render_provenance_appendix(_state(), [src])
    assert "air.aod" in out
    # NO2 is intentionally omitted from the audit-transparency bullet
    # list (it still appears in the main provenance table above — the
    # assertion below scopes to the audit-transparency block).
    extras_block_start = out.find("Audit-transparency extras")
    assert extras_block_start != -1
    extras_block = out[extras_block_start:]
    assert "air.no2" not in extras_block


def test_pdf_appendix_omits_section_entirely_when_no_multi_swath():
    """Graceful degradation: when every indicator has
    ``granule_count == n_valid_dates`` (or no extras at all, like
    pre-engine-fix payloads), the entire 'Audit-transparency extras'
    heading is omitted. No dangling empty section."""
    extra = {
        # Single-swath indicator (no multi-swath story).
        "_provenance.air.no2": {
            "asset_id": "X",
            "extra":    {"n_valid_dates": 72, "granule_count": 72},
        },
        # Pre-engine-fix shape — no n_valid_dates / granule_count at all.
        "_provenance.nature.kba": {
            "asset_id": "Y",
            "extra":    {"confidence_terms": {"qa": 1.0}},
        },
    }
    src = _screening_source(extra_payload=extra)
    out = _render_provenance_appendix(_state(), [src])
    assert "Audit-transparency extras" not in out


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


def test_indicator_detail_full_screening_renders_per_indicator_table():
    # M-REPORT-A1.1 RF3: Indicator Detail is now the per-indicator deep table
    # (site / background / z-score / anomaly frequency / confidence /
    # attributability), not the pillar score block.
    full = _screening_source("f1", "Full screening")
    out = _render_indicator_detail(_state(), [full])
    assert "Indicator Detail" in out
    assert "z-score" in out          # deep-table column header
    assert "Attributability" in out
    assert "NO₂" in out              # an indicator display name (air pillar)
    # RF3: pillar-summary / composite rows no longer duplicated here.
    assert "Composite" not in out
    # RF2: single source → source sub-header suppressed (named in scope/exec).
    assert "<h3>Full screening</h3>" not in out


def test_indicator_detail_mixed_partial_and_full_keeps_only_full():
    partial = _screening_source("p1", "Partial", indicators=["air.no2.score"])
    full    = _screening_source("f1", "Full")
    out = _render_indicator_detail(_state(), [partial, full])
    assert "Indicator Detail" in out
    # Only the full-coverage screening contributes; the partial is skipped.
    assert "Partial" not in out


def test_indicator_detail_prioritisation_only_returns_empty():
    # RF3: Indicator Detail is screening-only — prioritisation sources carry no
    # single per-AOI payload and are covered by Per-Supplier Detail.
    prio = _prioritisation_source(name="Prio detail")
    out = _render_indicator_detail(_state(), [prio])
    assert out == ""


def test_indicator_detail_partial_plus_prioritisation_returns_empty():
    partial = _screening_source("p1", "Partial",
                                indicators=["air.no2.score"])
    prio    = _prioritisation_source("pr1", "Prio kept")
    out = _render_indicator_detail(_state(), [partial, prio])
    assert out == ""
