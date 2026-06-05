"""Tests for the supplier cooperation report (M-REPORT-COOP).

Pure-Python — no Streamlit. Covers the new template's presence, its single
user-chosen-pillar scoping, the reuse of the verbal-summary prose / dominant-
contributor resolution / canonical screening-not-determination language, and
the deliberate exclusions (no cross-supplier ranking, confidence payload,
provenance appendix, or ESRS codes).
"""

# M-REPORT-COOP
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from ui.components import p11_sections
from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_assembler import build_report_html
from ui.components.p11_sections import (
    RenderContext,
    _render_cooperation_finding,
    _render_cooperation_framing,
    _render_cooperation_improvement,
    _render_cooperation_title,
    highest_priority_pillar,
)
from ui.components.p11_templates import ALL_PILLARS, get_template
from ui.p11_state import ReportState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(title="Carajás cooperation report", notes=""):
    return SimpleNamespace(title=title, notes=notes)


def _nature_led_source(sid="caraj-1", name="Carajás mine site"):
    """A full-19 screening source whose Nature pillar leads (Carajás-like)."""
    payload = {
        "air.audit_followup_priority":  0.18,
        "ghg.audit_followup_priority":  0.30,
        "nature.followup_priority":     0.91,
        "composite.overall_screening":  0.46,
    }
    return {
        "id":   sid,
        "name": name,
        "type": "screening",
        "screening_setup": {
            "centre":     {"lat": -6.07, "lon": -50.16},
            "radius_km":  10,
            "time_range": ["2025-01-01", "2025-06-01"],
            "indicators": list(ALL_INDICATOR_IDS),
        },
        "payload": payload,
    }


def _coop_ctx(pillar="nature"):
    return RenderContext(
        pillars=frozenset({pillar}), template_id="supplier_cooperation",
    )


def _fake_verbal():
    return SimpleNamespace(
        overview="overview-text",
        air="AIR-PROSE",
        ghg="GHG-PROSE",
        nature="NATURE-PROSE",
    )


# ---------------------------------------------------------------------------
# highest_priority_pillar — the S1 default
# ---------------------------------------------------------------------------

def test_highest_priority_pillar_picks_max():
    assert highest_priority_pillar(_nature_led_source()["payload"]) == "nature"


def test_highest_priority_pillar_ties_favour_earliest_in_order():
    payload = {
        "air.audit_followup_priority": 0.5,
        "ghg.audit_followup_priority": 0.5,
        "nature.followup_priority":    0.5,
    }
    assert highest_priority_pillar(payload) == "air"


def test_highest_priority_pillar_empty_payload_defaults_to_air():
    assert highest_priority_pillar({}) == "air"


# ---------------------------------------------------------------------------
# RenderContext narrowing — only the cooperation template honours the pillar
# ---------------------------------------------------------------------------

def test_context_narrows_pillar_for_cooperation_template():
    t = get_template("supplier_cooperation")
    ctx = RenderContext.from_template(t, "mnc", pillar="nature")
    assert ctx.pillars == frozenset({"nature"})
    assert ctx.apply_esrs is False  # never ESRS-framed, even for an MNC


def test_context_ignores_pillar_for_other_templates():
    """A stale pillar must not narrow a fixed-pillar / all-pillar report."""
    general = RenderContext.from_template(get_template("general"), "mnc", pillar="nature")
    assert general.pillars == ALL_PILLARS


# ---------------------------------------------------------------------------
# Single-pillar scoping — the finding uses ONLY the chosen pillar's prose
# ---------------------------------------------------------------------------

def test_cooperation_finding_uses_only_chosen_pillar_prose():
    src = _nature_led_source()
    with patch.object(p11_sections, "generate_verbal_summary",
                      return_value=_fake_verbal()):
        out = _render_cooperation_finding(_state(), [src], _coop_ctx("nature"))
    assert "NATURE-PROSE" in out
    assert "AIR-PROSE" not in out
    assert "GHG-PROSE" not in out


def test_cooperation_finding_includes_headline_score_table():
    """The finding grounds the prose in the pillar's score table (like the
    other reports), not prose alone."""
    src = _nature_led_source()
    with patch.object(p11_sections, "generate_verbal_summary",
                      return_value=_fake_verbal()):
        out = _render_cooperation_finding(_state(), [src], _coop_ctx("nature"))
    assert "NATURE-PROSE" in out          # prose
    assert "Follow-up priority" in out    # + the headline score table
    assert "Nature/Land" in out


def test_cooperation_finding_respects_a_different_chosen_pillar():
    src = _nature_led_source()
    with patch.object(p11_sections, "generate_verbal_summary",
                      return_value=_fake_verbal()):
        out = _render_cooperation_finding(_state(), [src], _coop_ctx("air"))
    assert "AIR-PROSE" in out
    assert "NATURE-PROSE" not in out


