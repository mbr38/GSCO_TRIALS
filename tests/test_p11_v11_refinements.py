"""Tests for M-REPORT-A1.1 v1.1 rendering refinements (RF1–RF6).

RF1 cover names the template · RF2 single-source header suppression · RF3
per-indicator deep table · RF4 reference prose · RF5 pillar-pure filtering ·
RF6 inert fallback/adjustment appendices suppressed.

Pure-Python: synthetic payloads, section + assembler calls.
"""

# M-REPORT-A1.1
from __future__ import annotations

from types import SimpleNamespace

from ui.components.p04_indicator_registry import ALL_INDICATOR_IDS
from ui.components.p11_assembler import build_report_html
from ui.components.p11_sections import (
    RenderContext,
    _render_indicator_detail,
    _render_provenance_appendix,
    _render_title_page,
    _report_type_name,
)
from ui.components.p11_templates import get_template


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _full_payload(extra=None):
    p = {
        "air.audit_followup_priority": 0.7, "ghg.audit_followup_priority": 0.5,
        "nature.followup_priority": 0.3, "composite.overall_screening": 0.5,
        # per-indicator values (NO₂ — air; CH₄ — ghg)
        "air.no2.site": 1.2e-4, "air.no2.background": 8.0e-5,
        "air.no2.z": 2.4, "air.no2.hf": 0.42, "air.no2.confidence": 0.81,
        "ghg.ch4.site": 1901.0, "ghg.ch4.background": 1880.0,
        "ghg.ch4.z": 1.1, "ghg.ch4.hf": 0.10, "ghg.ch4.confidence": 0.7,
        "nature.forest_loss.pct": 2.3, "ghg.co2.mean": 12450,
        "_provenance.air.no2": {
            "asset_id": "COPERNICUS/S5P", "native_scale_m": 1000,
            "time_range": ["2026-01-01", "2026-03-01"],
            "extra": {"wind_attributability_state": "low",
                      "ring_land_fraction": 1.0, "land_mask_applied": True},
        },
        "_provenance.ghg.ch4": {
            "asset_id": "COPERNICUS/S5P_CH4", "native_scale_m": 7000,
            "time_range": ["2026-01-01", "2026-03-01"], "extra": {},
        },
        "_provenance.nature.forest_loss": {
            "asset_id": "UMD/hansen", "native_scale_m": 30,
            "time_range": ["2020", "2025"], "extra": {},
        },
    }
    if extra:
        p.update(extra)
    return p


def _source(name="Acme Plant", payload=None):
    return {
        "id": "s1", "name": name, "type": "screening",
        "screening_setup": {
            "indicators": list(ALL_INDICATOR_IDS),
            "centre": {"lat": 1.0, "lon": 2.0}, "radius_km": 5,
            "time_range": ["2026-01-01", "2026-03-01"],
        },
        "payload": payload if payload is not None else _full_payload(),
    }


def _state(user_type="mnc"):
    return SimpleNamespace(title="Q2 audit", notes="", user_type=user_type,
                           template_id="x")


def _build(user_type, template_id, payload=None):
    st = SimpleNamespace(title="Q2 audit", notes="", user_type=user_type,
                         template_id=template_id)
    return build_report_html(st, [_source(payload=payload)],
                             get_template(template_id))


def _body(html: str) -> str:
    return html.split("<section class='chapter-break glossary'>")[0]


# ---------------------------------------------------------------------------
# RF1 — template identity on the cover
# ---------------------------------------------------------------------------

def test_report_type_names():
    assert _report_type_name(RenderContext.from_template(
        get_template("mnc_ghg"), "mnc")) == "ESRS E1 — Climate change report"
    assert _report_type_name(RenderContext.from_template(
        get_template("mnc_air"), "mnc")) == "ESRS E2 — Pollution report"
    assert _report_type_name(RenderContext.from_template(
        get_template("mnc_nature"), "mnc")) == (
        "ESRS E4 — Biodiversity and ecosystems report")
    assert _report_type_name(RenderContext.from_template(
        get_template("general"), "mnc")) == "Environmental screening report"
    assert _report_type_name(RenderContext.from_template(
        get_template("general"), "policy_maker")) == (
        "Environmental screening report")
    assert _report_type_name(RenderContext.from_template(
        get_template("trend"), "mnc")) == "Environmental trend report"


def test_cover_names_the_template():
    ctx = RenderContext.from_template(get_template("mnc_ghg"), "mnc")
    out = _render_title_page(_state(), [_source()], ctx)
    assert "ESRS E1 — Climate change report" in out
    assert "report-type" in out  # styled cover element present


