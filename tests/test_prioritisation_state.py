"""Tests for ui.prioritisation_state (M-P08.1).

Pure-Python — no Streamlit. Covers ``classify`` decisions, the
``PrioritisationState`` defaults, and the ``SupplierResult`` shape.
"""

# M-P08.1
from __future__ import annotations

import dataclasses

from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
    SupplierResult,
    classify,
    selected_pillars,
)


# ---------------------------------------------------------------------------
# classify
# ---------------------------------------------------------------------------

def test_classify_none_setup_routes_to_e1():
    assert classify(None) == PrioritisationStateKind.E1_FAILED


def test_classify_empty_dict_routes_to_e1():
    assert classify({}) == PrioritisationStateKind.E1_FAILED


def test_classify_empty_suppliers_routes_to_e1():
    setup = {"suppliers": [], "radius_km": 5, "indicators": ["air.no2.score"]}
    assert classify(setup) == PrioritisationStateKind.E1_FAILED


def test_classify_one_supplier_routes_to_s2_running():
    setup = {
        "suppliers": [
            {"id": "x", "name": "X", "lat": 0.0, "lon": 0.0, "source": "ad_hoc"},
        ],
        "radius_km": 5,
        "indicators": ["air.no2.score"],
        "time_range": ["2026-01-01", "2026-04-01"],
    }
    assert classify(setup) == PrioritisationStateKind.S2_RUNNING


# ---------------------------------------------------------------------------
# Dataclass shapes
# ---------------------------------------------------------------------------

def test_prioritisation_state_defaults_are_sensible():
    state = PrioritisationState(kind=PrioritisationStateKind.S2_RUNNING)
    assert state.setup is None
    assert state.supplier_results == []
    assert state.completed_count == 0
    assert state.total_count == 0
    assert state.cancelled is False
    assert state.error is None


def test_supplier_result_has_eight_fields():
    """Pin the SupplierResult shape — 6 required + 2 optional = 8 total."""
    fields = dataclasses.fields(SupplierResult)
    assert [f.name for f in fields] == [
        "supplier_id", "name", "lat", "lon", "source",
        "status", "result", "error",
    ]


# ---------------------------------------------------------------------------
# selected_pillars
# ---------------------------------------------------------------------------

def test_selected_pillars_all_three():
    setup = {
        "indicators": [
            "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
        ],
    }
    assert selected_pillars(setup) == {"air", "ghg", "nature"}


def test_selected_pillars_air_only():
    setup = {"indicators": ["air.no2.score", "air.so2.score"]}
    assert selected_pillars(setup) == {"air"}


def test_selected_pillars_two_pillars():
    setup = {"indicators": ["air.no2.score", "ghg.ch4.score"]}
    assert selected_pillars(setup) == {"air", "ghg"}


def test_selected_pillars_empty_setup_returns_empty():
    assert selected_pillars({}) == set()


def test_selected_pillars_none_setup_returns_empty():
    assert selected_pillars(None) == set()


def test_selected_pillars_empty_indicator_list_returns_empty():
    assert selected_pillars({"indicators": []}) == set()
