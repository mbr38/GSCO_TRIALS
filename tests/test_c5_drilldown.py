"""Tests for ui.components.c5_drilldown (M-UI-E.4).

Pure-Python — no Streamlit. Tests the helpers and the static spec
tuples; the ``render_*`` functions write to Streamlit and can't be
asserted on directly.
"""

# M-UI-E.4
from __future__ import annotations

import pytest

from engine.constants import (
    AIR_FOLLOWUP_WEIGHTS,
    GHG_FOLLOWUP_WEIGHTS,
    NATURE_FOLLOWUP_WEIGHTS,
)
from ui.components.c5_drilldown import (
    _AIR_DATASET_KEYS,
    _AIR_FORMULA,
    _AIR_ROWS,
    _GHG_DATASET_KEYS,
    _GHG_FORMULA,
    _GHG_ROWS,
    _NATURE_DATASET_KEYS,
    _NATURE_FORMULA,
    _ch4_card_fields,
    _build_confidence_terms_rows,
    _compute_final_confidence,
    _fmt,
    _format_extra_value,
    _format_nature_confidence_line,
    _format_provenance_extra_lines,
    _should_render_column_to_surface_row,
)


# ---------------------------------------------------------------------------
# _fmt
# ---------------------------------------------------------------------------

def test_fmt_none_renders_em_dash():
    assert _fmt(None, ".2f") == "—"


def test_fmt_renders_two_decimals():
    assert _fmt(0.1234, ".2f") == "0.12"


def test_fmt_signed_general_format_for_negative_value():
    """Spot-check the ``+.2g`` general format that the anomaly column
    uses — leaves the natural minus sign in place."""
    assert _fmt(-5.0, "+.2g") == "-5"


def test_fmt_signed_general_format_for_positive_value():
    """``+`` flag forces a leading plus for positives."""
    assert _fmt(3.14, "+.2g") == "+3.1"


# ---------------------------------------------------------------------------
# Formula tuples
# ---------------------------------------------------------------------------

# M-TREND-A1 (TR10): Air/GHG follow-up formulas drop the aggregate trend
# term → 3 terms each; Nature keeps its 4 (it never had a trend term).
def test_air_formula_has_three_terms():
    assert len(_AIR_FORMULA) == 3


def test_air_formula_weights_sum_to_one():
    assert sum(t.weight for t in _AIR_FORMULA) == pytest.approx(1.0, abs=0.01)


def test_ghg_formula_has_two_terms():
    # M-GHG-REDESIGN-A1 (GATE B): the spatiotemporal-anomaly term is retired,
    # leaving core_support + quality.
    assert len(_GHG_FORMULA) == 2


def test_ghg_formula_weights_sum_to_one():
    assert sum(t.weight for t in _GHG_FORMULA) == pytest.approx(1.0, abs=0.01)


def test_nature_formula_has_four_terms():
    assert len(_NATURE_FORMULA) == 4


def test_nature_formula_weights_sum_to_one():
    assert sum(t.weight for t in _NATURE_FORMULA) == pytest.approx(1.0, abs=0.01)


def test_formula_weights_track_engine_constants():
    """The UI breakdown is built from engine.constants — if the engine
    rebalances weights, the UI must follow. This test pins the wiring.
    """
    assert (
        {t.weight for t in _AIR_FORMULA}
        == set(AIR_FOLLOWUP_WEIGHTS.values())
    )
    assert (
        {t.weight for t in _GHG_FORMULA}
        == set(GHG_FOLLOWUP_WEIGHTS.values())
    )
    assert (
        {t.weight for t in _NATURE_FORMULA}
        == set(NATURE_FOLLOWUP_WEIGHTS.values())
    )


def test_every_formula_term_payload_key_is_namespaced():
    """Every term reads a key under its pillar's namespace."""
    for term in _AIR_FORMULA:
        assert term.payload_key.startswith("air.")
    for term in _GHG_FORMULA:
        assert term.payload_key.startswith("ghg.")
    for term in _NATURE_FORMULA:
        assert term.payload_key.startswith("nature.")