def test_cooperation_finding_partial_coverage_falls_back_to_score():
    src = _nature_led_source()
    src["screening_setup"]["indicators"] = ["air.no2.score"]  # not full-19
    out = _render_cooperation_finding(_state(), [src], _coop_ctx("nature"))
    assert "full" in out.lower()           # the partial-coverage note
    assert "Nature/Land" in out            # headline score table for the pillar


# ---------------------------------------------------------------------------
# Improvement area — names the dominant contributor, collaboratively
# ---------------------------------------------------------------------------

def test_cooperation_improvement_names_dominant_driver():
    src = _nature_led_source()
    with patch.object(
        p11_sections, "dominant_contributor",
        return_value=("nature.habitat.conversion_score", "habitat conversion"),
    ):
        out = _render_cooperation_improvement(_state(), [src], _coop_ctx("nature"))
    assert "habitat conversion" in out
    assert "where attention would matter most" in out


def test_cooperation_improvement_lists_underlying_indicator_and_meaning():
    """Names the concrete indicator behind the driver + a brief meaning,
    reused from the indicator library."""
    src = _nature_led_source()
    with patch.object(
        p11_sections, "dominant_contributor",
        return_value=("nature.vegetation_condition", "vegetation condition"),
    ):
        out = _render_cooperation_improvement(_state(), [src], _coop_ctx("nature"))
    assert "The measurement behind this" in out
    # The reused indicator-library brief for NDVI (bold title + meaning).
    assert "NDVI" in out
    assert "plant health" in out


def test_cooperation_improvement_combustion_proxy_lists_two_indicators():
    src = _nature_led_source()
    with patch.object(
        p11_sections, "dominant_contributor",
        return_value=("ghg.combustion_proxy", "combustion proxy (NO₂ + CO)"),
    ):
        out = _render_cooperation_improvement(_state(), [src], _coop_ctx("ghg"))
    assert "The measurements behind this" in out  # plural — two indicators
    assert "Nitrogen Dioxide" in out
    assert "Carbon Monoxide" in out


def test_cooperation_improvement_handles_no_dominant_driver():
    src = _nature_led_source()
    with patch.object(p11_sections, "dominant_contributor", return_value=None):
        out = _render_cooperation_improvement(_state(), [src], _coop_ctx("nature"))
    assert "no single measure dominates" in out.lower()


# ---------------------------------------------------------------------------
# Framing — reuses the canonical screening-not-determination language
# ---------------------------------------------------------------------------

def test_cooperation_framing_reuses_canonical_attributability_language():
    out = _render_cooperation_framing(_state(), [_nature_led_source()], _coop_ctx())
    # Canonical core (shared with the methodology section).
    assert p11_sections.ATTRIBUTABILITY_FRAMING_CORE_HTML in out
    assert "relative to its surrounding region" in out


def test_cooperation_framing_is_collaborative_not_a_determination():
    out = _render_cooperation_framing(_state(), [_nature_led_source()], _coop_ctx())
    assert "starting point for a conversation" in out
    assert "not a determination of cause or compliance" in out


# ---------------------------------------------------------------------------
# Title — supplier + screening window
# ---------------------------------------------------------------------------

def test_cooperation_title_shows_supplier_and_window():
    out = _render_cooperation_title(_state(), [_nature_led_source()], _coop_ctx())
    assert "Supplier cooperation report" in out
    assert "Carajás mine site" in out
    assert "2025-01-01 → 2025-06-01" in out


# ---------------------------------------------------------------------------
# Full assembly — single-pillar body, audit machinery excluded
# ---------------------------------------------------------------------------

def test_build_report_html_cooperation_is_single_pillar_and_excludes_audit():
    template = get_template("supplier_cooperation")
    state = ReportState(
        template_id="supplier_cooperation",
        source_ids=["caraj-1"],
        title="Carajás cooperation report",
        user_type="mnc",
        pillar="nature",
    )
    src = _nature_led_source()
    with patch.object(p11_sections, "generate_verbal_summary",
                      return_value=_fake_verbal()):
        html_out = build_report_html(state, [src], template)

    # Single-pillar: only the chosen pillar's prose appears.
    assert "NATURE-PROSE" in html_out
    assert "AIR-PROSE" not in html_out
    assert "GHG-PROSE" not in html_out

    # Collaborative framing + glossary present.
    assert "Supplier cooperation report" in html_out
    assert "starting point for a conversation" in html_out
    assert "Glossary" in html_out

    # Deliberately excluded machinery is absent. (The shared shell stylesheet
    # carries .esrs-* CSS classes, so we assert no ESRS *content* renders —
    # topical headings / codes — rather than the bare token.)
    assert "Provenance" not in html_out
    assert "Findings by ESRS topic" not in html_out
    assert "ESRS E1" not in html_out
    assert "ESRS E2" not in html_out
    assert "ESRS E4" not in html_out
    assert "Composite score methodology" not in html_out
    assert "Executive Summary" not in html_out
