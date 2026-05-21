"""Tests for ui.components.p08_save_action (M-P08.4).

Pure-Python. The render path uses ``st.session_state`` / ``st.toast``;
we monkeypatch the module-level alias rather than ``streamlit`` itself
so tests stay isolated.
"""

# M-P08.4
from __future__ import annotations

import pytest

from ui.components import p08_save_action
from ui.components.p08_save_action import (
    _build_save_entry,
    save_prioritisation_as_report,
)
from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
    SupplierResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _supplier(name: str, status: str = "success") -> SupplierResult:
    payload = {
        "air.audit_followup_priority": 0.5,
        "ghg.audit_followup_priority": 0.5,
        "nature.followup_priority":    0.5,
        "composite.overall_screening": 0.5,
    } if status not in ("failed", "cancelled") else None
    return SupplierResult(
        supplier_id=name.lower(),
        name=name,
        lat=0.0, lon=0.0, source="ad_hoc",
        status=status,
        result=payload,
        error=None,
    )


def _state(suppliers: list[SupplierResult], indicators: list[str]) -> PrioritisationState:
    setup = {
        "suppliers":  [
            {"id": s.supplier_id, "name": s.name, "lat": s.lat,
             "lon": s.lon, "source": s.source}
            for s in suppliers
        ],
        "radius_km":  5,
        "time_range": ["2026-01-01", "2026-04-01"],
        "indicators": indicators,
        "mode":       "prioritisation",
    }
    return PrioritisationState(
        kind=PrioritisationStateKind.S3_RESULTS,
        setup=setup,
        supplier_results=suppliers,
        completed_count=len(suppliers),
        total_count=len(suppliers),
    )


@pytest.fixture
def stub_streamlit(monkeypatch):
    """Replace st.session_state with a dict and st.toast with a recorder."""
    fake_state: dict = {}
    toasts: list[tuple[str, dict]] = []
    monkeypatch.setattr(p08_save_action.st, "session_state", fake_state)
    monkeypatch.setattr(
        p08_save_action.st, "toast",
        lambda msg, **kw: toasts.append((msg, kw)),
    )
    return fake_state, toasts


# ---------------------------------------------------------------------------
# _build_save_entry — pure builder
# ---------------------------------------------------------------------------

def test_build_save_entry_happy_path_three_successes():
    suppliers = [_supplier(n) for n in ("A", "B", "C")]
    state = _state(suppliers, [
        "air.no2.score", "ghg.ch4.score", "nature.kba.proximity_score",
    ])
    entry = _build_save_entry(state)
    assert entry["type"]                == "prioritisation"
    assert entry["prioritisation_setup"] is state.setup
    assert len(entry["supplier_results"]) == 3
    assert entry["summary"]             == {
        "n_total": 3, "n_success": 3, "n_partial": 0,
        "n_failed": 0, "n_cancelled": 0,
    }
    # Name includes supplier count + pillar list + a UTC timestamp.
    assert "3 suppliers" in entry["name"]
    assert "UTC"          in entry["name"]


def test_build_save_entry_mixed_status_summary():
    suppliers = [
        _supplier("A", status="success"),
        _supplier("B", status="success"),
        _supplier("C", status="partial"),
        _supplier("D", status="failed"),
        _supplier("E", status="cancelled"),
    ]
    state = _state(suppliers, ["air.no2.score", "ghg.ch4.score",
                               "nature.kba.proximity_score"])
    entry = _build_save_entry(state)
    assert entry["summary"] == {
        "n_total": 5, "n_success": 2, "n_partial": 1,
        "n_failed": 1, "n_cancelled": 1,
    }


def test_build_save_entry_single_pillar_batch_reflects_in_name():
    suppliers = [_supplier("A")]
    state = _state(suppliers, ["air.no2.score", "air.so2.score"])
    entry = _build_save_entry(state)
    # Pillar list in the name reflects only the selected pillar.
    assert "(air)" in entry["name"]
    assert "ghg" not in entry["name"]
    assert "nature" not in entry["name"]


def test_build_save_entry_uuids_unique_across_calls():
    suppliers = [_supplier("A")]
    state = _state(suppliers, ["air.no2.score"])
    e1 = _build_save_entry(state)
    e2 = _build_save_entry(state)
    assert e1["id"] != e2["id"]


def test_build_save_entry_supplier_results_serialised_as_dicts():
    """Pin the serialisation contract — the saved list is plain dicts
    (via dataclasses.asdict), not SupplierResult instances, so json.dumps
    via Export JSON works without a custom encoder."""
    suppliers = [_supplier("A")]
    state = _state(suppliers, ["air.no2.score"])
    entry = _build_save_entry(state)
    serialised = entry["supplier_results"][0]
    assert isinstance(serialised, dict)
    assert serialised["name"]   == "A"
    assert serialised["status"] == "success"
    assert "result" in serialised


# ---------------------------------------------------------------------------
# save_prioritisation_as_report — session-state surface
# ---------------------------------------------------------------------------

def test_save_initialises_saved_analyses_when_missing(stub_streamlit):
    fake_state, toasts = stub_streamlit
    suppliers = [_supplier("A")]
    state = _state(suppliers, ["air.no2.score"])
    save_prioritisation_as_report(state)
    assert isinstance(fake_state["saved_analyses"], list)
    assert len(fake_state["saved_analyses"]) == 1
    assert fake_state["saved_analyses"][0]["type"] == "prioritisation"
    assert len(toasts) == 1
    assert "Saved as" in toasts[0][0]


def test_save_preserves_existing_entries(stub_streamlit):
    fake_state, _ = stub_streamlit
    fake_state["saved_analyses"] = [{"id": "preexisting", "type": "screening"}]
    suppliers = [_supplier("A")]
    state = _state(suppliers, ["air.no2.score"])
    save_prioritisation_as_report(state)
    assert len(fake_state["saved_analyses"]) == 2
    assert fake_state["saved_analyses"][0]["id"] == "preexisting"


def test_save_empty_results_warns_and_does_not_save(stub_streamlit):
    fake_state, toasts = stub_streamlit
    state = PrioritisationState(
        kind=PrioritisationStateKind.S3_RESULTS,
        setup={"suppliers": [], "radius_km": 5, "indicators": [],
               "time_range": ["2026-01-01", "2026-04-01"]},
        supplier_results=[],
    )
    save_prioritisation_as_report(state)
    assert "saved_analyses" not in fake_state
    assert len(toasts) == 1
    assert "Nothing to save" in toasts[0][0]
