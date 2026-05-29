"""Tests for the saved-analyses search (M-UX-A1 item 2.7).

Pure-Python — the search logic lives in testable helpers
(``_filter_saves`` / ``_matches_search``) so the Streamlit rendering isn't
needed to exercise UX4/UX5/UX6.
"""

# M-UX-A1
from __future__ import annotations

import pytest

from ui.components.p10_list import _filter_saves, _matches_search


def _save(name: str, node_name: str = "", source: str = "") -> dict:
    return {
        "id": name,
        "name": name,
        "screening_setup": {
            "centre_metadata": {"node_name": node_name, "source": source},
        },
    }


@pytest.fixture
def saves() -> list[dict]:
    return [
        _save(
            "Amazon Basin Pilot",
            node_name="Sapezal Plantation (demo)",
            source="P-04 supply-chain scope · Soy & Cattle — Pará / Mato Grosso",
        ),
        _save(
            "Suape Port Industrial Complex — Pernambuco, Brazil",
            node_name="Suape Port Industrial Complex (demo)",
            source="Petrochemical, shipyard & container terminal — NE Brazil",
        ),
        _save(
            "Brasilia low-priority baseline",
            node_name="Brasilia Distrito Federal (demo)",
            source="P-04 supply-chain scope · Federal District",
        ),
    ]


class TestFilterSaves:
    def test_empty_input_shows_all(self, saves) -> None:
        # UX6 — empty input returns the full list unchanged.
        assert _filter_saves(saves, "") == saves

    def test_whitespace_only_shows_all(self, saves) -> None:
        # A search of just spaces strips to empty → full list.
        assert _filter_saves(saves, "   ") == saves

    def test_match_in_name(self, saves) -> None:
        out = _filter_saves(saves, "amazon")
        assert len(out) == 1
        assert out[0]["name"] == "Amazon Basin Pilot"

    def test_match_in_supplier_node_name(self, saves) -> None:
        # Substring lives only in centre_metadata.node_name.
        out = _filter_saves(saves, "plantation")
        assert len(out) == 1
        assert out[0]["name"] == "Amazon Basin Pilot"

    def test_match_in_location_source(self, saves) -> None:
        # Substring lives only in centre_metadata.source.
        out = _filter_saves(saves, "petrochemical")
        assert len(out) == 1
        assert out[0]["name"].startswith("Suape")

    @pytest.mark.parametrize("q", ["AMAZON", "amazon", "Amazon", "aMaZoN"])
    def test_case_insensitive(self, saves, q) -> None:
        # UX5 — case-insensitive substring match.
        out = _filter_saves(saves, q)
        assert len(out) == 1
        assert out[0]["name"] == "Amazon Basin Pilot"

    def test_non_matching_input_returns_empty(self, saves) -> None:
        assert _filter_saves(saves, "no-such-supplier-xyz") == []

    def test_leading_trailing_whitespace_stripped(self, saves) -> None:
        # A search with surrounding whitespace strips before matching.
        out = _filter_saves(saves, "  amazon  ")
        assert len(out) == 1
        assert out[0]["name"] == "Amazon Basin Pilot"

    def test_or_combined_across_fields(self, saves) -> None:
        # "brazil" appears in Suape's name and location but no others.
        out = _filter_saves(saves, "brazil")
        assert len(out) == 1
        assert out[0]["name"].startswith("Suape")

    def test_clearing_input_reshows_full_list(self, saves) -> None:
        # Filter then clear → original list restored.
        assert _filter_saves(saves, "amazon") != saves
        assert _filter_saves(saves, "") == saves

    def test_order_preserved(self, saves) -> None:
        # All three contain "demo" in node_name → order unchanged.
        out = _filter_saves(saves, "demo")
        assert [s["name"] for s in out] == [s["name"] for s in saves]


class TestMatchesSearch:
    def test_defensive_on_missing_centre_metadata(self) -> None:
        # Prioritisation / stub entries without centre_metadata still match
        # on name and don't raise.
        save = {"name": "Batch run over 12 suppliers", "type": "prioritisation"}
        assert _matches_search(save, "batch") is True
        assert _matches_search(save, "suppliers") is True
        assert _matches_search(save, "nope") is False

    def test_defensive_on_none_fields(self) -> None:
        save = {
            "name": None,
            "screening_setup": {"centre_metadata": {"node_name": None, "source": None}},
        }
        # No crash; nothing to match against.
        assert _matches_search(save, "anything") is False
        assert _matches_search(save, "") is True
