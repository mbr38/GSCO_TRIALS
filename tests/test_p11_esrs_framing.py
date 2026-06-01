"""Tests for the M-REPORT-A1 ESRS framing layer + dual-framed General report.

Exercises the assembler end-to-end so the RenderContext threading, the ESRS
topical grouping (RT6), scope-honesty out-of-scope stubs (RT4), the General
report's dual framing (RT8), and pillar filtering (RT5) are all covered.

Pure-Python: no Streamlit, no Earth Engine — synthetic payloads only.
"""

# M-REPORT-A1
from __future__ import annotations

from types import SimpleNamespace

from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_assembler import build_report_html
from ui.components.p11_esrs import datapoint_label, esrs_code
from ui.components.p11_sections import RenderContext
from ui.components.p11_templates import get_template


def _payload():
    return {
        "air.audit_followup_priority": 0.72,
        "ghg.audit_followup_priority": 0.20,
        "nature.followup_priority":    0.45,
        "composite.overall_screening": 0.50,
        "nature.forest_loss.pct":      2.34,
        "ghg.co2.mean":                12450,
        "ghg.ch4.site":                1901.0,
        "_provenance.air.no2": {
            "asset_id": "COPERNICUS/S5P", "native_scale_m": 1000,
            "time_range": ["2026-01-01", "2026-03-01"],
        },
    }


def _full_source():
    return {
        "id": "s1", "name": "Acme Plant", "type": "screening",
        "screening_setup": {
            "indicators": list(ALL_INDICATOR_IDS),
            "centre": {"lat": 1.0, "lon": 2.0}, "radius_km": 5,
            "time_range": ["2026-01-01", "2026-03-01"],
        },
        "payload": _payload(),
    }


def _state(user_type, template_id="general"):
    return SimpleNamespace(title="Q2 audit", notes="Test.",
                           user_type=user_type, template_id=template_id)


def _build(user_type, template_id):
    return build_report_html(_state(user_type, template_id),
                             [_full_source()], get_template(template_id))


def _body(html: str) -> str:
    """The report body with the glossary appendix stripped, so substring
    assertions don't trip over glossary term labels/definitions."""
    return html.split("<section class='chapter-break glossary'>")[0]


# ---------------------------------------------------------------------------
# RenderContext.from_template — the dual-framing decision (RT8)
# ---------------------------------------------------------------------------

def test_general_esrs_only_for_mnc():
    g = get_template("general")
    assert RenderContext.from_template(g, "mnc").apply_esrs is True
    assert RenderContext.from_template(g, "policy_maker").apply_esrs is False


def test_pillar_template_context_is_single_pillar_and_esrs():
    ctx = RenderContext.from_template(get_template("mnc_air"), "mnc")
    assert ctx.pillars == frozenset({"air"})
    assert ctx.apply_esrs is True


def test_trend_template_never_esrs():
    ctx = RenderContext.from_template(get_template("trend"), "mnc")
    assert ctx.apply_esrs is False


# ---------------------------------------------------------------------------
# General report dual framing (RT8)
# ---------------------------------------------------------------------------

def test_mnc_general_is_esrs_framed():
    body = _body(_build("mnc", "general"))
    assert "ESRS E1 — Climate change" in body
    assert "ESRS E2 — Pollution" in body
    assert "ESRS E4 — Biodiversity and ecosystems" in body
    assert "metrics &amp; evidence" in body
    assert "out of scope" in body.lower()


def test_policy_general_strips_esrs():
    body = _body(_build("policy_maker", "general"))
    assert "ESRS E1" not in body
    assert "ESRS E2" not in body
    assert "out of scope" not in body.lower()
    # Same body still renders the plain pillar findings.
    assert "Pillar Findings" in body


def test_dual_framing_keys_off_user_type_not_template_id():
    # Same template_id, different user_type → different framing.
    mnc = _body(_build("mnc", "general"))
    pol = _body(_build("policy_maker", "general"))
    assert ("ESRS E2" in mnc) and ("ESRS E2" not in pol)


# ---------------------------------------------------------------------------
# Pillar-specific MNC reports (RT5/RT6)
# ---------------------------------------------------------------------------

def test_air_report_shows_only_e2():
    body = _body(_build("mnc", "mnc_air"))
    assert "ESRS E2 — Pollution" in body
    assert "ESRS E1" not in body
    assert "ESRS E4" not in body


def test_ghg_report_shows_only_e1_and_keeps_reference_datasets():
    body = _body(_build("mnc", "mnc_ghg"))
    assert "ESRS E1 — Climate change" in body
    assert "ESRS E2" not in body
    # ODIAC/CH4 reference rows belong to GHG; Hansen (nature) is filtered out.
    assert "<h2>Reference datasets</h2>" in body
    assert "ODIAC CO" in body
    assert "Hansen forest loss" not in body


def test_air_report_omits_reference_datasets_section():
    # Air (E2) owns no reference datasets — section omits entirely.
    body = _body(_build("mnc", "mnc_air"))
    assert "<h2>Reference datasets</h2>" not in body


def test_nature_report_shows_only_e4_and_hansen():
    body = _body(_build("mnc", "mnc_nature"))
    assert "ESRS E4 — Biodiversity and ecosystems" in body
    assert "Hansen forest loss" in body
    assert "ODIAC CO" not in body


# ---------------------------------------------------------------------------
# Scope honesty (RT4) + datapoint deferral (Step A §8.4)
# ---------------------------------------------------------------------------

def test_out_of_scope_stub_present_for_each_topic():
    body = _body(_build("mnc", "general"))
    # One stub per pillar (3) — policies/actions/targets are the company's.
    assert body.count("class='oos-tag'") == 3
    assert "produces the environmental-screening metrics" in body


def test_esrs_code_mapping():
    assert esrs_code("air") == "E2"
    assert esrs_code("ghg") == "E1"
    assert esrs_code("nature") == "E4"


def test_datapoint_label_deferred():
    # Step A §8.4: codes not in project docs yet — hook returns None.
    assert datapoint_label("air.no2.score") is None


# ---------------------------------------------------------------------------
# Glossary presence on every report (RT12)
# ---------------------------------------------------------------------------

def test_every_built_report_carries_glossary():
    for tid in ("general", "mnc_ghg", "mnc_air", "mnc_nature"):
        out = _build("mnc", tid)
        assert "<h2>Glossary</h2>" in out


def test_esrs_glossary_term_only_in_mnc_general():
    # MNC general is ESRS-framed → the report text contains "ESRS …" → the
    # glossary defines it. The policy variant strips ESRS → no such term.
    assert "EU disclosure standards" in _build("mnc", "general")
    assert "EU disclosure standards" not in _build("policy_maker", "general")
