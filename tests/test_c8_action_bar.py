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
    """The entry shape mirrors the planned P-10 row schema."""
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert set(entry.keys()) == {"id", "name", "type", "scope", "date_saved", "payload"}


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


def test_saved_entry_pulls_scope_from_screening_setup(stub_streamlit):
    """The scope block reads centre + radius from the session-stored setup."""
    stub_streamlit["screening_setup"] = {
        "centre":    {"lat": -23.5505, "lon": -46.6333},
        "radius_km": 5,
    }
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert entry["scope"] == {
        "centre":    {"lat": -23.5505, "lon": -46.6333},
        "radius_km": 5,
    }


def test_saved_entry_name_falls_back_to_zero_when_no_setup(stub_streamlit):
    """No `screening_setup` → name uses (0.0000, 0.0000) sentinel coords."""
    _save_as_report(_payload())
    entry = stub_streamlit["saved_analyses"][0]
    assert "(0.0000, 0.0000)" in entry["name"]