# ---------------------------------------------------------------------------
# Row specs
# ---------------------------------------------------------------------------

def test_air_rows_has_nine_entries():
    assert len(_AIR_ROWS) == 9


def test_air_rows_first_entry_is_no2():
    """Canonical ordering — NO₂ first because it carries the largest
    weight in air.pollution_proxy_score."""
    assert _AIR_ROWS[0].indicator == "no2"


def test_ghg_rows_has_one_entry():
    # M-CH4-A1 removed CH₄; M-ODIAC-A1 removed CO₂ (ODIAC) — both are reference
    # data, rendered as cards in the "Reference datasets" section, not as scored
    # rows. Only VIIRS nighttime lights remains as a scored raw GHG row.
    assert len(_GHG_ROWS) == 1
    assert {r.indicator for r in _GHG_ROWS} == {"viirs"}


def test_other_ghg_rows_read_site():
    """VIIRS uses the standard six-step .site key (CH₄ and ODIAC removed —
    both reference data)."""
    for slug in ("viirs",):
        row = next(r for r in _GHG_ROWS if r.indicator == slug)
        assert row.value_key == f"ghg.{slug}.site"


# ---------------------------------------------------------------------------
# Dataset key integrity
# ---------------------------------------------------------------------------

def test_air_dataset_keys_count():
    assert len(_AIR_DATASET_KEYS) == 9


def test_ghg_dataset_keys_count():
    assert len(_GHG_DATASET_KEYS) == 3


def test_nature_dataset_keys_count():
    assert len(_NATURE_DATASET_KEYS) == 7


def test_air_row_slugs_match_dataset_keys():
    """Every Air row's indicator slug also appears in the dataset list,
    so each row's value has a discoverable provenance block."""
    row_slugs = {r.indicator for r in _AIR_ROWS}
    assert row_slugs == set(_AIR_DATASET_KEYS)


def test_ghg_row_slugs_match_dataset_keys():
    # M-CH4-A1 / M-ODIAC-A1: scored rows are a subset of the dataset keys. CH₄
    # and CO₂ (ODIAC) stay in _GHG_DATASET_KEYS (their provenance still surfaces
    # in "Datasets used") but are no longer scored rows — both render as
    # reference cards instead.
    row_slugs = {r.indicator for r in _GHG_ROWS}
    assert row_slugs <= set(_GHG_DATASET_KEYS)
    assert "ch4" in _GHG_DATASET_KEYS and "ch4" not in row_slugs
    assert "co2" in _GHG_DATASET_KEYS and "co2" not in row_slugs


# ---------------------------------------------------------------------------
# CH₄ reference card (M-CH4-A1)
# ---------------------------------------------------------------------------

def test_ch4_reference_card_fields():
    """M-CH4-A1 — CH₄ renders as a reference card: raw ppb column reading,
    date-stamped to the screening window, pointing at the P-09 entry, with no
    severity/score framing."""
    payload = {
        "ghg.ch4.site": 1901.0,
        "_provenance.ghg.ch4": {"time_range": ["2026-02-22", "2026-05-23"]},
    }
    fields = _ch4_card_fields(payload)
    assert fields.indicator_id == "ghg.ch4.score"   # P-09 card key
    assert fields.value_str == "1,901 ppb"
    assert "2026-02-22" in fields.vintage_line and "2026-05-23" in fields.vintage_line
    assert "TROPOMI" in fields.source_line


def test_ch4_reference_card_missing_value():
    """RD12 — the card still resolves when CH₄ is unavailable (value_str None)."""
    fields = _ch4_card_fields({})
    assert fields.value_str is None
    assert fields.vintage_line == "Data window: live screening window"


# ---------------------------------------------------------------------------
# Nature confidence row (M-UI-A1-SURFACE Sub-milestone 1)
# ---------------------------------------------------------------------------

