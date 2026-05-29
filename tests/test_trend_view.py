"""Tests for the M-TREND-A2 per-indicator trend view, save, and report section.

Pure-layer coverage (no Streamlit render, no Earth Engine): series-eligibility
gating, the verdict grammar across all bucket states, the UT5 badge-zoom
invariant, the inline-SVG builder, the saved-record schema + search, the EE
adapter's non-series guard, and the P-11 trend report section incl. its
graceful SVG-failure fallback.
"""

from __future__ import annotations

import pytest

from engine.core.trend import base_indicator_id, is_series_indicator
from ui.components.p11_sections import get_section
from ui.components.p11_templates import get_template
from ui.components.trend_compute import compute_trend_for_indicator
from ui.components.trend_record import (
    make_trend_entry,
    significance_text,
    slope_display,
    trend_search_indicator,
    verdict_badge,
)
from ui.components.trend_svg import build_trend_svg, season_regime
from ui.p11_state import ReportState


def _result(**over) -> dict:
    base = {
        "indicator_id": "air.no2",
        "trend": 1.2e-5,
        "trend_p": 0.02,
        "trend_severity": 0.4,
        "trend_confidence": 0.55,
        "significance_bucket": "significant",
        "seasonal_flag": False,
        "series": [
            ["2025-01-01", 1.0], ["2025-02-01", 1.1], ["2025-03-01", 1.3],
            ["2025-04-01", 1.5], ["2025-05-01", 1.6],
        ],
        "coverage": {"n_valid_days": 5, "span_days": 120, "largest_gap_days": 31},
        "provenance": {},
    }
    base.update(over)
    return base


# ---------------------------------------------------------------------------
# Series-eligibility (UT7)
# ---------------------------------------------------------------------------

class TestSeriesEligibility:
    @pytest.mark.parametrize("sid", [
        "air.no2.score", "air.aod.z", "ghg.ch4.score", "ghg.viirs.score",
        "nature.ndvi.score", "nature.ndvi",
    ])
    def test_series_indicators_eligible(self, sid) -> None:
        assert is_series_indicator(sid) is True

    @pytest.mark.parametrize("sid", [
        "ghg.co2.mean", "nature.kba.dist_km", "nature.dw.dominant_class",
        "nature.forest_loss.pct", "nature.habitat.conversion_score", None, "",
    ])
    def test_non_series_indicators_excluded(self, sid) -> None:
        assert is_series_indicator(sid) is False

    def test_base_id_normalisation(self) -> None:
        assert base_indicator_id("air.no2.score") == "air.no2"
        assert base_indicator_id("nature.ndvi") == "nature.ndvi"

    def test_adapter_rejects_non_series(self) -> None:
        # Guards before any EE work — a ValueError, not an EE call.
        with pytest.raises(ValueError):
            compute_trend_for_indicator(
                "ghg.co2.mean",
                {"centre": {"lat": 0, "lon": 0}, "radius_km": 5,
                 "time_range": ["2025-01-01", "2025-04-01"]},
                {},
            )


# ---------------------------------------------------------------------------
# Verdict badge (UT6) + zoom invariant (UT5)
# ---------------------------------------------------------------------------

class TestVerdictBadge:
    def test_rising_significant(self) -> None:
        b = verdict_badge(_result(trend=1.0, significance_bucket="significant"))
        assert b["tone"] == "rising"
        assert "Rising" in b["text"] and "significant" in b["text"]

    def test_falling_weak(self) -> None:
        b = verdict_badge(_result(trend=-1.0, significance_bucket="weak_emerging"))
        assert b["tone"] == "falling"
        assert "Falling" in b["text"] and "weak" in b["text"]

    def test_none_bucket(self) -> None:
        b = verdict_badge(_result(trend=0.5, significance_bucket="none"))
        assert b["tone"] == "none"
        assert "No significant trend" in b["text"]

    def test_unavailable(self) -> None:
        b = verdict_badge(_result(
            trend=None, trend_p=None, significance_bucket="unavailable",
            coverage={"n_valid_days": 2, "span_days": 30, "largest_gap_days": 20},
        ))
        assert b["tone"] == "unavailable"
        assert "unavailable" in b["text"].lower() and "N=2" in b["text"]

    def test_seasonal_caveat_appended(self) -> None:
        b = verdict_badge(_result(seasonal_flag=True))
        assert "possibly seasonal" in b["text"]
        b2 = verdict_badge(_result(seasonal_flag=False))
        assert "possibly seasonal" not in b2["text"]

    def test_badge_is_pure_function_of_result(self) -> None:
        # UT5 invariant: the badge derives from the computed statistics only,
        # so it cannot change under any view-side overlay/zoom state (there is
        # no view input to the function). Same result → identical badge.
        r = _result()
        assert verdict_badge(r) == verdict_badge(dict(r))


class TestMetricsText:
    def test_significance_text(self) -> None:
        assert "significant" in significance_text(_result(significance_bucket="significant"))
        assert significance_text(_result(significance_bucket="unavailable")) == "unavailable"

    def test_slope_display(self) -> None:
        assert "/yr" in slope_display(_result(trend=1.2))
        assert slope_display(_result(trend=None)) == "—"


# ---------------------------------------------------------------------------
# SVG builder (UT2/UT3/UT4)
# ---------------------------------------------------------------------------

