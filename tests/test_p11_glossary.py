"""Tests for the content-aware glossary appendix (M-REPORT-A1 §6).

Pure-Python. Pins content-awareness (RT13 — only terms present render), the
word-boundary guard (no partial-word false positives), family grouping order,
and determinism (RT15).
"""

# M-REPORT-A1
from __future__ import annotations

from ui.components.p11_glossary import collect_terms, render_glossary


def _terms(html: str) -> set[str]:
    return {t.term for t in collect_terms(html)}


# ---------------------------------------------------------------------------
# Content-awareness (RT13)
# ---------------------------------------------------------------------------

def test_only_present_terms_are_selected():
    html = "<p>The Theil-Sen slope was significant (p-value 0.01).</p>"
    present = _terms(html)
    assert "Theil-Sen slope" in present
    assert "p-value" in present
    # A term not in the text must not be selected.
    assert "NDVI" not in present
    assert "ESRS E1 / E2 / E4" not in present


def test_render_omits_unused_terms():
    html = "<p>NDVI dropped sharply this season.</p>"
    out = render_glossary(html)
    assert "NDVI" in out
    assert "vegetation-health index" in out
    # No ESRS / trend definitions when those terms are absent.
    assert "Theil-Sen" not in out
    assert "EU disclosure standards" not in out


def test_empty_report_renders_header_with_note():
    out = render_glossary("<p>Nothing notable here at all.</p>")
    assert "<h2>Glossary</h2>" in out
    assert "No glossary terms were used" in out


# ---------------------------------------------------------------------------
# Word-boundary guard (Step A §8.5 false-positive risk)
# ---------------------------------------------------------------------------

def test_acronym_not_matched_inside_a_larger_token():
    # "AOD" must not match inside "AODX"; "AOI" must not match "AOIX".
    html = "<p>The AODX sensor and the AOIX region are unrelated.</p>"
    present = _terms(html)
    assert "AOD (Aerosol Optical Depth)" not in present
    assert "AOI / buffer" not in present


def test_acronym_matched_as_standalone_token():
    html = "<p>AOD was high; the AOI buffer was 5 km.</p>"
    present = _terms(html)
    assert "AOD (Aerosol Optical Depth)" in present
    assert "AOI / buffer" in present


def test_tags_are_stripped_before_scanning():
    # A term appearing only inside an attribute/tag should still be reachable
    # via visible text; here NDVI is visible text, the class name is noise.
    html = "<section class='ndvi-block'><p>NDVI trend</p></section>"
    assert "NDVI" in _terms(html)


# ---------------------------------------------------------------------------
# Grouping + determinism
# ---------------------------------------------------------------------------

def test_families_render_in_fixed_order():
    # Include one term from each family; statistical → methodological → domain.
    html = "<p>z-score anomaly NDVI</p>"
    out = render_glossary(html)
    assert out.index("Statistical") < out.index("Methodological") < out.index(
        "Domain / dataset"
    )


def test_glossary_is_deterministic():
    html = "<p>Theil-Sen slope, p-value, NDVI, ESRS E2 pollution.</p>"
    assert render_glossary(html) == render_glossary(html)


def test_esrs_term_selected_via_topical_code():
    html = "<h2>ESRS E2 — Pollution: metrics &amp; evidence</h2>"
    out = render_glossary(html)
    assert "ESRS E1 / E2 / E4" in out
    assert "EU disclosure standards" in out