def test_format_nature_confidence_line_none_renders_low_glyph_and_em_dash():
    """None confidence → empty/low-tier glyph + canonical em-dash."""
    assert _format_nature_confidence_line(None) == "Confidence: ○ —"


def test_format_nature_confidence_line_high_value_renders_filled_glyph():
    """A value above the high tertile (0.66) renders the filled dot."""
    assert _format_nature_confidence_line(0.756) == "Confidence: ● 0.756"


def test_format_nature_confidence_line_moderate_value_renders_half_glyph():
    """A value in the moderate tertile (0.33–0.66) renders the half dot."""
    assert _format_nature_confidence_line(0.500) == "Confidence: ◐ 0.500"


def test_format_nature_confidence_line_with_label_includes_parenthetical():
    """Multi-indicator cards (e.g. habitat conversion) disambiguate via
    a label that appears in parentheses next to the Confidence prefix."""
    line = _format_nature_confidence_line(0.685, label="habitat")
    assert line == "Confidence (habitat): ● 0.685"


def test_format_nature_confidence_line_uses_three_decimals():
    """Spec calls for 3 decimals (vs Air/GHG uniform row's 2) to align
    with the confidence_terms breakdown coming in Sub-milestone 2."""
    line = _format_nature_confidence_line(0.123456)
    assert "0.123" in line
    assert "0.1234" not in line


# ---------------------------------------------------------------------------
# Confidence terms expander (M-UI-A1-SURFACE Sub-milestone 2)
# ---------------------------------------------------------------------------

_FULL_TERMS = {
    "qa": 0.85,
    "n_valid": 0.70,
    "anomaly_strength": 0.40,
    "spatial_context": 1.00,
    "column_to_surface_uncertainty": "moderate",
}


def test_render_confidence_terms_full_dict_builds_four_rows_with_contributions():
    """Spec 3.1 — full dict produces the four engine-canonical term rows
    with non-None values and matching contributions (value × weight).
    """
    rows = _build_confidence_terms_rows(_FULL_TERMS)
    assert rows is not None
    assert [r.key for r in rows] == ["qa", "n_valid", "anomaly_strength", "spatial_context"]
    # qa: 0.85 × 0.30 = 0.255
    qa_row = rows[0]
    assert qa_row.value == pytest.approx(0.85)
    assert qa_row.weight == pytest.approx(0.30)
    assert qa_row.contribution == pytest.approx(0.255)
    # spatial_context: 1.00 × 0.15 = 0.15
    sc_row = rows[3]
    assert sc_row.contribution == pytest.approx(0.15)


def test_render_confidence_terms_none_and_empty_short_circuit():
    """Spec 3.2 — both None and {} return None so the renderer falls
    through to the 'No confidence breakdown available' caption."""
    assert _build_confidence_terms_rows(None)  is None
    assert _build_confidence_terms_rows({})    is None


def test_render_confidence_terms_partial_dict_with_none_value_carries_strict_none():
    """Spec 3.3 — a per-term None within an otherwise populated dict
    renders the row but carries None as value and contribution. The
    other three terms still compute their contributions cleanly.
    """
    partial = {
        "qa": 0.85,
        "n_valid": None,
        "anomaly_strength": 0.40,
        "spatial_context": 1.00,
        "column_to_surface_uncertainty": "n_a",
    }
    rows = _build_confidence_terms_rows(partial)
    assert rows is not None
    by_key = {r.key: r for r in rows}
    assert by_key["n_valid"].value is None
    assert by_key["n_valid"].contribution is None
    # The other three terms compute normally.
    assert by_key["qa"].contribution               == pytest.approx(0.255)
    assert by_key["anomaly_strength"].contribution == pytest.approx(0.10)
    assert by_key["spatial_context"].contribution  == pytest.approx(0.15)


