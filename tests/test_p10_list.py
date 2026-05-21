"""Tests for ui.components.p10_list (M-P10).

Pure-Python. The list/dialog rendering depends on Streamlit and isn't
exercised here; the pure helpers (``_format_row_caption``,
``_apply_delete``) carry the logic that matters.
"""

# M-P10
from __future__ import annotations

import pytest

from ui.components import p10_list
from ui.components.p10_list import (
    _apply_delete,
    _format_row_caption,
    _open_prioritisation,
)


# ---------------------------------------------------------------------------
# _format_row_caption — happy path + stub-safe fallbacks
# ---------------------------------------------------------------------------

class TestFormatRowCaption:
    def test_full_setup_renders_every_field(self) -> None:
        save = {
            "date_saved": "2026-05-19T14:23:01+00:00",
            "screening_setup": {
                "centre":     {"lat": -3.1019, "lon": -60.0250},
                "radius_km":  25,
                "indicators": ["air.no2.score", "nature.kba.proximity_score"],
            },
        }
        caption = _format_row_caption(save)
        assert "-3.1019, -60.0250" in caption
        assert "25 km" in caption
        assert "Indicators: 2" in caption
        assert "2026-05-19" in caption

    def test_stub_entry_falls_back_to_dashes_without_raising(self) -> None:
        """Stub seed entries have empty screening_setup. The caption must
        render without raising so the seeded rows can still show up.
        """
        save = {
            "id":               "stub",
            "name":             "[stub]",
            "screening_setup":  {},
            "date_saved":       "",
            "payload":          {},
        }
        caption = _format_row_caption(save)
        assert "Centre: —" in caption
        assert "Buffer: — km" in caption
        assert "Indicators: 0" in caption
        assert "Saved: —" in caption

    def test_none_screening_setup_treated_like_empty(self) -> None:
        """Defensive — earlier-shape entries (or a half-deserialised
        stub) where setup is None must not raise.
        """
        save = {"screening_setup": None, "date_saved": "2026-05-19"}
        caption = _format_row_caption(save)
        assert "Centre: —" in caption
        assert "Saved: 2026-05-19" in caption

    def test_partial_centre_missing_lon_falls_back(self) -> None:
        """A centre dict with only ``lat`` set falls back rather than
        rendering "—1.234, None"."""
        save = {
            "screening_setup": {
                "centre":    {"lat": -1.234},
                "radius_km": 5,
            },
            "date_saved": "2026-05-20",
        }
        caption = _format_row_caption(save)
        assert "Centre: —" in caption


# ---------------------------------------------------------------------------
# _apply_delete — pure list filter
# ---------------------------------------------------------------------------

class TestApplyDelete:
    def test_removes_matching_id(self) -> None:
        saves = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        out = _apply_delete(saves, "b")
        assert [s["id"] for s in out] == ["a", "c"]

    def test_preserves_order_of_remaining(self) -> None:
        saves = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
        out = _apply_delete(saves, "c")
        assert [s["id"] for s in out] == ["a", "b", "d"]

    def test_no_match_returns_same_contents(self) -> None:
        saves = [{"id": "a"}, {"id": "b"}]
        out = _apply_delete(saves, "missing")
        assert [s["id"] for s in out] == ["a", "b"]

    def test_returns_a_new_list_not_mutating_input(self) -> None:
        saves = [{"id": "a"}, {"id": "b"}]
        out = _apply_delete(saves, "a")
        # Input untouched — the renderer reassigns session_state, doesn't
        # mutate the existing list. Guard against accidental in-place edits.
        assert [s["id"] for s in saves] == ["a", "b"]
        assert out is not saves


# ---------------------------------------------------------------------------
# M-P08.4: prioritisation-entry dispatch
# ---------------------------------------------------------------------------

