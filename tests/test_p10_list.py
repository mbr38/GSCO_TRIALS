"""Tests for ui.components.p10_list (M-P10).

Pure-Python. The list/dialog rendering depends on Streamlit and isn't
exercised here; the pure helpers (``_format_row_caption``,
``_apply_delete``) carry the logic that matters.
"""

# M-P10
from __future__ import annotations

import pytest

from ui.components.p10_list import _apply_delete, _format_row_caption


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
