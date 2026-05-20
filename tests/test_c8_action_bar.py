"""Tests for ui.components.c8_action_bar (M-UI-E.5).

Pure-Python. ``_save_as_report`` is the only logic; the render function
is a thin button wrapper. We monkeypatch ``st.session_state`` with a
dict and ``st.toast`` with a no-op — both interfaces the helper uses
are dict-compatible.
"""

# M-UI-E.5
from __future__ import annotations

import uuid

import pytest

from ui.components import c8_action_bar
from ui.components.c8_action_bar import _save_as_report


@pytest.fixture
def stub_streamlit(monkeypatch):
    """Replace st.session_state with a dict and st.toast with a no-op.

    The action-bar module references ``st`` from its imports; we patch
    the module-level alias rather than ``streamlit`` globally to avoid
    leaking state across tests.
    """
    fake_state: dict = {}
    monkeypatch.setattr(c8_action_bar.st, "session_state", fake_state)
    monkeypatch.setattr(c8_action_bar.st, "toast", lambda *a, **kw: None)
    return fake_state


def _payload() -> dict:
    return {"composite.overall_screening": 0.42, "_meta": {"pillars_run": ["air"]}}


# ---------------------------------------------------------------------------
# _save_as_report — list initialisation + append
# ---------------------------------------------------------------------------

def test_save_initialises_saved_analyses_when_missing(stub_streamlit):
    assert "saved_analyses" not in stub_streamlit
    _save_as_report(_payload())
    assert isinstance(stub_streamlit["saved_analyses"], list)
    assert len(stub_streamlit["saved_analyses"]) == 1


def test_save_appends_to_existing_list(stub_streamlit):
    stub_streamlit["saved_analyses"] = [{"id": "preexisting"}]
    _save_as_report(_payload())
    assert len(stub_streamlit["saved_analyses"]) == 2
    assert stub_streamlit["saved_analyses"][0]["id"] == "preexisting"


# ---------------------------------------------------------------------------
# Saved entry schema
# ---------------------------------------------------------------------------

def test_saved_entry_has_canonical_keys(stub_streamlit):
    """The entry shape mirrors the P-10 row schema (M-P10)."""
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert set(entry.keys()) == {
        "id", "name", "type", "screening_setup", "date_saved", "payload",
    }


def test_saved_entry_type_is_screening(stub_streamlit):
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["type"] == "screening"


def test_saved_entry_payload_is_the_dict_passed_in(stub_streamlit):
    """Identity check — the entry references the same dict, no copy."""
    payload = _payload()
    _save_as_report(payload)
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["payload"] is payload


def test_saved_entry_id_is_a_valid_uuid(stub_streamlit):
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    parsed = uuid.UUID(entry["id"])
    assert parsed.version == 4


def test_saved_entry_captures_full_screening_setup(stub_streamlit):
    """M-P10 — the entry stores the full setup so P-10 Open can hydrate
    P-05 with no information loss. Identity check confirms it's the same
    dict from session_state, not a partial copy.
    """
    setup = {
        "centre":           {"lat": -23.5505, "lon": -46.6333},
        "radius_km":        5,
        "time_range":       ("2026-02-19", "2026-05-20"),
        "indicators":       ["air.no2.score", "nature.kba.proximity_score"],
        "mode":             "screening",
        "centre_metadata":  {"source": "P-04 free coordinates"},
    }
    stub_streamlit["screening_setup"] = setup
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["screening_setup"] is setup


def test_saved_entry_name_falls_back_to_zero_when_no_setup(stub_streamlit):
    """No `screening_setup` → name uses (0.0000, 0.0000) sentinel coords."""
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert "(0.0000, 0.0000)" in entry["name"]


# ---------------------------------------------------------------------------
# M-P10-POLISH — name builder reads loaded scope from session_state
# ---------------------------------------------------------------------------

class _FakeChain:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeRegion:
    def __init__(self, name: str, country: str) -> None:
        self.name    = name
        self.country = country


def test_save_name_uses_supply_chain_scope(stub_streamlit):
    """End-to-end: supply-chain scope + node metadata in
    centre_metadata → readable supply-chain name in the saved entry.
    Verifies _save_as_report wires through to _build_save_name with the
    loaded scope from session_state.
    """
    stub_streamlit["screening_setup"] = {
        "centre":          {"lat": -11.86, "lon": -55.51},
        "centre_metadata": {
            "source":    "P-04 supply-chain scope · Soy & Cattle",
            "node_id":   "node_05",
            "node_name": "Sinop Soy Hub",
        },
    }
    stub_streamlit["scope"] = {
        "kind": "supply_chain",
        "data": _FakeChain("Soy & Cattle — Pará / Mato Grosso"),
    }
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["name"] == "Sinop Soy Hub — Soy & Cattle — Pará / Mato Grosso"


def test_save_name_uses_region_scope(stub_streamlit):
    """End-to-end: region scope + region_name/country in
    centre_metadata → readable region name in the saved entry."""
    stub_streamlit["screening_setup"] = {
        "centre":          {"lat": -15.78, "lon": -47.93},
        "centre_metadata": {
            "source":      "P-04 region scope · Distrito Federal, Brazil",
            "region_name": "Distrito Federal",
            "country":     "Brazil",
        },
    }
    stub_streamlit["scope"] = {
        "kind": "region",
        "data": _FakeRegion("Distrito Federal", "Brazil"),
    }
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["name"] == "Distrito Federal, Brazil — Region screening"
