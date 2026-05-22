"""Tests for ui.components.p04_form pillar-toggle helper (M-DEMO-POLISH).

Pure-Python — no Streamlit. Pins the truth table for the per-pillar
"Select all" checkbox state derivation. The render function itself
isn't testable without Streamlit, but the state derivation is.
"""

# M-DEMO-POLISH
from __future__ import annotations

from ui.components.p04_form import _pillar_all_selected


_PILLAR = ("air.no2.score", "air.so2.score", "air.co.score")


def test_pillar_all_selected_true_when_every_id_is_in_selected():
    selected = {"air.no2.score", "air.so2.score", "air.co.score"}
    assert _pillar_all_selected(_PILLAR, selected) is True


def test_pillar_all_selected_false_when_subset_is_in_selected():
    selected = {"air.no2.score", "air.co.score"}
    assert _pillar_all_selected(_PILLAR, selected) is False


def test_pillar_all_selected_false_when_empty():
    assert _pillar_all_selected(_PILLAR, set()) is False


def test_pillar_all_selected_true_when_selected_has_extras_from_other_pillars():
    # Extras from outside the pillar don't affect the result —
    # the toggle only cares about its pillar's IDs.
    selected = {
        "air.no2.score", "air.so2.score", "air.co.score",
        "ghg.ch4", "nature.kba",
    }
    assert _pillar_all_selected(_PILLAR, selected) is True