def test_compute_final_confidence_full_dict_applies_multiplier():
    """c_raw = 0.255 + 0.21 + 0.10 + 0.15 = 0.715; multiplier=0.95
    → c_final ≈ 0.679. Mirrors engine.core.confidence."""
    c_raw, c_final, tag = _compute_final_confidence(_FULL_TERMS)
    assert tag == "moderate"
    assert c_raw   == pytest.approx(0.715)
    assert c_final == pytest.approx(0.715 * 0.95)


def test_compute_final_confidence_strict_none_propagates():
    """Any None term collapses both c_raw and c_final to None — matches
    compute_indicator_confidence's strict-None lock."""
    partial = {**_FULL_TERMS, "n_valid": None}
    c_raw, c_final, _ = _compute_final_confidence(partial)
    assert c_raw   is None
    assert c_final is None


# ---------------------------------------------------------------------------
# Column-to-surface row suppression (Sub-milestone 2 fix)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tag", ["n_a", "strong"])
def test_should_render_column_to_surface_row_hidden_when_multiplier_is_one(tag):
    """The row only adds visual noise when the multiplier is 1.00 —
    both tags map to 1.00 and must be suppressed."""
    assert _should_render_column_to_surface_row(tag) is False


@pytest.mark.parametrize("tag", ["moderate", "moderate_weak", "weak"])
def test_should_render_column_to_surface_row_shown_when_multiplier_penalises(tag):
    """The row renders for tags that actually penalise the confidence."""
    assert _should_render_column_to_surface_row(tag) is True


def test_should_render_column_to_surface_row_handles_none_and_unknown_tags():
    """Defensive: None and unknown tags must not crash and must not render."""
    assert _should_render_column_to_surface_row(None)         is False
    assert _should_render_column_to_surface_row("unknown_tag") is False


# ---------------------------------------------------------------------------
# Provenance extra iteration (Sub-milestone 3)
# ---------------------------------------------------------------------------

def test_provenance_block_renders_extra_fields_excluding_confidence_terms():
    """Spec — extra iteration must surface n_valid_dates / granule_count
    and exclude confidence_terms (which has its own dedicated surface)."""
    extra = {
        "n_valid_dates": 47,
        "granule_count": 2761,
        "confidence_terms": {"qa": 0.85, "n_valid": 1.0},
        "aod_qa_bit_mask": "0xF00",
    }
    lines = _format_provenance_extra_lines(extra)
    rendered = "\n".join(lines)
    assert "Valid dates observed: 47"        in rendered
    assert "Raw image (granule) count: 2761" in rendered
    # The pre-A1 indicator-specific key falls through to the raw label.
    assert "aod_qa_bit_mask: 0xF00"          in rendered
    # confidence_terms must NEVER appear here — it has its own home.
    assert "confidence_terms" not in rendered
    assert "qa: 0.85"         not in rendered


def test_provenance_block_handles_missing_or_empty_extra():
    """Defensive: a missing or empty extra dict must produce no lines
    (the renderer skips the entire 'Extra' subsection cleanly)."""
    assert _format_provenance_extra_lines(None) == []
    assert _format_provenance_extra_lines({})   == []
    # An extra dict containing only confidence_terms also produces no
    # lines — the section header would otherwise dangle empty.
    only_conf_terms = {"confidence_terms": {"qa": 0.85}}
    assert _format_provenance_extra_lines(only_conf_terms) == []


@pytest.mark.parametrize("value, expected", [
    (None,           "—"),
    (47,             "47"),
    (0.123456,       "0.123"),
    (True,           "true"),
    ("0xF00",        "0xF00"),
])
def test_format_extra_value_per_type(value, expected):
    """Type-dispatch sanity for the extra-field value formatter."""
    assert _format_extra_value(value) == expected


def test_format_extra_value_dict_and_list_use_inline_json():
    """Dict / list values pretty-print inline rather than crashing."""
    assert "[1, 2, 3]" in _format_extra_value([1, 2, 3])
    assert "\"a\": 1"  in _format_extra_value({"a": 1})
