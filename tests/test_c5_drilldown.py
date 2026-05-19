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
    _fmt,
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

def test_air_formula_has_four_terms():
    assert len(_AIR_FORMULA) == 4


def test_air_formula_weights_sum_to_one():
    assert sum(t.weight for t in _AIR_FORMULA) == pytest.approx(1.0, abs=0.01)


def test_ghg_formula_has_four_terms():
    assert len(_GHG_FORMULA) == 4


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


def test_ghg_rows_has_three_entries():
    assert len(_GHG_ROWS) == 3


def test_ghg_co2_row_reads_mean_not_site():
    """ODIAC's headline value lives at ghg.co2.mean (not .site) per
    the M5.5/M5.6 GHG schema."""
    co2 = next(r for r in _GHG_ROWS if r.indicator == "co2")
    assert co2.value_key == "ghg.co2.mean"


def test_other_ghg_rows_read_site():
    """CH₄ and VIIRS use the standard six-step .site key."""
    for slug in ("ch4", "viirs"):
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
    row_slugs = {r.indicator for r in _GHG_ROWS}
    assert row_slugs == set(_GHG_DATASET_KEYS)
