"""Tests for the P-08 → P-05 drill-in path (M-P08.4).

Pure-Python. The drill helper writes session_state, calls st.toast,
and routes via st.switch_page — all of which are monkeypatched out.
"""

# M-P08.4
from __future__ import annotations

import pytest

from ui.components import p08_ranked_table
from ui.components.p08_ranked_table import (
    _hydrate_p05_and_route,
    drill_to_supplier,
)
from ui.prioritisation_state import (
    PrioritisationState,
    PrioritisationStateKind,
    SupplierResult,
)


def _supplier(
    name: str = "Demo Site",
    status: str = "success",
    result: dict | None = None,
    error: str | None = None,
) -> SupplierResult:
    if result is None and status not in ("failed", "cancelled"):
        result = {
            "air.audit_followup_priority": 0.5,
            "composite.overall_screening": 0.5,
        }
    return SupplierResult(
        supplier_id=name.lower().replace(" ", "_"),
        name=name,
        lat=-23.5505, lon=-46.6333, source="ad_hoc",
        status=status, result=result, error=error,
    )


def _state(suppliers: list[SupplierResult]) -> PrioritisationState:
    return PrioritisationState(
        kind=PrioritisationStateKind.S3_RESULTS,
        setup={
            "suppliers":  [],
            "radius_km":  5,
            "time_range": ["2026-01-01", "2026-04-01"],
            "indicators": ["air.no2.score", "ghg.ch4.score"],
            "mode":       "prioritisation",
        },
        supplier_results=suppliers,
    )


@pytest.fixture
def stub_streamlit(monkeypatch):
    """Patch the module-level st alias the drill helpers reach through."""
    fake_state: dict = {}
    toasts:    list[tuple[str, dict]] = []
    switches:  list[str] = []
    monkeypatch.setattr(p08_ranked_table.st, "session_state", fake_state)
    monkeypatch.setattr(
        p08_ranked_table.st, "toast",
        lambda msg, **kw: toasts.append((msg, kw)),
    )
    monkeypatch.setattr(
        p08_ranked_table.st, "switch_page",
        lambda path: switches.append(path),
    )
    return fake_state, toasts, switches


# ---------------------------------------------------------------------------
# drill_to_supplier
# ---------------------------------------------------------------------------

def test_drill_happy_path_hydrates_p05_state_and_navigates(stub_streamlit):
    fake_state, toasts, switches = stub_streamlit
    supplier = _supplier("Demo Site")
    state    = _state([supplier])

    drill_to_supplier(state, "Demo Site")

    assert switches == ["pages/05_Screening_Results.py"]
    # screening_setup hydrated with the supplier's coords + batch params.
    setup = fake_state["screening_setup"]
    assert setup["centre"]    == {"lat": -23.5505, "lon": -46.6333}
    assert setup["radius_km"] == 5
    assert setup["indicators"] == ["air.no2.score", "ghg.ch4.score"]
    assert setup["centre_metadata"]["node_name"] == "Demo Site"
    # page_state set to S2_Results.
    page_state = fake_state["page_state"]
    assert page_state.name   == "S2_Results"
    assert page_state.result is supplier.result
    # Drill-origin flag set.
    assert fake_state["p05_drill_origin"] == "prioritisation"
    # No warning toast on the happy path.
    assert toasts == []


def test_drill_failed_supplier_toasts_no_navigation(stub_streamlit):
    fake_state, toasts, switches = stub_streamlit
    supplier = _supplier("Bad Site", status="failed", error="EE timeout")
    state    = _state([supplier])

    drill_to_supplier(state, "Bad Site")

    assert switches == []
    assert "screening_setup" not in fake_state
    assert len(toasts) == 1
    assert "no result to inspect"   in toasts[0][0]
    assert "failed"                 in toasts[0][0]


def test_drill_cancelled_supplier_toasts_no_navigation(stub_streamlit):
    fake_state, toasts, switches = stub_streamlit
    supplier = _supplier("Skipped Site", status="cancelled")
    state    = _state([supplier])

    drill_to_supplier(state, "Skipped Site")

    assert switches == []
    assert "screening_setup" not in fake_state
    assert len(toasts) == 1
    assert "cancelled" in toasts[0][0]


def test_drill_supplier_with_none_result_toasts(stub_streamlit):
    """Defensive — status looks successful but result is None."""
    fake_state, toasts, switches = stub_streamlit
    supplier = SupplierResult(
        supplier_id="defensive", name="Defensive",
        lat=0.0, lon=0.0, source="ad_hoc",
        status="success", result=None, error=None,
    )
    state = _state([supplier])

    drill_to_supplier(state, "Defensive")

    assert switches == []
    assert len(toasts) == 1
    assert "no result to inspect" in toasts[0][0]


def test_drill_unknown_name_is_noop(stub_streamlit):
    """Defensive — name not in the supplier list. No crash, no nav."""
    fake_state, toasts, switches = stub_streamlit
    state = _state([_supplier("Demo Site")])

    drill_to_supplier(state, "Nonexistent")

    assert switches == []
    assert toasts == []
    assert "screening_setup" not in fake_state


# ---------------------------------------------------------------------------
# _hydrate_p05_and_route — shape contract
# ---------------------------------------------------------------------------

def test_hydrate_p05_setup_shape(stub_streamlit):
    fake_state, _, switches = stub_streamlit
    supplier = _supplier("Demo Site")
    batch_setup = {
        "radius_km":  10,
        "time_range": ["2026-01-01", "2026-04-01"],
        "indicators": ["air.no2.score"],
    }
    _hydrate_p05_and_route(supplier, batch_setup)

    setup = fake_state["screening_setup"]
    assert setup["mode"]      == "screening"
    assert setup["radius_km"] == 10
    cm = setup["centre_metadata"]
    assert cm["node_id"]   == "demo_site"
    assert cm["node_name"] == "Demo Site"
    assert "P-08 batch"     in cm["source"]
    # Flag set so P-05 can render the back-link.
    assert fake_state["p05_drill_origin"] == "prioritisation"
    assert switches == ["pages/05_Screening_Results.py"]