class TestTrendSvg:
    # The Theil-Sen line is the only red (#dc2626) stroke; gridlines/frame use
    # other colours, so we key the line's presence on its colour.
    _TREND_STROKE = 'stroke="#dc2626"'

    def test_renders_scatter_and_line(self) -> None:
        svg = build_trend_svg(_result())
        assert svg.startswith("<svg")
        assert "<circle" in svg                 # scatter
        assert self._TREND_STROKE in svg        # Theil-Sen line

    def test_unavailable_has_scatter_no_line(self) -> None:
        svg = build_trend_svg(_result(trend=None, significance_bucket="unavailable"))
        assert "<circle" in svg
        # No Theil-Sen line when slope is None (gridlines may still be <line>).
        assert self._TREND_STROKE not in svg

    def test_empty_series_renders_placeholder(self) -> None:
        svg = build_trend_svg(_result(series=[]))
        assert svg.startswith("<svg")
        assert "No observations" in svg

    def test_season_bands_only_temperate(self) -> None:
        temperate = build_trend_svg(_result(), lat=52.0, show_season_bands=True)
        tropical = build_trend_svg(_result(), lat=2.0, show_season_bands=True)
        # Season labels (e.g. Winter/Summer) appear for temperate, not tropical.
        assert any(s in temperate for s in ("Winter", "Spring", "Summer", "Autumn"))
        assert not any(s in tropical for s in ("Winter", "Spring", "Summer", "Autumn"))

    def test_season_regime_classification(self) -> None:
        assert season_regime(52.0) == "n_temperate"
        assert season_regime(-40.0) == "s_temperate"
        assert season_regime(5.0) == "tropical"
        assert season_regime(None) == "unknown"

    def test_overlays_add_elements(self) -> None:
        base = build_trend_svg(_result())
        cov = build_trend_svg(_result(), show_coverage_strip=True)
        assert "coverage" in cov and "coverage" not in base


# ---------------------------------------------------------------------------
# Saved record (UT9)
# ---------------------------------------------------------------------------

class TestSavedRecord:
    def test_make_trend_entry_schema(self) -> None:
        entry = make_trend_entry(
            entry_id="abc", name="Trend · NO₂ · Plant",
            indicator_id="air.no2", display_name="Nitrogen Dioxide",
            screening_setup={"centre": {"lat": 1.0, "lon": 2.0}},
            result=_result(), date_saved_iso="2026-05-29T00:00:00+00:00",
        )
        assert entry["type"] == "trend"
        assert entry["indicator_id"] == "air.no2"
        # The per-day series is persisted (load-bearing for re-open + report).
        assert entry["trend_result"]["series"] == _result()["series"]
        assert entry["screening_setup"]["centre"]["lat"] == 1.0

    def test_search_indicator_field(self) -> None:
        entry = make_trend_entry(
            entry_id="abc", name="n", indicator_id="air.no2",
            display_name="Nitrogen Dioxide", screening_setup={},
            result=_result(), date_saved_iso="x",
        )
        s = trend_search_indicator(entry)
        assert "air.no2" in s and "Nitrogen Dioxide" in s
        # Empty for non-trend records.
        assert trend_search_indicator({"type": "screening"}) == ""

    def test_p10_search_matches_trend_indicator(self) -> None:
        from ui.components.p10_list import _matches_search
        entry = make_trend_entry(
            entry_id="abc", name="Trend A", indicator_id="air.no2",
            display_name="Nitrogen Dioxide", screening_setup={},
            result=_result(), date_saved_iso="x",
        )
        assert _matches_search(entry, "nitrogen") is True
        assert _matches_search(entry, "air.no2") is True
        assert _matches_search(entry, "methane") is False


# ---------------------------------------------------------------------------
# P-11 report section (UT10)
# ---------------------------------------------------------------------------

class TestReportSection:
    def _trend_source(self, result=None):
        return {
            "id": "t1", "name": "Trend NO₂", "type": "trend",
            "indicator_id": "air.no2", "display_name": "Nitrogen Dioxide",
            "screening_setup": {"centre": {"lat": 52.0, "lon": 0.0}},
            "trend_result": result or _result(),
        }

    def test_emits_svg_and_verdict(self) -> None:
        fn = get_section("trend_graph")
        frag = fn(ReportState(), [self._trend_source()])
        assert "<svg" in frag
        assert "Rising" in frag

    def test_empty_when_no_trend_sources(self) -> None:
        fn = get_section("trend_graph")
        assert fn(ReportState(), [{"type": "screening", "payload": {}}]) == ""

    def test_fallback_table_on_svg_failure(self) -> None:
        fn = get_section("trend_graph")
        # A non-ISO date in the series makes build_trend_svg raise; the
        # section must degrade to the series table, never a broken section.
        bad = _result(series=[["not-a-date", 1.0], ["also-bad", 2.0]])
        frag = fn(ReportState(), [self._trend_source(bad)])
        assert "series-table" in frag
        assert "Rising" in frag  # verdict still rendered

    def test_registered_in_templates(self) -> None:
        for tid in ("policy_audit", "supplier_audit"):
            tpl = get_template(tid)
            assert "trend" in tpl.accepted_source_types
            assert "trend_graph" in tpl.sections