class TestPrioritisationCaption:
    def test_prioritisation_entry_renders_batch_caption(self) -> None:
        save = {
            "type":                 "prioritisation",
            "date_saved":           "2026-05-21T09:00:00+00:00",
            "prioritisation_setup": {"radius_km": 5},
            "summary":              {"n_total": 8},
        }
        caption = _format_row_caption(save)
        assert "Prioritisation" in caption
        assert "8 suppliers"    in caption
        assert "5 km buffer"    in caption
        assert "2026-05-21"     in caption

    def test_prioritisation_entry_with_missing_fields_falls_back(self) -> None:
        """Defensive — stub-ish prioritisation entry with missing keys
        still renders without raising."""
        save = {"type": "prioritisation"}
        caption = _format_row_caption(save)
        assert "Prioritisation" in caption
        assert "0 suppliers"    in caption
        assert "— km buffer"    in caption


class TestOpenPrioritisation:
    @pytest.fixture
    def stub_streamlit(self, monkeypatch):
        fake_state: dict = {}
        switches: list[str] = []
        monkeypatch.setattr(p10_list.st, "session_state", fake_state)
        monkeypatch.setattr(
            p10_list.st, "switch_page", lambda path: switches.append(path),
        )
        monkeypatch.setattr(p10_list.st, "error", lambda *a, **kw: None)
        return fake_state, switches

    def test_open_prioritisation_hydrates_state_and_routes(self, stub_streamlit):
        fake_state, switches = stub_streamlit
        save = {
            "id":   "x",
            "type": "prioritisation",
            "prioritisation_setup": {
                "suppliers":  [{"id": "s1", "name": "S1", "lat": 0.0,
                                "lon": 0.0, "source": "ad_hoc"}],
                "radius_km":  5,
                "time_range": ["2026-01-01", "2026-04-01"],
                "indicators": ["air.no2.score"],
            },
            "supplier_results": [{
                "supplier_id": "s1", "name": "S1", "lat": 0.0, "lon": 0.0,
                "source": "ad_hoc", "status": "success",
                "result": {"air.audit_followup_priority": 0.5},
                "error":  None,
            }],
            "summary": {"n_total": 1, "n_success": 1, "n_partial": 0,
                        "n_failed": 0, "n_cancelled": 0},
        }
        _open_prioritisation(save)
        # State rehydrated.
        from ui.prioritisation_state import (
            PrioritisationState, PrioritisationStateKind, SupplierResult,
        )
        state = fake_state["prioritisation_state"]
        assert isinstance(state, PrioritisationState)
        assert state.kind == PrioritisationStateKind.S3_RESULTS
        assert state.setup is save["prioritisation_setup"]
        assert len(state.supplier_results) == 1
        assert isinstance(state.supplier_results[0], SupplierResult)
        assert state.supplier_results[0].name == "S1"
        assert state.total_count == 1
        assert state.cancelled is False
        # Routed to P-08.
        assert switches == ["pages/08_Prioritisation_Results.py"]
        # Setup also stashed (so the page treats this like a fresh batch).
        assert fake_state["prioritisation_setup"] is save["prioritisation_setup"]

    def test_open_prioritisation_missing_supplier_results_no_crash(self, stub_streamlit):
        """Defensive: a save with no supplier_results still opens with an
        empty results list."""
        fake_state, switches = stub_streamlit
        save = {
            "id":                   "y",
            "type":                 "prioritisation",
            "prioritisation_setup": {
                "suppliers":  [],
                "radius_km":  5,
                "time_range": ["2026-01-01", "2026-04-01"],
                "indicators": [],
            },
            # No supplier_results key at all.
            "summary": {},
        }
        _open_prioritisation(save)
        state = fake_state["prioritisation_state"]
        assert state.supplier_results == []
        assert switches == ["pages/08_Prioritisation_Results.py"]

    def test_open_prioritisation_missing_setup_errors_and_no_route(self, stub_streamlit):
        fake_state, switches = stub_streamlit
        save = {"id": "z", "type": "prioritisation"}
        _open_prioritisation(save)
        # No routing, no state hydration.
        assert "prioritisation_state" not in fake_state
        assert switches == []