def test_ghg_report_cover_shows_esrs_identity_end_to_end():
    out = _build("mnc", "mnc_ghg")
    # Identity is visible on the cover, before the findings section.
    assert out.index("ESRS E1 — Climate change report") < out.index(
        "Findings by ESRS topic")


# ---------------------------------------------------------------------------
# RF2 — single-source header suppression
# ---------------------------------------------------------------------------

def test_single_source_suppresses_section_subheaders():
    body = _body(_build("mnc", "mnc_ghg"))
    # The per-section "<h3>Acme Plant</h3>" divider is gone for a 1-source report.
    assert "<h3>Acme Plant</h3>" not in body
    # But the source is still named once, in the scope summary.
    assert "Acme Plant" in body


def test_multi_source_keeps_source_dividers():
    st = SimpleNamespace(title="Q2", notes="", user_type="mnc",
                         template_id="general")
    sources = [_source("Plant A"), _source("Plant B")]
    out = build_report_html(st, sources, get_template("general"))
    assert "<h3>Plant A</h3>" in out
    assert "<h3>Plant B</h3>" in out


# ---------------------------------------------------------------------------
# RF3 — per-indicator deep table
# ---------------------------------------------------------------------------

def test_indicator_detail_is_per_indicator_with_six_columns():
    # Use the General report so a z-score indicator (NO₂) is in scope.
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source()], ctx)
    for col in ("Site value", "Background", "z-score", "Anomaly frequency",
                "Confidence", "Attributability"):
        assert col in out
    # NO₂ (z-score grammar) fills the columns; values formatted.
    assert "NO₂" in out
    assert "+2.40" in out          # air.no2.z = 2.4 → "+2.40"
    assert "42%" in out            # air.no2.hf = 0.42 → "42%"


def test_indicator_detail_excludes_reference_datasets():
    # Reference datasets (CH₄ / ODIAC / Hansen) are not scored anomalies — they
    # live in the Reference datasets section, not the Indicator Detail table.
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source()], ctx)
    assert "CH₄" not in out
    assert "ODIAC" not in out
    assert "Forest loss (Hansen)" not in out


def test_ghg_indicator_detail_drops_ch4_and_odiac():
    ctx = RenderContext.from_template(get_template("mnc_ghg"), "mnc")
    out = _render_indicator_detail(_state(), [_source()], ctx)
    # Only the scored GHG indicator (VIIRS) remains; CH₄/ODIAC are reference.
    assert "CH₄" not in out
    assert "ODIAC" not in out


def test_indicator_detail_projects_attributability_state():
    out = _render_indicator_detail(_state(), [_source()],
                                  RenderContext.from_template(
                                      get_template("general"), "mnc"))
    assert "Low" in out            # air.no2 wind_attributability_state = low


def test_findings_and_indicator_detail_no_longer_overlap():
    # Findings carries the pillar narrative + pillar score; Indicator Detail
    # carries the per-indicator table — the bare pillar row isn't duplicated.
    body = _body(_build("mnc", "mnc_ghg"))
    assert "Findings by ESRS topic" in body
    assert "Indicator Detail" in body
    # GHG Indicator Detail uses VIIRS sustained-contrast columns, not z-score.
    assert "Lit-contrast percentile" in body
    assert "Anomaly frequency" not in body  # that's the Air grammar


# ---------------------------------------------------------------------------
# RF4 — reference-datasets prose clarity (no structural change)
# ---------------------------------------------------------------------------

def test_reference_prose_names_each_dataset_role():
    body = _body(_build("mnc", "general"))
    assert "regional_loss_evidence" in body          # Hansen role
    assert "inventory-allocated" in body             # ODIAC role
    assert "raw column reading" in body              # CH₄ role
    assert "not part of the composite score" in body


# ---------------------------------------------------------------------------
# RF5 — pillar-pure filtering across the whole report body
# ---------------------------------------------------------------------------

def test_ghg_report_provenance_is_pillar_pure():
    ctx = RenderContext.from_template(get_template("mnc_ghg"), "mnc")
    out = _render_provenance_appendix(_state(), [_source()], ctx)
    assert "ghg.ch4" in out
    # Air + Nature indicators must NOT appear in a GHG report's provenance.
    assert "air.no2" not in out
    assert "nature.forest_loss" not in out


def test_general_report_provenance_shows_all_pillars():
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_provenance_appendix(_state(), [_source()], ctx)
    assert "air.no2" in out
    assert "ghg.ch4" in out
    assert "nature.forest_loss" in out


