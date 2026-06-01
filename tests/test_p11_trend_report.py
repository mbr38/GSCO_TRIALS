"""Tests for the M-REPORT-A1 Trend report (Option A, §5 / RT9-RT11).

Per-indicator structure grouped under pillar headers, no composite, not
ESRS-framed. Pure-Python: trend records carry the saved per-day series so the
report renders without recompute (Step A §8.3).
"""

# M-REPORT-A1
from __future__ import annotations

from types import SimpleNamespace

from ui.components.p11_assembler import build_report_html
from ui.components.p11_sections import _render_trend_indicator_sections
from ui.components.p11_templates import get_template


def _trend_result(slope=1.5e-5):
    return {
        "trend": slope,
        "trend_p": 0.012,
        "significance_bucket": "significant",
        "seasonal_flag": False,
        "trend_confidence": 0.81,
        "coverage": {"n_valid_days": 60},
        "series": [["2026-01-01", 1.0], ["2026-02-01", 1.4],
                   ["2026-03-01", 1.9]],
    }


def _trend_source(indicator_id, display, result=None):
    return {
        "id": f"t-{indicator_id}", "name": f"{display} trend", "type": "trend",
        "indicator_id": indicator_id, "display_name": display,
        "trend_result": result or _trend_result(),
        "screening_setup": {"centre": {"lat": 1.0, "lon": 2.0}},
    }


def _state():
    return SimpleNamespace(title="Trend report", notes="", user_type="mnc",
                           template_id="trend")


# ---------------------------------------------------------------------------
# Section-level structure
# ---------------------------------------------------------------------------

def test_indicators_grouped_under_pillar_headers():
    sources = [
        _trend_source("air.no2.site", "NO₂"),
        _trend_source("ghg.ch4.site", "CH₄"),
        _trend_source("nature.ndvi.score", "NDVI"),
    ]
    out = _render_trend_indicator_sections(_state(), sources)
    # Pillar grouping headers (RT10) present, in locked air → ghg → nature order.
    assert out.index("Air Pollution") < out.index("GHG Emissions") < out.index(
        "Nature/Land"
    )
    # Each indicator's own sub-heading + verdict rendered.
    assert "NO₂" in out and "CH₄" in out and "NDVI" in out
    assert "Rising" in out  # verdict badge from the saved series


def test_no_composite_or_pillar_score_in_trend_report():
    out = _render_trend_indicator_sections(
        _state(), [_trend_source("air.no2.site", "NO₂")]
    )
    # RT9/RT10 — pillar headers carry no aggregate score, no composite value.
    # (The intro prose explains there's no composite; that's expected — what
    # must be absent is any actual composite/pillar score artefact.)
    assert "composite.overall_screening" not in out
    assert "Composite (overall)" not in out
    assert "pillar-chip" not in out  # no banded score chips


def test_empty_when_no_trend_sources():
    assert _render_trend_indicator_sections(_state(), []) == ""
    assert _render_trend_indicator_sections(
        _state(), [{"type": "screening", "name": "x"}]
    ) == ""


def test_svg_failure_degrades_to_series_table():
    bad = _trend_result()
    bad["series"] = [["not-a-date", 1.0], ["also-bad", 2.0]]
    out = _render_trend_indicator_sections(
        _state(), [_trend_source("air.no2.site", "NO₂", bad)]
    )
    assert "series-table" in out
    assert "Rising" in out  # verdict still rendered


# ---------------------------------------------------------------------------
# End-to-end via the assembler
# ---------------------------------------------------------------------------

def test_trend_report_builds_and_is_not_esrs_framed():
    sources = [_trend_source("air.no2.site", "NO₂"),
               _trend_source("ghg.ch4.site", "CH₄")]
    out = build_report_html(_state(), sources, get_template("trend"))
    body = out.split("<section class='chapter-break glossary'>")[0]
    assert "Trend analysis" in body
    # RT11 — not ESRS-framed: no topical headings / metrics-&-evidence framing
    # in the rendered body (the shell CSS naming "esrs" is not report content).
    assert "ESRS E1 —" not in body
    assert "ESRS E2 —" not in body
    assert "metrics &amp; evidence" not in body
    assert "out of scope" not in body.lower()
    assert "<h2>Glossary</h2>" in out    # RT12 — glossary still present
    # Trend-specific glossary terms selected (content-aware).
    assert "Theil-Sen slope" in out
    assert "Mann-Kendall test" in out
