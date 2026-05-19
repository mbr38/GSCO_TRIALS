"""Tests for ui.components.p04_indicator_registry (M-P04).

Pure-Python — no Streamlit, no Earth Engine. The registry is the most
drift-prone part of P-04: it pairs hand-curated display names with
engine-canonical IDs. These tests pin the count, the pillar split, the
display-name lookup, and the cross-reference against
``engine.ids.is_valid_id`` — that last test is the one that fails
loudly if the engine renames or removes an indicator the UI still
offers.
"""

# M-P04
from __future__ import annotations

import pytest

from engine.ids import is_valid_id
from ui.components.p04_indicator_registry import (
    ALL_INDICATOR_IDS,
    INDICATORS_BY_PILLAR,
    _DISPLAY_NAMES,
    display_name,
)


# ---------------------------------------------------------------------------
# Count + grouping integrity
# ---------------------------------------------------------------------------

def test_all_indicator_ids_total_nineteen():
    """v1 count is locked at 19 — 9 air + 3 ghg + 7 nature."""
    assert len(ALL_INDICATOR_IDS) == 19


def test_pillar_split_is_nine_three_seven():
    assert len(INDICATORS_BY_PILLAR["air"])    == 9
    assert len(INDICATORS_BY_PILLAR["ghg"])    == 3
    assert len(INDICATORS_BY_PILLAR["nature"]) == 7


def test_no_duplicate_ids_across_pillars():
    """No indicator should appear in two pillars."""
    all_ids = [
        ind
        for pillar in INDICATORS_BY_PILLAR
        for ind in INDICATORS_BY_PILLAR[pillar]
    ]
    assert len(all_ids) == len(set(all_ids))


def test_every_id_has_a_display_name_entry():
    for indicator_id in ALL_INDICATOR_IDS:
        assert indicator_id in _DISPLAY_NAMES


def test_every_id_is_namespaced_to_its_pillar():
    """``<pillar>.…`` prefix matches the bucket it lives in."""
    for pillar, ids in INDICATORS_BY_PILLAR.items():
        for indicator_id in ids:
            assert indicator_id.startswith(f"{pillar}."), indicator_id


# ---------------------------------------------------------------------------
# display_name
# ---------------------------------------------------------------------------

def test_display_name_spot_check():
    assert display_name("air.no2.score") == "NO₂"
    assert display_name("ghg.co2.score") == "CO₂ (ODIAC)"
    assert display_name("nature.kba.proximity_score") == "Key Biodiversity Areas"


def test_display_name_falls_back_to_raw_id():
    """Unknown IDs return themselves rather than crashing the page."""
    assert display_name("nonexistent.id") == "nonexistent.id"
    assert display_name("") == ""


# ---------------------------------------------------------------------------
# Cross-reference against engine canonical IDs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("indicator_id", ALL_INDICATOR_IDS)
def test_every_registry_id_is_a_canonical_engine_id(indicator_id):
    """Each P-04 ID must round-trip through ``engine.ids.is_valid_id``.

    This is the lockstep test: if engine drops or renames an indicator,
    this fails loudly and we know to update the registry rather than
    silently shipping a broken P-04 selection.
    """
    assert is_valid_id(indicator_id), indicator_id