def test_air_report_body_excludes_other_pillars_everywhere():
    payload = _full_payload()
    body = _body(_build("mnc", "mnc_air", payload=payload))
    # Provenance appendix is pillar-pure: no ghg/nature indicator ids.
    assert "ghg.ch4" not in body
    assert "nature.forest_loss" not in body
    assert "air.no2" in body


# ---------------------------------------------------------------------------
# RF6 — inert fallback/adjustment appendices suppressed
# ---------------------------------------------------------------------------

def test_coastal_appendix_suppressed_when_mask_did_not_effectively_fire():
    # ring_land_fraction == 1.0 (fully inland) → coastal block must not render.
    payload = _full_payload()
    out = _render_provenance_appendix(
        _state(), [_source(payload=payload)],
        RenderContext.from_template(get_template("general"), "mnc"))
    assert "Coastal AOI handling" not in out


def test_coastal_appendix_suppressed_when_rounds_to_full_land():
    # ring_land_fraction = 0.996 → 100% land / 0% water → mask didn't
    # effectively fire → suppressed (the first-artifact bug, RF6).
    payload = _full_payload()
    payload["_provenance.air.no2"]["extra"]["ring_land_fraction"] = 0.996
    out = _render_provenance_appendix(
        _state(), [_source(payload=payload)],
        RenderContext.from_template(get_template("general"), "mnc"))
    assert "Coastal AOI handling" not in out


def test_coastal_appendix_renders_when_effectively_coastal():
    payload = _full_payload()
    payload["_provenance.air.no2"]["extra"]["ring_land_fraction"] = 0.55
    out = _render_provenance_appendix(
        _state(), [_source(payload=payload)],
        RenderContext.from_template(get_template("general"), "mnc"))
    assert "Coastal AOI handling" in out


def test_fallback_appendix_suppressed_when_no_fallback_fired():
    # No temporal/climatology fallback flags → no fallback block.
    out = _render_provenance_appendix(
        _state(), [_source()],
        RenderContext.from_template(get_template("general"), "mnc"))
    assert "Fallback methodology applied" not in out


# ---------------------------------------------------------------------------
# M-REPORT-A1.1 (cont.) — per-pillar Indicator Detail tables
# ---------------------------------------------------------------------------

def test_indicator_detail_air_uses_zscore_columns():
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source()], ctx)
    assert "Air Pollution" in out          # pillar heading
    for col in ("Site value", "Background", "z-score", "Anomaly frequency"):
        assert col in out
    assert "NO₂" in out and "+2.40" in out and "42%" in out


def test_indicator_detail_air_renders_unit_when_display_unit_present():
    """M-DOCS-CLEANUP-A3 — Site value carries the native unit from
    provenance.extra.display_unit (single source of truth with C5)."""
    payload = _full_payload()
    payload["_provenance.air.no2"]["extra"]["display_unit"] = "µmol/m²"
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source(payload=payload)], ctx)
    assert "µmol/m²" in out


def test_indicator_detail_air_omits_unit_when_dimensionless():
    """AAI/AOD-style dimensionless indicators render the bare value (DC6)."""
    payload = _full_payload()
    payload["_provenance.air.no2"]["extra"]["display_unit"] = "dimensionless"
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source(payload=payload)], ctx)
    # air.no2.site = 1.2e-4 → "0.00012"; no unit suffix appended.
    assert "0.00012" in out
    assert "0.00012 dimensionless" not in out


def test_indicator_detail_ghg_renders_brightness_unit():
    """M-DOCS-CLEANUP-A3 — VIIRS site-brightness cell carries nW/cm²/sr."""
    payload = _full_payload({
        "ghg.viirs.site_brightness": 4.7, "ghg.viirs.lit_contrast_percentile": 88.0,
        "ghg.viirs.flaring_frac": 0.12, "ghg.viirs.ring_lit_pixel_count": 1500,
        "ghg.viirs.confidence": 0.79, "ghg.viirs.attributability_state": "moderate",
        "_provenance.ghg.viirs": {
            "asset_id": "NOAA/VIIRS/001/VNP46A2", "native_scale_m": 500,
            "time_range": ["2026-01-01", "2026-03-01"],
            "extra": {"display_unit": "nW/cm²/sr"},
        },
    })
    ctx = RenderContext.from_template(get_template("mnc_ghg"), "mnc")
    out = _render_indicator_detail(_state(), [_source(payload=payload)], ctx)
    assert "nW/cm²/sr" in out


def test_indicator_detail_ghg_uses_sustained_contrast_columns():
    payload = _full_payload({
        "ghg.viirs.site_brightness": 4.7, "ghg.viirs.lit_contrast_percentile": 88.0,
        "ghg.viirs.flaring_frac": 0.12, "ghg.viirs.ring_lit_pixel_count": 1500,
        "ghg.viirs.confidence": 0.79, "ghg.viirs.attributability_state": "moderate",
    })
    ctx = RenderContext.from_template(get_template("mnc_ghg"), "mnc")
    out = _render_indicator_detail(_state(), [_source(payload=payload)], ctx)
    assert "GHG Emissions" in out
    # VIIRS-native columns, not z-score columns.
    assert "Lit-contrast percentile" in out
    assert "Flaring fraction" in out
    # No z-score / anomaly-frequency *columns* (those are the Air grammar).
    assert "<th>z-score</th>" not in out
    assert "<th>Anomaly frequency</th>" not in out
    assert "Nighttime lights (VIIRS)" in out
    assert "88%" in out                    # lit_contrast_percentile 88.0 → 88%
    assert "12%" in out                    # flaring_frac 0.12 → 12%
    assert "Moderate" in out               # attributability from direct key


def test_indicator_detail_nature_uses_key_metric_column():
    payload = _full_payload({
        "nature.kba.dist_km": 12.3, "nature.kba.overlap_pct": 0.0,
        "nature.kba.confidence": 1.0,
        "nature.habitat.natural_loss_ha": 45.0, "nature.habitat.natural_loss_pct": 2.1,
        "nature.habitat.annualised_rate": 9.0, "nature.habitat.confidence": 0.95,
        "nature.ndvi.mean": 0.62, "nature.ndvi.z": 0.58, "nature.ndvi.confidence": 0.5,
    })
    ctx = RenderContext.from_template(get_template("general"), "mnc")
    out = _render_indicator_detail(_state(), [_source(payload=payload)], ctx)
    assert "Nature / Land" in out
    assert "Key metric" in out
    assert "12.3 km to nearest KBA" in out
    assert "45 ha natural loss (2.1% of buffer)" in out
    assert "NDVI mean 0.62" in out


def test_indicator_detail_pillar_pure_for_pillar_report():
    # A GHG report's Indicator Detail has only the GHG table — no Air/Nature.
    payload = _full_payload()
    out = _render_indicator_detail(
        _state(), [_source(payload=payload)],
        RenderContext.from_template(get_template("mnc_ghg"), "mnc"))
    assert "GHG Emissions" in out
    assert "Air Pollution" not in out
    assert "Nature / Land" not in out


# ---------------------------------------------------------------------------
# M-REPORT-A1.1 — composite-formula appendix
# ---------------------------------------------------------------------------

def test_composite_formula_appendix_present_in_screening_reports():
    for tid in ("general", "mnc_ghg", "mnc_air", "mnc_nature"):
        out = _build("mnc", tid)
        assert "Composite score methodology" in out
        assert "composite = ( Air priority + GHG priority + Nature priority" in out
        # Per-pillar weight tables, all three pillars (composite is whole-screening).
        assert "Air Pollution priority" in out
        assert "GHG Emissions priority" in out
        assert "Nature / Land priority" in out


def test_composite_formula_weights_match_constants():
    from engine.constants import (AIR_FOLLOWUP_WEIGHTS, GHG_FOLLOWUP_WEIGHTS,
                                   NATURE_FOLLOWUP_WEIGHTS)
    out = _build("mnc", "general")
    # A couple of representative weights, formatted to 2dp, must appear.
    assert f"{AIR_FOLLOWUP_WEIGHTS['proxy']:.2f}" in out
    assert f"{GHG_FOLLOWUP_WEIGHTS['core_support']:.2f}" in out
    assert f"{NATURE_FOLLOWUP_WEIGHTS['biodiversity_exposure']:.2f}" in out


def test_composite_formula_absent_from_trend_report():
    st = SimpleNamespace(title="T", notes="", user_type="mnc", template_id="trend")
    src = {"id": "t1", "name": "NO₂ trend", "type": "trend",
           "indicator_id": "air.no2.site", "display_name": "NO₂",
           "trend_result": {"trend": 1.0, "significance_bucket": "none",
                            "series": [["2026-01-01", 1.0]]},
           "screening_setup": {"centre": {"lat": 1.0}}}
    out = build_report_html(st, [src], get_template("trend"))
    assert "Composite score methodology" not in out
